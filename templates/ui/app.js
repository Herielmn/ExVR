import { PANES, SIDEBAR, DEFAULTS } from "/ui/spec.js";
import { openAdvanced } from "/ui/advanced.js";
import { menuControl, syncMenu, closeAnyMenu } from "/ui/menu.js";
import { drawQr } from "/ui/qr.js";
import { mountQt, unmountQt, syncQt } from "/ui/qt.js";

const cookieToken = () =>
  (document.cookie.match(/(?:^|;\s*)exvr_api=([^;]*)/) || [])[1];
export const token = new URLSearchParams(location.search).get("k")
  || (cookieToken() && decodeURIComponent(cookieToken()));
if (location.search) history.replaceState(null, "", location.pathname);

export const auth = { "X-ExVR-Token": token, "Content-Type": "application/json" };

const hostSend = (message) => window.ipc && window.ipc.postMessage(message);
if (window.ipc) document.documentElement.classList.add("hosted");

const state = {
  socket: null,
  trees: {},
  writable: new Set(),
  topology: null,
  metrics: null,
  choices: {},
  commands: {},
  restart: new Set(),
  status: {},
  pairing: null,
  pane: PANES[0].id,
  lang: 0,
  dirty: new Set(),
};

const $ = (id) => document.getElementById(id);
const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

export const log = (...parts) => {
  const box = $("log");
  box.textContent += parts.join(" ") + "\n";
  box.scrollTop = box.scrollHeight;
};

let toastTimer = null;
export function toast(message) {
  let node = $("toast");
  if (!node) {
    node = el("div", "");
    node.id = "toast";
    node.setAttribute("role", "status");
    document.body.append(node);
  }
  node.textContent = message;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.remove(), 3200);
}

const BUSY_LIMIT = 180000;
let busyVeil = null;
let busyTimer = null;
let busyReturn = null;

export function holdBusy(label) {
  if (busyVeil) {
    busyVeil.querySelector(".status").textContent = label;
    return;
  }
  const veil = el("div", document.querySelector(".sheet-backdrop") ? "instant" : "");
  veil.id = "busy-veil";
  veil.tabIndex = -1;
  veil.setAttribute("aria-busy", "true");
  const status = el("div", "status", label);
  status.setAttribute("role", "status");
  veil.append(status);
  veil.addEventListener("keydown", (event) => {
    if (event.key === "Tab") event.preventDefault();
  });
  busyReturn = document.activeElement;
  document.body.append(veil);
  busyVeil = veil;
  veil.focus();
  clearTimeout(busyTimer);
  busyTimer = setTimeout(() => {
    dropBusy();
    toast(state.lang ? "还没有回音，界面已解除锁定"
                     : "No word back yet; the window is usable again");
  }, BUSY_LIMIT);
  showDriver();
  syncQt();
}

export function dropBusy(instant = false) {
  const veil = busyVeil;
  const back = busyReturn;
  busyVeil = null;
  busyReturn = null;
  clearTimeout(busyTimer);
  busyTimer = null;
  if (!veil) return;
  if (instant) veil.remove();
  else dismiss(veil);
  showDriver();
  syncQt();
  if (back && back.focus && back.isConnected) back.focus();
}

const THEMES = ["system", "light", "dark"];
const THEME_LABEL = {
  system: ["System", "跟随系统"],
  light: ["Light", "浅色"],
  dark: ["Dark", "深色"],
};
const SKIN = "qt";
const SKIN_ON_LABEL = ["Windchime Moonshadow", "风铃月影"];
const SKIN_OFF_LABEL = ["Default window", "默认界面"];
const APP_WINDOW = [1120, 740, 880, 600];
const SKIN_WINDOW = [0.3, 0.65, 600, 800];
const prefersDark = window.matchMedia("(prefers-color-scheme: dark)");

let themeBase = "system";
let skinOn = false;

function stored(key) {
  try {
    return localStorage.getItem(key) || "";
  } catch (error) {
    return "";
  }
}

function remember(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch (error) {
  }
}

function resolveTheme() {
  const choice = skinOn ? SKIN : themeBase;
  document.documentElement.dataset.theme = choice;
  const dark = choice === "dark" || (choice === "system" && prefersDark.matches);
  document.documentElement.dataset.themeResolved = dark ? "dark" : "light";
  const button = $("theme");
  if (button) button.title = THEME_LABEL[themeBase][state.lang];
  const toggle = $("skin");
  if (toggle) {
    const label = (skinOn ? SKIN_OFF_LABEL : SKIN_ON_LABEL)[state.lang];
    toggle.title = label;
    toggle.setAttribute("aria-label", label);
    toggle.setAttribute("aria-pressed", skinOn ? "true" : "false");
  }
  document.querySelectorAll("[data-theme-choice]").forEach((node) => {
    node.value = themeBase;
    syncMenu(node);
  });
}

function applyQt(rebuild = false) {
  if (!skinOn || rebuild) unmountQt();
  if (skinOn && state.trees.config) mountQt(context());
}

function sizeHost() {
  const [wide, tall, least, low] = skinOn ? SKIN_WINDOW : APP_WINDOW;
  const width = skinOn ? Math.max(least, Math.round(screen.availWidth * wide)) : wide;
  const height = skinOn ? Math.max(low, Math.round(screen.availHeight * tall)) : tall;
  hostSend(`${skinOn ? "size" : "size-back"}:${width}x${height}:${least}x${low}`);
}

