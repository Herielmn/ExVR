const L = {
  title: ["ExVR {v} - Experience Virtual Reality", "ExVR {v} - 体验虚拟现实"],
  restore: ["Restore default", "恢复默认"],
  restoreHint: ["Back to the default window", "切回默认界面"],
  minimize: ["Minimize", "最小化"],
  maximize: ["Maximize", "最大化"],
  close: ["Close", "关闭"],
  language: ["Language", "语言"],
  steamvrOn: ["SteamVR Installed", "SteamVR 已安装"],
  steamvrOff: ["SteamVR Not Installed", "SteamVR 未安装"],
  flipX: ["Flip X", "水平翻转"],
  flipY: ["Flip Y", "垂直翻转"],
  ip: ["Enter IP camera URL", "输入 IP 摄像头 URL"],
  noCamera: ["No camera found", "未检测到摄像头"],
  performance: ["Performance", "性能"],
  aspect: ["Aspect", "比例"],
  provider: ["Model Provider", "模型后端"],
  priority: ["Priority", "优先级"],
  install: ["Install Drivers", "安装驱动"],
  uninstall: ["Uninstall Drivers", "卸载驱动"],
  start: ["Start Tracking", "开始追踪"],
  stop: ["Stop Tracking", "停止追踪"],
  showFrame: ["Show Frame", "显示画面"],
  hideFrame: ["Hide Frame", "隐藏画面"],
  onlyIngame: ["Only Ingame", "仅游戏内"],
  onlyIngameHint: ["Currently this only applies to hotkeys and mouse input "
                   + "and not head movement",
                   "当前仅作用于热键和鼠标输入，不作用于头部移动"],
  onlyIngameGame: ["window title / process name / VRChat, VRChat.exe, javaw.exe",
                   "窗口标题 / 进程名 / VRChat, VRChat.exe, javaw.exe"],
  resetHead: ["Reset Head", "重置头部"],
  resetEyes: ["Reset Eyes", "重置眼睛"],
  resetLHand: ["Reset LHand", "重置左手"],
  resetRHand: ["Reset RHand", "重置右手"],
  head: ["Head", "头部"],
  face: ["Face", "面部"],
  tongue: ["Tongue", "舌头"],
  hand: ["Hand", "手"],
  handDown: ["Hand Down", "手部下放"],
  fingerAction: ["Finger Action", "手指动作"],
  handReturn: ["Hand Return Time (s)", "手部回正时间 (秒)"],
  leftController: ["Left Controller", "左控制器"],
  rightController: ["Right Controller", "右控制器"],
  mouse: ["Mouse", "鼠标"],
  resetHotkey: ["Reset Hotkey", "重置热键"],
  stopHotkey: ["Stop Hotkey", "停止热键"],
  setFace: ["Set Face", "面部设置"],
  updateConfig: ["Update Config", "刷新配置"],
  saveConfig: ["Save Config", "保存配置"],
  saved: ["Written to settings/", "已保存到 settings/"],
  removing: ["Removing the driver...", "正在卸载驱动…"],
  writing: ["Writing the driver...", "正在写入驱动…"],
  uninstallTitle: ["Uninstall the VMT / VRto3D driver?", "卸载 VMT / VRto3D 驱动？"],
  uninstallBody: ["ExVR's tracking will not work any more once these are removed.",
                  "删除后 ExVR 的追踪功能将不再工作。"],
  uninstallConfirm: ["Uninstall", "卸载"],
};

const MIN = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8h10"/></svg>';
const MAX = '<svg viewBox="0 0 16 16" aria-hidden="true">'
          + '<rect x="3.5" y="3.5" width="9" height="9"/></svg>';
const CLOSE = '<svg viewBox="0 0 16 16" aria-hidden="true">'
            + '<path d="M3.5 3.5l9 9M12.5 3.5l-9 9"/></svg>';

let api = null;
let root = null;
let seat = null;
let syncs = [];

const t = (spec) => api.text(spec);
const cfg = (path) => api.at(api.state.trees.config, path);
const busy = () => Boolean(document.getElementById("busy-veil"));
const el = (tag, className, content) => api.el(tag, className, content);

function row(...kids) {
  const node = el("div", "qt-row");
  node.append(...kids);
  return node;
}

