from __future__ import annotations

import asyncio
import hmac
import json
import os
import secrets
import threading
import time
from collections import deque
from urllib.parse import parse_qs, urlparse

import websockets
from flask import Flask, Response, abort, jsonify, make_response, request, send_from_directory
from werkzeug.serving import make_server

import utils.globals as g
from api import commands, diagnostics, landmarks, preview, state
from utils import logfile, metrics
from utils.config import save_config
from utils.paths import app_str
from utils.version import VERSION

HOST = "127.0.0.1"
HTTP_PORT = 8890
WS_PORT = 8891

TOKEN_HEADER = "X-ExVR-Token"
TOKEN_QUERY = "k"
TOKEN_COOKIE = "exvr_api"

ALLOWED_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1"}

SHUTDOWN_TIMEOUT = 3.0

LANDMARK_HZ = 20.0
METRICS_HZ = 1.0

NOTICE_BACKLOG = 8

_pending_notices: deque = deque(maxlen=NOTICE_BACKLOG)

HANDSHAKE_PREFIX = "EXVR-HANDSHAKE "

_token: str | None = None


def token() -> str:
    global _token
    if _token is None:
        _token = secrets.token_urlsafe(24)
        logfile.add_secret(_token)
    return _token


def authorised(supplied) -> bool:
    return bool(supplied) and hmac.compare_digest(str(supplied), token())