export function setTheme(choice) {
  themeBase = THEMES.includes(choice) ? choice : "system";
  remember("exvr.theme", themeBase);
  resolveTheme();
}

export function setSkin(on) {
  if (Boolean(on) === skinOn) return;
  skinOn = !skinOn;
  remember("exvr.skin", skinOn ? SKIN : "");
  sizeHost();
  resolveTheme();
  applyQt();
}

function restoreTheme() {
  themeBase = stored("exvr.theme") || "system";
  skinOn = stored("exvr.skin") === SKIN;
  if (themeBase === SKIN) {
    themeBase = "system";
    skinOn = true;
    remember("exvr.theme", themeBase);
    remember("exvr.skin", SKIN);
  }
  if (!THEMES.includes(themeBase)) themeBase = "system";
  resolveTheme();
  if (skinOn) sizeHost();
}

prefersDark.addEventListener("change", resolveTheme);

function send(message) {
  if (state.socket && state.socket.readyState === WebSocket.OPEN) {
    state.socket.send(JSON.stringify(message));
    return true;
  }
  return false;
}

export function patch(path, value, tree = "config") {
  const parts = path.split("/");
  const delta = {};
  let node = delta;
  parts.forEach((key, index) => {
    if (index === parts.length - 1) node[key] = value;
    else node = (node[key] = {});
  });
  if (!send({ type: "patch", tree, delta })) {
    fetch(`/api/tree/${tree}`, { method: "PATCH", headers: auth, body: JSON.stringify(delta) })
      .then((response) => response.json())
      .then((body) => { if (body.rejected) log("rejected:", JSON.stringify(body.rejected)); });
  }
}

export function command(name, args) {
  if (!send({ type: "command", name, args })) {
    fetch(`/api/command/${name}`, { method: "POST", headers: auth,
                                    body: JSON.stringify(args || {}) })
      .then((response) => response.json())
      .then((body) => body.error && log("command", name, "failed:", body.error));
  }
}

const pendingPatches = new Map();
let patchFrame = null;

export function flushPatches() {
  if (patchFrame !== null) cancelAnimationFrame(patchFrame);
  patchFrame = null;
  for (const [path, value] of pendingPatches) patch(path, value);
  pendingPatches.clear();
}

export function patchSoon(path, value) {
  pendingPatches.set(path, value);
  if (patchFrame === null) patchFrame = requestAnimationFrame(flushPatches);
}

function dismiss(backdrop, after) {
  backdrop.classList.add("closing");
  let done = false;
  const finish = () => {
    if (done) return;
    done = true;
    backdrop.remove();
    if (after) after();
  };
  backdrop.addEventListener("animationend", finish);
  setTimeout(finish, 600);
}

export function ask({ title, body, confirm, destructive, busy }) {
  return dialog({ title, body, confirm, destructive, busy, question: true });
}

export function note({ title, body, danger }) {
  return dialog({ title, body, confirm: state.lang ? "好" : "OK",
                  destructive: false, danger, question: false });
}

function showNotice(notice) {
  if (notice.kind === "error" || notice.modal) {
    note({ title: notice.title, body: notice.body, danger: notice.kind === "error" });
  } else {
    toast(notice.title ? `${notice.title}：${notice.body}` : notice.body);
  }
}