function fill(...kids) {
  const node = el("div", "qt-row qt-fill");
  node.append(...kids);
  return node;
}

const line = () => el("hr", "qt-line");
const label = (spec) => el("span", "qt-label", t(spec));

function button(spec, click, className) {
  const node = el("button", "qt-button qt-wide" + (className ? " " + className : ""), t(spec));
  node.onclick = click;
  return node;
}
function check(spec, path, hint) {
  const wrap = el("label", "qt-check");
  const box = el("input");
  box.type = "checkbox";
  box.checked = Boolean(cfg(path));
  box.onchange = () => api.patch(path, box.checked);
  if (hint) wrap.title = t(hint);
  wrap.append(box, el("span", "", t(spec)));
  syncs.push(() => {
    if (document.activeElement !== box) box.checked = Boolean(cfg(path));
  });
  return wrap;
}

function menu(choices, path, grow) {
  const select = el("select", "qt-select" + (grow ? " qt-grow" : ""));
  for (const [value, caption] of api.state.choices[choices] || []) {
    const option = el("option", "", t(caption));
    option.value = JSON.stringify(value);
    select.append(option);
  }
  const load = () => {
    const stored = cfg(path);
    const value = JSON.stringify(stored);
    if (select.value === value) return;
    select.value = value;
    if (select.selectedIndex < 0) {
      const option = el("option", "", `${stored} (?)`);
      option.value = value;
      select.append(option);
      select.value = value;
    }
  };
  load();
  select.onchange = () => api.patch(path, JSON.parse(select.value));
  syncs.push(load);
  return select;
}

function cameras() {
  const select = el("select", "qt-select qt-grow");
  const devices = api.state.choices.camera_device || [];
  for (const [index, name] of devices) {
    const option = el("option", "", name);
    option.value = String(index);
    select.append(option);
  }
  if (!devices.length) {
    select.append(el("option", "", t(L.noCamera)));
    select.disabled = true;
  }
  if (api.state.choices.camera_selected != null) {
    select.value = String(api.state.choices.camera_selected);
  }
  select.onchange = () => api.command("select_camera", {
    index: Number(select.value),
    name: select.options[select.selectedIndex].textContent,
  });
  return select;
}
function field(path, placeholder) {
  const input = el("input", "qt-input qt-grow");
  input.type = "text";
  input.placeholder = t(placeholder);
  input.value = cfg(path) ?? "";
  input.oninput = () => api.patchSoon(path, input.value);
  input.onchange = () => api.flushPatches();
  syncs.push(() => {
    if (document.activeElement !== input) input.value = cfg(path) ?? "";
  });
  return input;
}

const trim = (value) => String(Number(Number(value).toFixed(2)));

function returnTime() {
  const path = "Tracking/Hand/hand_return_time";
  const input = el("input", "qt-input qt-narrow");
  input.type = "text";
  const show = () => { input.value = trim(cfg(path) ?? 0.5); };
  input.onchange = () => {
    const value = Number(input.value);
    if (!Number.isFinite(value)) { show(); return; }
    const bounded = Math.max(0, Math.min(60, value));
    api.patch(path, bounded);
    input.value = trim(bounded);
  };
  show();
  syncs.push(() => {
    if (document.activeElement !== input) show();
  });
  return input;
}

function slider(spec) {
  const readout = el("span", "qt-value");
  const input = el("input", "qt-slider");
  input.type = "range";
  input.min = String(spec.min);
  input.max = String(spec.max);
  input.step = "1";
  const show = (value) => {
    readout.textContent = `${spec.prefix} ${spec.digits
      ? (value / spec.scale).toFixed(spec.digits)
      : Math.round(value / spec.scale)}`;
  };
  const load = () => {
    input.value = String(Math.round(Number(cfg(spec.key)) * spec.scale));
    show(Number(input.value));
  };
  input.oninput = () => {
    const value = Number(input.value);
    api.state.dirty.add(spec.key);
    show(value);
    api.patchSoon(spec.key, value / spec.scale);
    if (spec.mirror) {
      api.patchSoon(spec.mirror, (spec.negate ? -value : value) / spec.scale);
    }
  };
  input.onchange = () => {
    api.flushPatches();
    api.state.dirty.delete(spec.key);
  };
  load();
  syncs.push(() => {
    if (document.activeElement === input || api.state.dirty.has(spec.key)) return;
    load();
  });
  return [readout, input];
}
const HAND = [
  { prefix: "x", key: "Tracking/Hand/x_scalar", min: 1, max: 200, scale: 100, digits: 2 },
  { prefix: "y", key: "Tracking/Hand/y_scalar", min: 1, max: 200, scale: 100, digits: 2 },
  { prefix: "z", key: "Tracking/Hand/z_scalar", min: 1, max: 100, scale: 100, digits: 2 },
];