class ControlApi:

    def __init__(self, store=None, frames=None):
        self.store = store or state.store()
        self.frames = frames or preview.broker()
        self.app = Flask(__name__,
                         template_folder=app_str("templates"),
                         static_folder=None)
        self._server = None
        self._http_thread = None
        self._ws_server = None
        self._ws_thread = None
        self._ws_loop = None
        self._clients: set = set()
        self._stopping = False
        self._started_at = time.time()
        self._setup_routes()
        self._unsubscribe = self.store.subscribe(self._on_config_change)

    def _setup_routes(self):
        app = self.app
        app.before_request(self._require_token)
        app.add_url_rule("/", "index", self._index)
        app.add_url_rule("/ui/<path:filename>", "ui", self._ui_asset)
        app.add_url_rule("/api/health", "health", self._health)
        app.add_url_rule("/api/state", "state", self._state)
        app.add_url_rule("/api/tree/<name>", "tree_get", self._tree_get)
        app.add_url_rule("/api/tree/<name>", "tree_patch", self._tree_patch,
                         methods=["PATCH"])
        app.add_url_rule("/api/tree/<name>/save", "tree_save", self._tree_save,
                         methods=["POST"])
        app.add_url_rule("/api/reload", "reload", self._reload, methods=["POST"])
        app.add_url_rule("/api/metrics", "metrics", self._metrics)
        app.add_url_rule("/api/topology", "topology", self._topology)
        app.add_url_rule("/api/landmarks", "landmarks", self._landmarks)
        app.add_url_rule("/api/preview.mjpeg", "mjpeg", self._mjpeg)
        app.add_url_rule("/api/preview.jpg", "jpeg", self._jpeg)
        app.add_url_rule("/api/commands", "commands", self._commands)
        app.add_url_rule("/api/command/<name>", "command", self._command,
                         methods=["POST"])
        app.add_url_rule("/api/choices", "choices", self._choices)
        app.add_url_rule("/api/pairing", "pairing", self._pairing)
        app.add_url_rule("/api/pairing/rotate", "pairing_rotate",
                         self._pairing_rotate, methods=["POST"])
        app.add_url_rule("/api/diagnostics", "diagnostics", self._diagnostics,
                         methods=["GET", "POST"])

    def _require_token(self):
        host = (request.host or "").split(":")[0]
        if host not in ALLOWED_HOSTS:
            abort(404)
        supplied = (request.headers.get(TOKEN_HEADER)
                    or request.args.get(TOKEN_QUERY)
                    or request.cookies.get(TOKEN_COOKIE))
        if not authorised(supplied):
            abort(403)
        return None

    def _index(self):
        response = make_response(
            send_from_directory(app_str("templates", "ui"), "index.html"))
        response.set_cookie(TOKEN_COOKIE, token(), samesite="Strict",
                            httponly=False, secure=False, path="/")
        return response

    def _ui_asset(self, filename):
        return send_from_directory(app_str("templates", "ui"), filename)

    def _health(self):
        return jsonify(self.status())

    def status(self) -> dict:
        return {
            "ok": True,
            "version": VERSION,
            "uptime": round(time.time() - self._started_at, 1),
            "tracking": commands.query("tracking_active", default=False),
            "preview": commands.query("preview_active", default=False),
            "fps": round(float(g.current_fps or 0.0), 2),
            "metrics_enabled": metrics.ENABLED,
            "log": str(logfile.log_path()),
            "websocket": f"ws://{HOST}:{WS_PORT}/",
            "steamvr": commands.query("steamvr_present", default=False),
            "driver_installed": commands.query("driver_installed", default=False),
        }

    def _state(self):
        return jsonify({
            "status": self.status(),
            "trees": {name: self.store.snapshot(name) for name in state.TREES},
            "writable": [name for name in state.TREES if self.store.writable(name)],
            "restart_required_paths": sorted(state.RESTART_REQUIRED),
        })

    def _tree_get(self, name):
        if name not in state.TREES:
            abort(404)
        return jsonify({"tree": name, "writable": self.store.writable(name),
                        "value": self.store.snapshot(name)})

    def _metrics(self):
        return jsonify(metrics.snapshot())

    def _topology(self):
        return jsonify(landmarks.topology())

    def _landmarks(self):
        return jsonify(landmarks.snapshot())

    def _tree_patch(self, name):
        if name not in state.TREES:
            abort(404)
        delta = request.get_json(silent=True)
        if delta is None:
            return jsonify({"error": "expected a JSON object body"}), 400
        try:
            change = self.store.apply(name, delta)
        except state.DeltaError as exc:
            return jsonify({"error": "invalid delta",
                            "rejected": exc.rejections}), 422
        return jsonify(change.as_dict())

    def _tree_save(self, name):
        if not self.store.writable(name):
            abort(404)
        from utils import bootstrap
        if name == "config":
            save_config(g.config)
        elif name == "default_data":
            bootstrap.save_all()
        else:
            abort(404)
        return jsonify({"saved": name})

    def _reload(self):
        from utils import bootstrap
        bootstrap.reload_all()
        self._broadcast({"type": "reloaded", "status": self.status()})
        return jsonify({"reloaded": True, "status": self.status()})

    def _commands(self):
        return jsonify({"commands": commands.names()})

    def _command(self, name):
        payload = request.get_json(silent=True) or {}
        try:
            result = commands.invoke(name, **payload)
        except KeyError:
            return jsonify({"error": f"unknown command {name!r}",
                            "commands": commands.names()}), 404
        except Exception as exc:
            return jsonify({"error": repr(exc)}), 500
        return jsonify({"command": name, "result": result,
                        "status": self.status()})

    def _choices(self):
        return jsonify(commands.query("choices", default={}))

    def _pairing(self):
        from utils import network, pairing

        token = pairing.get_or_create_token()
        port = g.config["Controller"]["server_port"] if g.config else 8888
        query = f"?{pairing.QUERY_KEY}={token}"
        found = network.private_ips()
        urls = [f"https://{ip}:{port}/{query}" for _name, ip in found]
        urls.append(f"https://127.0.0.1:{port}/{query}")
        return jsonify({
            "code": token,
            "urls": urls,
            "interfaces": [{"name": name, "label": network.interface_label(name),
                            "ip": ip} for name, ip in found],
        })

    def _pairing_rotate(self):
        from utils import pairing

        pairing.rotate_token()
        return self._pairing()

    def _mjpeg(self):
        body = self.frames.mjpeg(stop=lambda: self._stopping)
        response = Response(body, mimetype=f"multipart/x-mixed-replace; "
                                          f"boundary={preview.BOUNDARY}")
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Accel-Buffering"] = "no"
        return response

    def _jpeg(self):
        payload = self.frames.snapshot_jpeg()
        if payload is None:
            return jsonify({"error": "no frame; tracking is not running"}), 503
        return Response(payload, mimetype="image/jpeg",
                        headers={"Cache-Control": "no-store"})

    def _diagnostics(self):
        name, blob = diagnostics.build(
            g.config,
            extra={"status": self.status(), "commands": commands.names()},
            preview_jpeg=self.frames.snapshot_jpeg() if self.frames.wanted else None,
        )
        return Response(blob, mimetype="application/zip", headers={
            "Content-Disposition": f'attachment; filename="{name}"',
        })

    async def _ws_handler(self, socket, path):
        query = parse_qs(urlparse(path or "").query)
        if not authorised(query.get(TOKEN_QUERY, [None])[0]):
            await socket.close(1008, "token required")
            return

        session = {"landmarks": False, "metrics": False}
        self._clients.add(socket)
        try:
            await socket.send(json.dumps({
                "type": "hello",
                "status": self.status(),
                "topology": landmarks.topology(),
                "trees": {name: self.store.snapshot(name) for name in state.TREES},
                "writable": [n for n in state.TREES if self.store.writable(n)],
                "restart_required_paths": sorted(state.RESTART_REQUIRED),
                "commands": commands.names(),
                "notices": self._drain_notices(),
            }))
            pusher = asyncio.ensure_future(self._push_loop(socket, session))
            try:
                await self._receive_loop(socket, session)
            finally:
                pusher.cancel()
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._clients.discard(socket)

    async def _receive_loop(self, socket, session):
        async for raw in socket:
            try:
                message = json.loads(raw)
            except ValueError:
                await socket.send(json.dumps({"type": "error",
                                              "error": "not JSON"}))
                continue
            kind = message.get("type")

            if kind == "patch":
                name = message.get("tree", "config")
                try:
                    change = self.store.apply(name, message.get("delta") or {})
                except state.DeltaError as exc:
                    await socket.send(json.dumps({"type": "rejected",
                                                  "tree": name,
                                                  "rejected": exc.rejections}))
                    continue
                await socket.send(json.dumps({"type": "applied",
                                              **change.as_dict()}))

            elif kind == "command":
                name = message.get("name", "")
                try:
                    result = commands.invoke(name, **(message.get("args") or {}))
                except KeyError:
                    await socket.send(json.dumps({
                        "type": "error", "error": f"unknown command {name!r}"}))
                    continue
                except Exception as exc:
                    await socket.send(json.dumps({
                        "type": "error", "error": repr(exc)}))
                    continue
                await socket.send(json.dumps({"type": "command",
                                              "name": name, "result": result,
                                              "status": self.status()}))

            elif kind == "subscribe":
                for key in ("landmarks", "metrics"):
                    if key in message:
                        session[key] = bool(message[key])
                await socket.send(json.dumps({"type": "subscribed",
                                              **session}))

            elif kind == "ping":
                await socket.send(json.dumps({"type": "pong",
                                              "status": self.status()}))

            else:
                await socket.send(json.dumps({"type": "error",
                                              "error": f"unknown type {kind!r}"}))

    async def _push_loop(self, socket, session):
        landmark_interval = 1.0 / LANDMARK_HZ
        metrics_interval = 1.0 / METRICS_HZ
        next_metrics = 0.0
        try:
            while True:
                now = time.perf_counter()
                if session["landmarks"]:
                    await socket.send(json.dumps({"type": "landmarks",
                                                  **landmarks.snapshot()}))
                if session["metrics"] and now >= next_metrics:
                    next_metrics = now + metrics_interval
                    await socket.send(json.dumps({"type": "metrics",
                                                  "series": metrics.snapshot(),
                                                  "status": self.status()}))
                await asyncio.sleep(landmark_interval)
        except (asyncio.CancelledError, websockets.exceptions.ConnectionClosed):
            pass

    def notify_status(self) -> None:
        self._broadcast({"type": "status", "status": self.status()})

    def notify_change(self, tree: str, changed: dict) -> None:
        self._broadcast({
            "type": "changed",
            "tree": tree,
            "changed": {path: {"from": None, "to": value}
                        for path, value in changed.items()},
            "derived": {},
            "restart_required": [],
        })

    def notice(self, body: str, title: str = "", kind: str = "info",
               modal: bool = False) -> None:
        payload = {"type": "notice", "kind": kind, "title": title,
                   "body": body, "modal": modal}
        if self._clients:
            self._broadcast(payload)
        else:
            _pending_notices.append(payload)

    def _drain_notices(self) -> list[dict]:
        drained = []
        while True:
            try:
                drained.append(_pending_notices.popleft())
            except IndexError:
                return drained

    def _on_config_change(self, change: state.Change):
        self._broadcast({"type": "changed", **change.as_dict()})

    def _broadcast(self, payload: dict) -> None:
        loop, clients = self._ws_loop, list(self._clients)
        if loop is None or not clients or loop.is_closed():
            return
        body = json.dumps(payload)

        async def send_all():
            for socket in clients:
                try:
                    await socket.send(body)
                except Exception:
                    pass

        try:
            asyncio.run_coroutine_threadsafe(send_all(), loop)
        except RuntimeError:
            pass

    def start(self, handshake: bool = False) -> None:
        self._stopping = False
        self._server = make_server(HOST, HTTP_PORT, self.app, threaded=True)
        self._http_thread = threading.Thread(
            target=self._server.serve_forever, name="ApiHttp", daemon=True)
        self._http_thread.start()

        ready = threading.Event()
        self._ws_thread = threading.Thread(
            target=self._run_ws_loop, args=(ready,), name="ApiWs", daemon=True)
        self._ws_thread.start()
        ready.wait(SHUTDOWN_TIMEOUT)
        self._announce(handshake)

    def _announce(self, handshake: bool) -> None:
        out = logfile.console()
        lines = [
            "============================",
            f"Control API  http://{HOST}:{HTTP_PORT}/?{TOKEN_QUERY}={token()}",
            f"             ws://{HOST}:{WS_PORT}/?{TOKEN_QUERY}={token()}",
            "             loopback only; the token is new for every launch.",
            "============================",
        ]
        if handshake:
            lines.append(HANDSHAKE_PREFIX + json.dumps({
                "http": HTTP_PORT, "ws": WS_PORT,
                "token": token(), "pid": os.getpid(),
            }))
        try:
            out.write("\n".join(lines) + "\n")
            out.flush()
        except Exception:
            pass

    def _run_ws_loop(self, ready: threading.Event) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._ws_loop = loop
        try:
            self._ws_server = loop.run_until_complete(
                websockets.serve(self._ws_handler, HOST, WS_PORT))
            ready.set()
            loop.run_forever()
        except Exception as exc:
            print(f"[api] websocket server failed: {exc}")
            ready.set()
        finally:
            loop.close()

    def stop(self) -> None:
        self._stopping = True
        try:
            self._unsubscribe()
        except Exception:
            pass
        self.frames.clear()

        if self._server is not None:
            self._server.shutdown()
        if self._http_thread is not None:
            self._http_thread.join(SHUTDOWN_TIMEOUT)
            if self._http_thread.is_alive():
                print("[api] HTTP thread did not stop within "
                      f"{SHUTDOWN_TIMEOUT:.0f}s; abandoning it")

        loop = self._ws_loop
        if loop is not None and not loop.is_closed():
            async def close_ws():
                for socket in list(self._clients):
                    try:
                        await socket.close(1001, "shutting down")
                    except Exception:
                        pass
                if self._ws_server is not None:
                    self._ws_server.close()
                    await self._ws_server.wait_closed()

            try:
                future = asyncio.run_coroutine_threadsafe(close_ws(), loop)
                future.result(SHUTDOWN_TIMEOUT)
            except Exception:
                pass
            loop.call_soon_threadsafe(loop.stop)
        if self._ws_thread is not None:
            self._ws_thread.join(SHUTDOWN_TIMEOUT)
            if self._ws_thread.is_alive():
                print("[api] websocket thread did not stop within "
                      f"{SHUTDOWN_TIMEOUT:.0f}s; abandoning it")
        self._ws_loop = None


_api: ControlApi | None = None


def api() -> ControlApi:
    global _api
    if _api is None:
        _api = ControlApi()
    return _api


def start(handshake: bool = False) -> ControlApi:
    instance = api()
    instance.start(handshake=handshake)
    return instance


def stop() -> None:
    if _api is not None:
        _api.stop()


def notify_status() -> None:
    if _api is not None:
        _api.notify_status()


def notify_change(tree: str, changed: dict) -> None:
    if _api is not None:
        _api.notify_change(tree, changed)


def notice(body: str, title: str = "", kind: str = "info", modal: bool = False) -> None:
    if _api is None:
        _pending_notices.append({"type": "notice", "kind": kind, "title": title,
                                 "body": body, "modal": modal})
        return
    _api.notice(body, title=title, kind=kind, modal=modal)