function dialog({ title, body, confirm, destructive, danger, question, busy }) {
  return new Promise((resolve) => {
    const backdrop = el("div", "sheet-backdrop centred");
    if (busyVeil) backdrop.classList.add("handoff");
    const sheet = el("section", "sheet compact");
    sheet.role = question ? "dialog" : "alertdialog";
    sheet.setAttribute("aria-modal", "true");
    sheet.tabIndex = -1;

    const header = el("header");
    const heading = el("h2", "", title);
    header.append(heading);
    const content = el("div", "body");
    content.append(el("p", danger ? "danger" : "", body));
    const footer = el("footer");
    const cancel = question
      ? el("button", "button small", state.lang ? "取消" : "Cancel") : null;
    const go = el("button", "button small" + (destructive ? " destructive" : " primary"),
                 confirm);
    if (cancel) footer.append(cancel);
    footer.append(go);
    sheet.append(header, content, footer);
    backdrop.append(sheet);

    const restore = document.activeElement === busyVeil
      ? busyReturn : document.activeElement;
    const settle = (answer) => {
      document.removeEventListener("keydown", onKey);
      if (answer && busy) {
        holdBusy(busy);
        backdrop.classList.add("handoff-out");
      }
      dismiss(backdrop, () => {
        if (restore && restore.focus) restore.focus();
        resolve(answer);
      });
    };
    function onKey(event) {
      if (event.key === "Escape") { event.preventDefault(); settle(!question); return; }
      if (event.key !== "Tab") return;
      const first = cancel || go;
      const last = go;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    if (cancel) cancel.onclick = () => settle(false);
    go.onclick = () => settle(true);
    if (question) {
      backdrop.onclick = (event) => { if (event.target === backdrop) settle(false); };
    }
    document.addEventListener("keydown", onKey);
    document.body.append(backdrop);
    if (backdrop.classList.contains("handoff")) dropBusy(true);
    (cancel || go).focus();
  });
}

export async function whileBusy(button, work) {
  if (button.classList.contains("busy")) return;
  button.classList.add("busy");
  try {
    return await work();
  } finally {
    button.classList.remove("busy");
  }
}

export function at(tree, path) {
  return path.split("/").reduce((node, key) => (node == null ? node : node[key]), tree);
}

const text = (pair) => (Array.isArray(pair) ? pair[state.lang] || pair[0] : pair || "");
let nextId = 0;

function labelFor(spec, control) {
  const label = el("label", "label");
  if (control && control.id) label.htmlFor = control.id;
  label.append(el("span", "title", text(spec.t)));
  if (spec.detail) label.append(el("span", "detail", text(spec.detail)));
  if (spec.path && state.restart.has("config/" + spec.path)) {
    label.append(el("span", "badge warn",
                    state.lang ? " 需重启追踪" : " restart"));
  }
  return label;
}

const SVG = "http://www.w3.org/2000/svg";

function undoGlyph() {
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("viewBox", "0 0 16 16");
  svg.setAttribute("aria-hidden", "true");
  for (const d of ["M2 8a6 6 0 1 0 6-6 6.4 6.4 0 0 0-4.5 1.85L2 5.4",
                   "M2 2v3.4h3.4"]) {
    const path = document.createElementNS(SVG, "path");
    path.setAttribute("d", d);
    svg.append(path);
  }
  return svg;
}

function atDefault(path, value) {
  const factory = DEFAULTS[path];
  return factory !== undefined && Math.abs(Number(value) - factory) < 1e-9;
}

function resetButton(spec, write) {
  if (!(spec.path in DEFAULTS)) return null;
  const factory = DEFAULTS[spec.path];
  const button = el("button", "reset");
  button.type = "button";
  button.dataset.reset = spec.path;
  const label = state.lang ? `恢复默认值（${factory}）` : `Restore the default (${factory})`;
  button.title = label;
  button.setAttribute("aria-label", label);
  button.append(undoGlyph());
  button.onclick = () => write(factory);
  return button;
}

function syncReset(node) {
  const row = node.closest(".row");
  const button = row && row.querySelector(`.reset[data-reset="${node.dataset.path}"]`);
  if (button) button.disabled = atDefault(node.dataset.path, node.value);
}

function makeSwitch(spec) {
  const row = el("div", "row");
  const box = el("span", "switch");
  const input = el("input");
  input.type = "checkbox";
  input.id = `c${nextId++}`;
  input.dataset.path = spec.path;
  input.checked = Boolean(at(state.trees.config, spec.path));
  input.onchange = () => patch(spec.path, input.checked);
  box.append(input, el("span", "track"), el("span", "thumb"));
  row.append(labelFor(spec, input), box);
  return row;
}

function makeSlider(spec) {
  const row = el("div", "row");
  const wrap = el("div", "slider");
  const input = el("input");
  input.type = "range";
  input.id = `c${nextId++}`;
  input.dataset.path = spec.path;
  input.min = spec.min;
  input.max = spec.max;
  input.step = spec.step;
  const readout = el("span", "value");
  const apply = (value) => {
    input.value = value;
    show(value);
    state.dirty.delete(spec.path);
    patch(spec.path, value);
    if (spec.mirror) patch(spec.mirror, spec.negate ? -value : value);
  };
  const reset = resetButton(spec, apply);
  const show = (value) => {
    readout.textContent = Number(value).toFixed(spec.digits);
    if (reset) reset.disabled = atDefault(spec.path, value);
  };
  input.value = at(state.trees.config, spec.path);
  show(input.value);
  input.oninput = () => {
    state.dirty.add(spec.path);
    show(input.value);
    const value = Number(input.value);
    patchSoon(spec.path, value);
    if (spec.mirror) patchSoon(spec.mirror, spec.negate ? -value : value);
  };
  input.onchange = () => {
    flushPatches();
    state.dirty.delete(spec.path);
  };
  wrap.append(input, readout);
  row.append(labelFor(spec, input), wrap);
  if (reset) row.append(reset);
  return row;
}

function makeNumber(spec) {
  const row = el("div", "row");
  const input = el("input");
  input.type = "number";
  input.className = "field number";
  input.id = `c${nextId++}`;
  input.dataset.path = spec.path;
  if (spec.min !== undefined) input.min = spec.min;
  if (spec.max !== undefined) input.max = spec.max;
  if (spec.step !== undefined) input.step = spec.step;
  input.value = at(state.trees.config, spec.path);
  const reset = resetButton(spec, (value) => {
    input.value = value;
    reset.disabled = true;
    patch(spec.path, value);
  });
  if (reset) reset.disabled = atDefault(spec.path, input.value);
  input.onchange = () => {
    patch(spec.path, Number(input.value));
    if (reset) reset.disabled = atDefault(spec.path, input.value);
  };
  row.append(labelFor(spec, input), input);
  if (spec.unit) row.append(el("span", "value", spec.unit));
  if (reset) row.append(reset);
  return row;
}

function makeText(spec) {
  const row = el("div", "row stacked");
  const input = el("input");
  input.type = "text";
  input.className = "field grow";
  input.id = `c${nextId++}`;
  input.dataset.path = spec.path;
  input.value = at(state.trees.config, spec.path) ?? "";
  if (spec.placeholder) input.placeholder = text(spec.placeholder);
  input.onchange = () => patch(spec.path, input.value);
  row.append(labelFor(spec, input), input);
  return row;
}

function makeMenu(spec) {
  const row = el("div", "row");
  const select = el("select", "menu");
  select.id = `c${nextId++}`;
  select.dataset.path = spec.path;
  const options = state.choices[spec.choices] || [];
  for (const [value, label] of options) {
    const option = el("option", "", text(label));
    option.value = JSON.stringify(value);
    select.append(option);
  }
  select.value = JSON.stringify(at(state.trees.config, spec.path));
  if (select.selectedIndex < 0) {
    const stored = at(state.trees.config, spec.path);
    const option = el("option", "", `${stored} (?)`);
    option.value = JSON.stringify(stored);
    select.append(option);
    select.value = option.value;
  }
  select.onchange = () => patch(spec.path, JSON.parse(select.value));
  const label = labelFor(spec, select);
  row.append(label, menuControl(select, text(spec.t)));
  return row;
}

function makeButtons(spec) {
  const row = el("div", "row buttons");
  for (const entry of spec.buttons) {
    const button = el("button", "button small", text(entry.t));
    button.onclick = () => command(entry.command, entry.args);
    row.append(button);
  }
  return row;
}

const CUSTOM = {
  "camera-device": (spec) => {
    const row = el("div", "row");
    const select = el("select", "menu");
    select.id = `c${nextId++}`;
    select.dataset.custom = "camera-device";
    for (const [index, name] of state.choices.camera_device || []) {
      const option = el("option", "", name);
      option.value = String(index);
      select.append(option);
    }
    if (!select.options.length) {
      select.append(el("option", "", state.lang ? "未检测到摄像头" : "No camera found"));
      select.disabled = true;
    }
    if (state.choices.camera_selected != null) {
      select.value = String(state.choices.camera_selected);
    }
    select.onchange = () => command("select_camera", {
      index: Number(select.value),
      name: select.options[select.selectedIndex].textContent,
    });
    const refresh = el("button", "button small", state.lang ? "重新扫描" : "Rescan");
    refresh.onclick = () => whileBusy(refresh, async () => {
      await loadChoices();
      render();
      toast(state.lang ? "已重新扫描摄像头" : "Rescanned cameras");
    });
    const label = labelFor(spec, select);
    row.append(label, menuControl(select, text(spec.t)), refresh);
    return row;
  },

  resolution: (spec) => {
    const row = el("div", "row");
    const value = el("span", "value tabular");
    value.dataset.custom = "resolution";
    value.style.width = "auto";
    row.append(labelFor(spec, null), value);
    showResolution(value);
    return row;
  },

  theme: (spec) => {
    const row = el("div", "row");
    const select = el("select", "menu");
    select.id = `c${nextId++}`;
    select.dataset.themeChoice = "1";
    for (const choice of THEMES) {
      const option = el("option", "", THEME_LABEL[choice][state.lang]);
      option.value = choice;
      select.append(option);
    }
    select.value = document.documentElement.dataset.theme || "system";
    select.onchange = () => setTheme(select.value);
    const label = labelFor(spec, select);
    row.append(label, menuControl(select, text(spec.t)));
    return row;
  },
};

CUSTOM.pairing = () => {
  const wrap = el("div", "");
  const codeRow = el("div", "row");
  const label = el("div", "label");
  label.append(el("span", "detail", state.lang ? "配对码" : "Pairing code"));
  const code = el("span", "code");
  code.dataset.custom = "pairing-code";
  code.textContent = "--------";
  label.append(code);
  const rotate = el("button", "button small", state.lang ? "更换" : "Rotate");
  rotate.onclick = async () => {
    const yes = await ask({
      title: state.lang ? "更换配对码？" : "Rotate the pairing code?",
      body: state.lang
        ? "已经扫码连上的手机会立刻断开，需要重新扫一次新的二维码。"
        : "Phones that already paired are dropped and have to scan the new code.",
      confirm: state.lang ? "更换" : "Rotate",
      destructive: true,
    });
    if (!yes) return;
    await whileBusy(rotate, async () => {
      const response = await fetch("/api/pairing/rotate", { method: "POST", headers: auth });
      state.pairing = await response.json();
      renderPairing(wrap);
    });
    toast(state.lang ? "配对码已更换，已连接的手机需重新扫码"
                     : "Rotated; paired phones must scan again");
  };
  codeRow.append(label, rotate);

  const qrRow = el("div", "row stacked");
  const canvas = el("canvas", "qr");
  canvas.dataset.custom = "pairing-qr";
  canvas.width = canvas.height = 148;
  qrRow.append(canvas);

  const urlRow = el("div", "row stacked");
  const urls = el("ul", "urls");
  urls.dataset.custom = "pairing-urls";
  urlRow.append(el("span", "detail", state.lang
    ? "手机与电脑连同一个 Wi-Fi，然后打开：" : "Same Wi-Fi as this PC, then open:"), urls);

  wrap.append(codeRow, qrRow, urlRow);
  renderPairing(wrap);
  return wrap;
};

function renderPairing(root) {
  const info = state.pairing;
  const code = root.querySelector('[data-custom="pairing-code"]');
  const canvas = root.querySelector('[data-custom="pairing-qr"]');
  const urls = root.querySelector('[data-custom="pairing-urls"]');
  if (!info) return;
  code.textContent = info.code;
  urls.textContent = "";
  for (const url of info.urls) urls.append(el("li", "", url));
  const primary = info.urls.find((url) => !url.includes("127.0.0.1")) || info.urls[0];
  if (primary) drawQr(canvas, primary);
}

CUSTOM.driver = () => {
  const wrap = el("div", "");
  const status = el("div", "row");
  const pill = el("span", "pill");
  pill.dataset.custom = "steamvr";
  pill.append(el("span", "dot"), el("span", "text", "..."));
  status.append(el("div", "label", state.lang ? "SteamVR" : "SteamVR"), pill);

  const buttons = el("div", "row buttons");
  const install = el("button", "button small");
  install.dataset.custom = "driver-button";
  install.textContent = "...";
  install.onclick = async () => {
    const installed = Boolean(state.status.driver_installed);
    const label = installed
      ? (state.lang ? "正在卸载驱动…" : "Removing the driver...")
      : (state.lang ? "正在写入驱动…" : "Writing the driver...");
    if (installed) {
      const yes = await ask({
        title: state.lang ? "卸载 VMT / VRto3D 驱动？" : "Uninstall the VMT / VRto3D driver?",
        body: state.lang
          ? "删除后 ExVR 的追踪功能将不再工作。"
          : "ExVR's tracking will not work any more once these are removed.",
        confirm: state.lang ? "卸载" : "Uninstall",
        destructive: true,
        busy: label,
      });
      if (!yes) return;
    } else {
      holdBusy(label);
    }
    command("install_components");
  };
  buttons.append(install);
  wrap.append(status, buttons);
  showDriver(wrap);
  return wrap;
};

CUSTOM.diagnostics = () => {
  const wrap = el("div", "");
  const metrics = el("div", "row");
  const metricsPill = el("span", "pill");
  metricsPill.dataset.custom = "metrics-state";
  metricsPill.append(el("span", "dot"), el("span", "text", "..."));
  metrics.append(el("div", "label", state.lang ? "性能指标" : "Metrics"), metricsPill);

  const logRow = el("div", "row stacked");
  const path = el("span", "detail");
  path.dataset.custom = "log-path";
  path.style.wordBreak = "break-all";
  logRow.append(el("span", "detail", state.lang ? "日志" : "Log file"), path);

  const buttons = el("div", "row buttons");
  const bundle = el("button", "button small", state.lang ? "打包诊断信息" : "Diagnostics bundle");
  bundle.onclick = () => whileBusy(bundle, downloadBundle);
  const advanced = el("button", "button small quiet", state.lang ? "高级…" : "Advanced...");
  advanced.onclick = () => openAdvanced(context());
  buttons.append(bundle, advanced);

  wrap.append(metrics, logRow, buttons);
  showDiagnostics(wrap);
  return wrap;
};

const RELEASES = "https://github.com/Herielmn/ExVR-Next/releases";

CUSTOM.about = () => {
  const wrap = el("div", "about");

  const versionRow = el("div", "row");
  const version = el("span", "value tabular");
  version.dataset.custom = "about-version";
  version.style.width = "auto";
  versionRow.append(el("div", "label", state.lang ? "版本" : "Version"), version);

  const linkRow = el("div", "row stacked");
  linkRow.append(el("span", "detail", state.lang
    ? "仍在测试中。"
    : "Still in testing."));
  const list = el("ul", "urls");
  list.append(el("li", "", RELEASES));
  linkRow.append(list);

  const buttons = el("div", "row buttons");
  const copy = el("button", "button small", state.lang ? "复制链接" : "Copy link");
  copy.onclick = async () => {
    try {
      await navigator.clipboard.writeText(RELEASES);
      toast(state.lang ? "已复制" : "Copied");
    } catch (error) {
      toast(state.lang ? "复制失败，请手动选中上面的地址" : "Select the address above instead");
    }
  };
  buttons.append(copy);

  const notice = el("p", "note", state.lang
    ? "ExVR-Next 基于 xiaofeiyu0723 的 ExVR，以 GPL-3.0 发布，不提供任何担保。"
    : "ExVR-Next is based on ExVR by xiaofeiyu0723, released under GPL-3.0, "
      + "with no warranty of any kind.");

  wrap.append(versionRow, linkRow, buttons, notice);
  showAbout(wrap);
  return wrap;
};

function showResolution(node) {
  const target = node || document.querySelector('[data-custom="resolution"]');
  if (!target || !state.trees.config) return;
  const setting = state.trees.config.Setting;
  target.textContent = `${setting.camera_width} × ${setting.camera_height}`
    + ` · ${setting.camera_fps} fps`;
}

const ASPECT_RATIOS = { "16:9": "16 / 9", "4:3": "4 / 3", "1:1": "1 / 1" };

function showAspect() {
  const setting = state.trees.config && state.trees.config.Setting;
  const viewport = document.querySelector(".viewport");
  if (!setting || !viewport) return;
  viewport.style.setProperty("--preview-aspect",
                             ASPECT_RATIOS[setting.camera_aspect] || ASPECT_RATIOS["4:3"]);
}

function showDriver(root) {
  const scope = root || document;
  const pill = scope.querySelector('[data-custom="steamvr"]');
  const button = scope.querySelector('[data-custom="driver-button"]');
  if (!pill) return;
  const installed = state.status.steamvr;
  const driver = state.status.driver_installed;
  pill.className = "pill " + (installed ? (driver ? "on" : "warn") : "off");
  pill.querySelector(".text").textContent = installed
    ? (driver ? (state.lang ? "驱动已安装" : "Driver installed")
              : (state.lang ? "未安装驱动" : "Driver missing"))
    : (state.lang ? "未安装 SteamVR" : "SteamVR not found");
  button.textContent = driver
    ? (state.lang ? "卸载驱动" : "Uninstall driver")
    : (state.lang ? "安装驱动" : "Install driver");
  button.className = "button small" + (driver ? " destructive" : " tinted");
  button.disabled = !installed || Boolean(busyVeil);
}

function showDiagnostics(root) {
  const scope = root || document;
  const pill = scope.querySelector('[data-custom="metrics-state"]');
  if (!pill) return;
  const on = Boolean(state.status.metrics_enabled);
  pill.className = "pill " + (on ? "on" : "");
  pill.querySelector(".text").textContent = on
    ? (state.lang ? "开启" : "On")
    : (state.lang ? "关闭（settings/metrics.on 开启）" : "Off (touch settings/metrics.on)");
  scope.querySelector('[data-custom="log-path"]').textContent = state.status.log || "";
}

function showAbout(root) {
  const scope = root || document;
  const version = scope.querySelector('[data-custom="about-version"]');
  if (!version) return;
  version.textContent = state.status.version || "";
}

async function downloadBundle() {
  const response = await fetch("/api/diagnostics", { method: "POST", headers: auth });
  const blob = await response.blob();
  const named = (response.headers.get("Content-Disposition") || "").match(/"(.+)"/);
  const link = el("a");
  link.href = URL.createObjectURL(blob);
  link.download = named ? named[1] : "exvr-diagnostics.zip";
  link.click();
  URL.revokeObjectURL(link.href);
  toast(`${link.download} · ${(blob.size / 1024).toFixed(0)} KiB`);
}

const MAKERS = { switch: makeSwitch, slider: makeSlider, number: makeNumber,
                 text: makeText, menu: makeMenu, buttons: makeButtons };

function renderGroups(host, groups) {
  for (const group of groups) {
    const block = el("div", "group");
    if (group.t) block.append(el("h2", "", text(group.t)));
    const card = el("div", "card");
    for (const row of group.rows) {
      const make = row.kind === "custom" ? CUSTOM[row.id] : MAKERS[row.kind];
      if (!make) { log("no renderer for", row.kind, row.id || row.path); continue; }
      card.append(make(row));
    }
    block.append(card);
    if (group.note) block.append(el("p", "note", text(group.note)));
    host.append(block);
  }
}

function renderPanes() {
  const tabs = $("segments");
  const host = $("panes");
  tabs.textContent = "";
  host.textContent = "";
  tabs.append(el("div", "indicator"));
  for (const pane of PANES) {
    const tab = el("button", "", text(pane.t));
    tab.role = "tab";
    tab.dataset.pane = pane.id;
    tab.setAttribute("aria-selected", String(pane.id === state.pane));
    tab.setAttribute("aria-controls", `pane-${pane.id}`);
    tab.onclick = () => selectPane(pane.id);
    tabs.append(tab);

    const section = el("section", "pane");
    section.id = `pane-${pane.id}`;
    section.role = "tabpanel";
    section.hidden = pane.id !== state.pane;
    renderGroups(section, pane.groups);
    host.append(section);
  }
  moveIndicator(false);
}

function renderSidebar() {
  const host = $("stage-controls");
  host.textContent = "";
  renderGroups(host, SIDEBAR);
}

function render() {
  renderPanes();
  renderSidebar();
  resolveTheme();
  applyQt(true);
}

function moveIndicator(animate = true) {
  const tabs = $("segments");
  const indicator = tabs.querySelector(".indicator");
  const seat = tabs.querySelector('[aria-selected="true"]');
  if (!indicator || !seat) return;
  const strip = tabs.getBoundingClientRect();
  const box = seat.getBoundingClientRect();
  if (!animate) indicator.classList.add("settling");
  indicator.style.setProperty("--x", `${Math.round(box.left - strip.left)}px`);
  indicator.style.setProperty("--w", `${Math.round(box.width)}px`);
  if (!animate) {
    requestAnimationFrame(() => indicator.classList.remove("settling"));
  }
}

function selectPane(id) {
  if (id === state.pane) return;
  const from = PANES.findIndex((pane) => pane.id === state.pane);
  const to = PANES.findIndex((pane) => pane.id === id);
  const direction = to > from ? "forward" : "back";
  state.pane = id;
  closeAnyMenu();
  for (const tab of $("segments").querySelectorAll("[data-pane]")) {
    tab.setAttribute("aria-selected", String(tab.dataset.pane === id));
  }
  for (const pane of PANES) {
    const section = $(`pane-${pane.id}`);
    if (!section) continue;
    delete section.dataset.enter;
    section.hidden = pane.id !== id;
    if (pane.id !== id) continue;
    section.dataset.enter = direction;
    section.addEventListener("animationend",
                             () => { delete section.dataset.enter; }, { once: true });
  }
  $("panes").scrollTop = 0;
  moveIndicator();
}

function reflect(path, value, tree = "config") {
  if (state.dirty.has(path)) return;
  for (const node of document.querySelectorAll(`[data-path="${path}"]`)) {
    if (node.dataset.tree && node.dataset.tree !== tree) continue;
    if (node.type === "checkbox") node.checked = Boolean(value);
    else if (node.tagName === "SELECT") {
      node.value = JSON.stringify(value);
      syncMenu(node);
    } else node.value = value;
    if (node.type === "range") {
      const readout = node.parentElement.querySelector(".value");
      if (readout) readout.textContent = Number(value).toFixed(digitsFor(path));
    }
    if (node.dataset.path) syncReset(node);
  }
  if (path.startsWith("Setting/camera_")) {
    showResolution();
    showAspect();
  }
  syncQt();
}

const DIGITS = new Map();
for (const pane of PANES) {
  for (const group of pane.groups) {
    for (const row of group.rows) {
      if (row.kind === "slider") DIGITS.set(row.path, row.digits);
    }
  }
}
const digitsFor = (path) => (DIGITS.has(path) ? DIGITS.get(path) : 2);

let wasTracking = false;

function setStatus(status) {
  state.status = status;
  const tracking = Boolean(status.tracking);
  if (wasTracking && !tracking) setPreview(false);
  wasTracking = tracking;
  const trackingPill = $("pill-tracking");
  trackingPill.className = "pill " + (tracking ? "on" : "off");
  trackingPill.querySelector(".text").textContent = tracking
    ? (state.lang ? "追踪中" : "Tracking")
    : (state.lang ? "已停止" : "Stopped");
  const fps = $("pill-fps");
  fps.hidden = !tracking;
  fps.querySelector(".text").textContent = `${status.fps} fps`;
  $("tracking-toggle").textContent = tracking
    ? (state.lang ? "停止追踪" : "Stop tracking")
    : (state.lang ? "开始追踪" : "Start tracking");
  $("version").hidden = false;
  $("version").textContent = status.version;
  $("viewport-message").textContent = tracking
    ? (state.lang ? "预览已关闭" : "Preview is off")
    : (state.lang ? "未在追踪" : "Not tracking");
  const shell = {
    recentre: ["Recentre", "全部归位"],
    reload: ["Reload", "重新载入"],
    save: ["Save", "保存"],
    advanced: ["Advanced", "高级"],
  };
  for (const [id, pair] of Object.entries(shell)) {
    $(id).textContent = pair[state.lang ? 1 : 0];
  }
  showPreviewButton();
  const chrome = {
    theme: ["Theme", "主题"],
    "win-min": ["Minimize", "最小化"],
    "win-max": ["Maximize", "最大化"],
    "win-close": ["Close", "关闭"],
  };
  for (const [id, pair] of Object.entries(chrome)) {
    const label = pair[state.lang ? 1 : 0];
    $(id).setAttribute("aria-label", label);
    $(id).title = label;
  }
  document.documentElement.lang = state.lang ? "zh-CN" : "en";
  $("video").alt = state.lang ? "摄像头预览" : "Camera preview";
  $("segments").setAttribute("aria-label", state.lang ? "分区" : "Sections");
  showDriver();
  showDiagnostics();
  showAbout();
  syncQt();
}

function setPreview(on) {
  const video = $("video");
  const placeholder = $("viewport-placeholder");
  if (on) {
    video.src = `/api/preview.mjpeg?k=${encodeURIComponent(token)}`;
    placeholder.hidden = true;
    send({ type: "subscribe", landmarks: true, metrics: true });
  } else {
    video.removeAttribute("src");
    placeholder.hidden = false;
    clearOverlay();
    send({ type: "subscribe", landmarks: false, metrics: true });
  }
  showPreviewButton();
}

function togglePreview() {
  setPreview(!$("video").getAttribute("src"));
}

function showPreviewButton() {
  const button = $("preview-toggle");
  const on = Boolean($("video").getAttribute("src"));
  button.textContent = on
    ? (state.lang ? "取消预览" : "Hide preview")
    : (state.lang ? "预览" : "Preview");
  button.classList.toggle("tinted", on);
  button.disabled = !state.status.tracking;
}

function clearOverlay() {
  const canvas = $("overlay");
  canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
}

const FACE_LINE = "rgb(52, 199, 89)";
const TONGUE_BOX = "rgb(255, 69, 58)";
const HAND_LINE = "rgb(255, 214, 10)";

function drawOverlay(frame) {
  const canvas = $("overlay");
  const context = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  context.clearRect(0, 0, w, h);
  if (!state.topology) return;

  context.lineWidth = 1;
  context.strokeStyle = FACE_LINE;
  for (const points of frame.faces || []) {
    context.beginPath();
    for (const [a, b] of state.topology.face_edges) {
      if (!points[a] || !points[b]) continue;
      context.moveTo(points[a][0] * w, points[a][1] * h);
      context.lineTo(points[b][0] * w, points[b][1] * h);
    }
    context.stroke();
    const box = state.topology.tongue_slots.map((i) => points[i]).filter(Boolean);
    if (box.length === 4) {
      const xs = box.map((p) => p[0] * w);
      const ys = box.map((p) => p[1] * h);
      context.strokeStyle = TONGUE_BOX;
      context.strokeRect(Math.min(...xs), Math.min(...ys),
                         Math.max(...xs) - Math.min(...xs),
                         Math.max(...ys) - Math.min(...ys));
      context.strokeStyle = FACE_LINE;
    }
  }

  context.lineWidth = 2;
  context.strokeStyle = HAND_LINE;
  context.fillStyle = HAND_LINE;
  for (const hand of frame.hands || []) {
    const points = hand.points;
    context.beginPath();
    for (const [a, b] of state.topology.hand_edges) {
      if (!points[a] || !points[b]) continue;
      context.moveTo(points[a][0] * w, points[a][1] * h);
      context.lineTo(points[b][0] * w, points[b][1] * h);
    }
    context.stroke();
    for (const point of points) {
      context.beginPath();
      context.arc(point[0] * w, point[1] * h, 3, 0, Math.PI * 2);
      context.fill();
    }
  }
}

export function context() {
  return { state, auth, patch, patchSoon, flushPatches, command, toast, log, el, text, at,
           ask, note, whileBusy, dismiss, holdBusy, hostSend, setTheme, setSkin,
           togglePreview,
           openAdvanced: () => openAdvanced(context()),
           reloadTree: (name) => reloadTree(name) };
}

async function reloadTree(name) {
  const response = await fetch(`/api/tree/${name}`, { headers: auth });
  const body = await response.json();
  state.trees[name] = body.value;
  return body.value;
}

async function loadChoices() {
  const response = await fetch("/api/choices", { headers: auth });
  state.choices = await response.json();
  return state.choices;
}

async function loadPairing() {
  const response = await fetch("/api/pairing", { headers: auth });
  state.pairing = await response.json();
  return state.pairing;
}

function connect(url) {
  const socket = new WebSocket(url);
  state.socket = socket;
  socket.onopen = () => send({ type: "subscribe", landmarks: false, metrics: true });
  socket.onclose = () => {
    dropBusy(true);
    $("viewport-message").textContent = state.lang
      ? "与核心的连接已断开" : "Lost the connection to the core";
    $("viewport-placeholder").hidden = false;
    setTimeout(() => connect(url), 1200);
  };
  socket.onmessage = (event) => {
    const message = JSON.parse(event.data);
    switch (message.type) {
      case "hello":
        state.topology = message.topology;
        state.restart = new Set(message.restart_required_paths);
        state.trees = message.trees;
        state.writable = new Set(message.writable || []);
        state.commands = message.commands;
        state.lang = languageIndex(state.trees.config);
        setStatus(message.status);
        render();
        showAspect();
        for (const notice of message.notices || []) showNotice(notice);
        break;
      case "landmarks":
        drawOverlay(message);
        break;
      case "metrics":
        state.metrics = message.series;
        setStatus(message.status);
        break;
      case "status":
      case "command":
        setStatus(message.status);
        break;
      case "notice":
        showNotice(message);
        break;
      case "applied":
      case "changed":
        for (const [path, change] of Object.entries(
            { ...message.changed, ...message.derived })) {
          if (state.trees[message.tree]) writeInto(state.trees[message.tree], path, change.to);
          reflect(path, change.to, message.tree);
          if (path === "Setting/language") relanguage();
        }
        if (message.restart_required && message.restart_required.length) {
          toast((state.lang ? "需重启追踪才生效：" : "Restart tracking to apply: ")
                + message.restart_required.join(", "));
        }
        break;
      case "reloaded":
        location.reload();
        break;
      case "rejected":
        log("rejected:", JSON.stringify(message.rejected));
        toast(state.lang ? "这个值被拒绝了" : "That value was refused");
        break;
      case "error":
        log("error:", message.error);
        break;
    }
  };
}

function writeInto(tree, path, value) {
  const parts = path.split("/");
  let node = tree;
  for (const key of parts.slice(0, -1)) {
    if (node == null) return;
    node = node[key];
  }
  if (node != null) node[parts[parts.length - 1]] = value;
}

function languageIndex(config) {
  const choice = (config && config.Setting && config.Setting.language) || "system";
  if (choice === "zh_CN") return 1;
  if (choice === "en") return 0;
  return /^zh\b/i.test(navigator.language || "") ? 1 : 0;
}

function relanguage() {
  state.lang = languageIndex(state.trees.config);
  document.documentElement.lang = state.lang ? "zh-CN" : "en";
  render();
  setStatus(state.status);
}

function wireShell() {
  const grip = $("grip");
  grip.addEventListener("mousedown", () => hostSend("drag"));
  grip.addEventListener("dblclick", () => hostSend("maximize"));
  $("win-min").onclick = () => hostSend("minimize");
  $("win-max").onclick = () => hostSend("maximize");
  $("win-close").onclick = () => hostSend("close");
  $("theme").onclick = () => {
    setTheme(THEMES[(THEMES.indexOf(themeBase) + 1) % THEMES.length]);
    toast(THEME_LABEL[themeBase][state.lang]);
  };
  $("skin").onclick = () => {
    setSkin(!skinOn);
    toast((skinOn ? SKIN_ON_LABEL : SKIN_OFF_LABEL)[state.lang]);
  };

  $("tracking-toggle").onclick = () => command("toggle_tracking");
  $("preview-toggle").onclick = togglePreview;
  $("recentre").onclick = () => {
    for (const name of ["reset_head", "reset_eyes", "reset_left_hand", "reset_right_hand"]) {
      command(name);
    }
    toast(state.lang ? "已重新居中" : "Recentred");
  };
  $("recentre").title = state.lang
    ? "头部、眼睛、左右手一起归位" : "Head, eyes and both hands at once";

  $("reload").onclick = () => whileBusy($("reload"), () =>
    fetch("/api/reload", { method: "POST", headers: auth }));
  $("save").onclick = () => whileBusy($("save"), async () => {
    for (const tree of ["config", "default_data"]) {
      await fetch(`/api/tree/${tree}/save`, { method: "POST", headers: auth });
    }
    toast(state.lang ? "已保存到 settings/" : "Written to settings/");
  });
  $("advanced").onclick = () => openAdvanced(context());

  window.addEventListener("keydown", (event) => {
    if (event.key === "`" && event.ctrlKey) document.body.classList.toggle("debug");
  });

  window.addEventListener("resize", () => moveIndicator(false));
}

async function main() {
  restoreTheme();
  wireShell();

  let health;
  try {
    health = await (await fetch("/api/health", { headers: auth })).json();
  } catch (error) {
    $("viewport-message").textContent = "The core is not answering /api/health.";
    log("health failed:", error);
    return;
  }
  setStatus(health);
  await Promise.all([loadChoices(), loadPairing()]);
  connect(`${health.websocket}?k=${encodeURIComponent(token)}`);
}

main();