const CONTROLLER = [
  { prefix: "x", key: "Tracking/LeftController/base_x", min: -50, max: 50,
    mirror: "Tracking/RightController/base_x", negate: true, scale: 100, digits: 2 },
  { prefix: "y", key: "Tracking/LeftController/base_y", min: -50, max: 50,
    mirror: "Tracking/RightController/base_y", scale: 100, digits: 2 },
  { prefix: "z", key: "Tracking/LeftController/base_z", min: -50, max: 50,
    mirror: "Tracking/RightController/base_z", scale: 100, digits: 2 },
  { prefix: "l", key: "Tracking/LeftController/length", min: 0, max: 100,
    mirror: "Tracking/RightController/length", scale: 100, digits: 2 },
];

const MOUSE = [
  { prefix: "x", key: "Mouse/scalar_x", min: 0, max: 360, scale: 1, digits: 0 },
  { prefix: "y", key: "Mouse/scalar_y", min: 0, max: 360, scale: 1, digits: 0 },
  { prefix: "dx", key: "Mouse/dx", min: 0, max: 20, scale: 100, digits: 2 },
];

function chrome(className, spec, glyph, click) {
  const node = el("button", className);
  node.innerHTML = glyph;
  node.title = t(spec);
  node.setAttribute("aria-label", t(spec));
  node.onclick = click;
  return node;
}

function caption() {
  const bar = el("div", "qt-caption");
  const title = el("div", "qt-title");
  const name = () => t(L.title).replace("{v}", api.state.status.version || "");
  title.textContent = name();
  title.addEventListener("mousedown", () => api.hostSend("drag"));
  title.addEventListener("dblclick", () => api.hostSend("maximize"));
  const restore = el("button", "qt-restore", t(L.restore));
  restore.title = t(L.restoreHint);
  restore.onclick = () => api.setSkin(false);
  bar.append(title, restore);
  if (document.documentElement.classList.contains("hosted")) {
    bar.append(chrome("qt-min", L.minimize, MIN, () => api.hostSend("minimize")),
               chrome("qt-max", L.maximize, MAX, () => api.hostSend("maximize")),
               chrome("qt-close", L.close, CLOSE, () => api.hostSend("close")));
  }
  syncs.push(() => { title.textContent = name(); });
  return bar;
}
function driverButton() {
  const node = button(L.install, async () => {
    const installed = Boolean(api.state.status.driver_installed);
    const held = t(installed ? L.removing : L.writing);
    if (installed) {
      const yes = await api.ask({
        title: t(L.uninstallTitle),
        body: t(L.uninstallBody),
        confirm: t(L.uninstallConfirm),
        destructive: true,
        busy: held,
      });
      if (!yes) return;
    } else {
      api.holdBusy(held);
    }
    api.command("install_components");
  });
  syncs.push(() => {
    const installed = Boolean(api.state.status.driver_installed);
    node.textContent = t(installed ? L.uninstall : L.install);
    node.classList.toggle("qt-blue", !installed);
    node.disabled = busy();
  });
  return node;
}

function trackingButton() {
  const node = button(L.start, () => api.command("toggle_tracking"));
  syncs.push(() => {
    const on = Boolean(api.state.status.tracking);
    node.textContent = t(on ? L.stop : L.start);
    node.classList.toggle("qt-red", on);
    node.classList.toggle("qt-green", !on);
  });
  return node;
}

function frameButton() {
  const node = button(L.showFrame, () => api.togglePreview());
  syncs.push(() => {
    const video = document.getElementById("video");
    const on = Boolean(video && video.getAttribute("src"));
    node.textContent = t(on ? L.hideFrame : L.showFrame);
    node.disabled = !api.state.status.tracking;
  });
  return node;
}

