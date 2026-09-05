import itertools
import queue
import threading

from utils import metrics


ORT_PRIORITY_HAND = 0
ORT_PRIORITY_FACE = 10

_PRIORITY_NAMES = {ORT_PRIORITY_HAND: "hand", ORT_PRIORITY_FACE: "face"}


class _OrtRunScheduler:
    def __init__(self):
        self._queue = queue.PriorityQueue()
        self._counter = itertools.count()
        self._worker = threading.Thread(
            target=self._worker_loop, daemon=True, name="OrtRunScheduler"
        )
        self._worker.start()

    def run(self, session, output_names, input_feed, priority):
        tag = _PRIORITY_NAMES.get(priority, str(priority))
        if "DmlExecutionProvider" not in session.get_providers():
            t = metrics.now()
            try:
                return session.run(output_names, input_feed)
            finally:
                metrics.observe("ort.%s.run_cpu" % tag, metrics.now() - t)

        done = threading.Event()
        request = {
            "session": session,
            "output_names": output_names,
            "input_feed": input_feed,
            "done": done,
            "result": None,
            "error": None,
            "tag": tag,
            "queued_at": metrics.now(),
        }
        self._queue.put((priority, next(self._counter), request))
        done.wait()
        metrics.observe("ort.%s.total" % tag, metrics.now() - request["queued_at"])
        if request["error"] is not None:
            raise request["error"]
        return request["result"]

    def _worker_loop(self):
        while True:
            _, _, request = self._queue.get()
            tag = request["tag"]
            started = metrics.now()
            metrics.observe("ort.%s.queue_wait" % tag, started - request["queued_at"])
            try:
                request["result"] = request["session"].run(
                    request["output_names"], request["input_feed"]
                )
            except Exception as exc:
                request["error"] = exc
            finally:
                metrics.observe("ort.%s.run_dml" % tag, metrics.now() - started)
                request["done"].set()
                self._queue.task_done()


_ORT_RUN_SCHEDULER = _OrtRunScheduler()


def run_ort(session, output_names, input_feed, priority=ORT_PRIORITY_FACE):
    return _ORT_RUN_SCHEDULER.run(session, output_names, input_feed, priority)