function reload(event) {
  return api.whileBusy(event.currentTarget,
                       () => fetch("/api/reload", { method: "POST", headers: api.auth }));
}

async function save(event) {
  await api.whileBusy(event.currentTarget, async () => {
    for (const tree of ["config", "default_data"]) {
      await fetch(`/api/tree/${tree}/save`, { method: "POST", headers: api.auth });
    }
  });
  api.toast(t(L.saved));
}
export function mountQt(context) {
  if (root) return;
  api = context;
  if (!api.state.trees.config) return;
  syncs = [];
  root = el("div", "");
  root.id = "qt";
  const body = el("div", "qt-body");

  const steamvr = el("span", "qt-steamvr");
  syncs.push(() => {
    const on = Boolean(api.state.status.steamvr);
    steamvr.textContent = t(on ? L.steamvrOn : L.steamvrOff);
    steamvr.classList.toggle("qt-missing", !on);
  });
  body.append(fill(el("span", "qt-grow"), label(L.language),
                   menu("language", "Setting/language"), steamvr));

  const viewport = document.querySelector(".viewport");
  if (viewport) {
    seat = { parent: viewport.parentNode, next: viewport.nextSibling };
    body.append(viewport);
  }

  body.append(row(check(L.flipX, "Setting/flip_x"), check(L.flipY, "Setting/flip_y")));
  body.append(fill(field("Setting/camera_ip", L.ip)));
  body.append(row(cameras(),
                  label(L.performance), menu("camera_performance", "Setting/camera_performance"),
                  label(L.aspect), menu("camera_aspect", "Setting/camera_aspect")));
  body.append(row(label(L.provider), menu("model_provider", "Model/provider")));
  body.append(row(label(L.priority), menu("priority", "Setting/priority")));
  body.append(row(driverButton()));
  body.append(row(trackingButton()));
  body.append(row(frameButton()));
  body.append(fill(check(L.onlyIngame, "Setting/only_ingame", L.onlyIngameHint),
                   field("Setting/only_ingame_game", L.onlyIngameGame)));
  body.append(line());
  body.append(row(button(L.resetHead, () => api.command("reset_head")),
                  button(L.resetEyes, () => api.command("reset_eyes")),
                  button(L.resetLHand, () => api.command("reset_left_hand")),
                  button(L.resetRHand, () => api.command("reset_right_hand"))));
  body.append(row(check(L.head, "Tracking/Head/enable"),
                  check(L.face, "Tracking/Face/enable"),
                  check(L.tongue, "Tracking/Tongue/enable"),
                  check(L.hand, "Tracking/Hand/enable")));
  body.append(row(check(L.handDown, "Tracking/Hand/enable_hand_down"),
                  check(L.fingerAction, "Tracking/Hand/enable_finger_action"),
                  label(L.handReturn), returnTime()));
  body.append(fill(...HAND.flatMap((spec) => slider(spec))));
  body.append(line());
  body.append(row(check(L.leftController, "Tracking/LeftController/enable"),
                  check(L.rightController, "Tracking/RightController/enable")));
  body.append(fill(...CONTROLLER.flatMap((spec) => slider(spec))));
  body.append(line());
  body.append(fill(check(L.mouse, "Mouse/enable"),
                   ...MOUSE.flatMap((spec) => slider(spec))));
  body.append(line());
  body.append(row(button(L.resetHotkey, () => api.command("reset_hotkeys")),
                  button(L.stopHotkey, () => api.command("stop_hotkeys")),
                  button(L.setFace, () => api.openAdvanced()),
                  button(L.updateConfig, reload),
                  button(L.saveConfig, save)));

  root.append(caption(), body);
  document.body.append(root);
  syncQt();
}

export function unmountQt() {
  if (!root) return;
  const viewport = root.querySelector(".viewport");
  if (viewport && seat && seat.parent) seat.parent.insertBefore(viewport, seat.next);
  root.remove();
  root = null;
  seat = null;
  syncs = [];
}

export function syncQt() {
  if (!root) return;
  for (const run of syncs) run();
}
