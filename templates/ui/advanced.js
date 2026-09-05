import { ADVANCED } from "/ui/spec.js";
import { menuControl, closeAnyMenu } from "/ui/menu.js";

const LABEL = {
  title: ["Advanced", "高级"],
  panel: ["Panel", "面板"],
  done: ["Done", "完成"],
  filter: ["Filter", "筛选"],
  matches: ["visible", "可见"],
  blendshape: ["Blend shape", "表情"],
  value: ["Value", "值"],
  shifting: ["Shifting", "偏移"],
  weight: ["Weight", "权重"],
  max: ["Max", "上限"],
  on: ["On", "启用"],
  stage: ["Stage", "阶段"],
  setting: ["Setting", "设置项"],
  empty: ["Nothing here", "没有内容"],
  readonly: ["Read-only: the app loads this table and never writes it back",
             "只读：程序只加载这张表，不会写回"],
  metricsOff: ["Metrics are off. Set EXVR_METRICS=1, or put a metrics.on file "
               + "next to settings/, and restart the core.",
               "未开启 metrics。设置 EXVR_METRICS=1，或在 settings/ 旁放一个 "
               + "metrics.on 文件，然后重启核心。"],
  live: ["Live, from the core", "实时，来自核心"],
  nullLeaf: ["null: no type to write against", "null：没有类型可写入"],
  appliesLive: ["Applies live. Save in the action bar writes settings/data.json.",
                "立即生效。点动作栏的「保存」才写入 settings/data.json。"],
  appliesLiveTree: ["Applies live. Save in the action bar writes it to settings/.",
                    "立即生效。点动作栏的「保存」才写入 settings/。"],
};

let current = null;

function column(api, label, className = "") {
  const cell = api.el("th", className, label);
  cell.scope = "col";
  return cell;
}

export function openAdvanced(api) {
  if (current) return;
  const { el, text, dismiss } = api;

  const backdrop = el("div", "sheet-backdrop");
  const sheet = el("section", "sheet");
  sheet.role = "dialog";
  sheet.setAttribute("aria-modal", "true");
  sheet.setAttribute("aria-label", text(LABEL.title));
  sheet.tabIndex = -1;

  const header = el("header");
  const picker = el("select", "menu");
  picker.setAttribute("aria-label", text(LABEL.panel));
  for (const panel of ADVANCED) {
    const option = el("option", "", text(panel.t));
    option.value = panel.id;
    picker.append(option);
  }
  const done = el("button", "button small", text(LABEL.done));
  header.append(el("h2", "", text(LABEL.title)),
                menuControl(picker, text(LABEL.panel)), done);

  const body = el("div", "body");
  const footer = el("footer");
  sheet.append(header, body, footer);
  backdrop.append(sheet);

  const restore = document.activeElement;
  let stop = null;

  function close() {
    if (stop) stop();
    document.removeEventListener("keydown", onKey);
    closeAnyMenu();
    current = null;
    dismiss(backdrop, () => { if (restore && restore.focus) restore.focus(); });
  }

  function onKey(event) {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = sheet.querySelectorAll(
      "button, select:not(.menu-model), input:not([disabled])");
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function show(id) {
    if (stop) stop();
    body.textContent = "";
    footer.textContent = "";
    stop = build(api, id, body, footer) || null;
    body.scrollTop = 0;
    body.classList.remove("swapped");
    void body.offsetWidth;
    body.classList.add("swapped");
  }

  done.onclick = close;
  backdrop.onclick = (event) => { if (event.target === backdrop) close(); };
  picker.onchange = () => show(picker.value);
  document.addEventListener("keydown", onKey);

  document.body.append(backdrop);
  current = backdrop;
  show(picker.value);
  sheet.focus();
}

function build(api, id, body, footer) {
  const { el, text } = api;
  const panel = ADVANCED.find((entry) => entry.id === id);
  if (panel && panel.detail) body.append(el("p", "note", text(panel.detail)));
  if (id === "blendshapes") return buildBlendshapes(api, body, footer);
  if (id === "metrics") return buildMetrics(api, body, footer);
  if (id.startsWith("tree:")) return buildTree(api, id.slice(5), body, footer);
  body.append(el("p", "note", text(LABEL.empty)));
  return null;
}

function tools(api, rows, describe) {
  const { el, text } = api;
  const bar = el("div", "tools");
  const field = el("input", "field grow");
  field.type = "search";
  field.placeholder = text(LABEL.filter);
  const count = el("span", "count");
  const apply = () => {
    const needle = field.value.trim().toLowerCase();
    let shown = 0;
    for (const [row, key] of rows) {
      const hit = !needle || key.toLowerCase().includes(needle);
      row.hidden = !hit;
      if (hit) shown += 1;
    }
    count.textContent = describe(shown, rows.length);
  };
  field.oninput = apply;
  bar.append(field, count);
  apply();
  return bar;
}

function leafInput(api, tree, path, value, writable) {
  const { el, patch } = api;
  const commit = (next) => patch(path, next, tree);
  if (typeof value === "boolean") {
    const input = el("input");
    input.type = "checkbox";
    input.checked = value;
    input.dataset.path = path;
    input.dataset.tree = tree;
    input.disabled = !writable;
    input.onchange = () => commit(input.checked);
    return input;
  }
  if (typeof value === "number") {
    const input = el("input", "field number");
    input.type = "number";
    input.step = Number.isInteger(value) ? "1" : "any";
    input.value = value;
    input.dataset.path = path;
    input.dataset.tree = tree;
    input.readOnly = !writable;
    if (writable) input.onchange = () => commit(Number(input.value));
    return input;
  }
  if (typeof value === "string") {
    const input = el("input", "field grow");
    input.type = "text";
    input.value = value;
    input.dataset.path = path;
    input.dataset.tree = tree;
    input.readOnly = !writable;
    if (writable) input.onchange = () => commit(input.value);
    return input;
  }
  return el("span", "count", api.text(LABEL.nullLeaf));
}

function buildBlendshapes(api, body, footer) {
  const { state, el, text, at } = api;
  const shapes = at(state.trees, "default_data/BlendShapes") || [];
  const writable = state.writable.has("default_data");

  const table = el("table", "data");
  const heading = el("tr");
  heading.append(column(api, text(LABEL.blendshape)));
  for (const label of [LABEL.value, LABEL.shifting, LABEL.weight, LABEL.max, LABEL.on]) {
    heading.append(column(api, text(label), "n"));
  }
  const head = el("thead");
  head.append(heading);
  const rows = [];
  const list = el("tbody");

  for (let index = 1; index < shapes.length; index++) {
    const shape = shapes[index];
    const row = el("tr");
    row.append(el("td", "key", shape.k));
    for (const key of ["v", "s", "w", "max"]) {
      const cell = el("td", "n");
      const input = leafInput(api, "default_data", `BlendShapes/${index}/${key}`,
                              Number(shape[key]), writable);
      input.step = "0.01";
      input.value = Number(shape[key]).toFixed(2);
      cell.append(input);
      row.append(cell);
    }
    const enabled = el("td", "n");
    enabled.append(leafInput(api, "default_data", `BlendShapes/${index}/e`,
                             Boolean(shape.e), writable));
    row.append(enabled);
    list.append(row);
    rows.push([row, shape.k]);
  }

  table.append(head, list);
  body.append(tools(api, rows, (shown, total) =>
    `${shown}/${total} ${text(LABEL.matches)}`), table);
  footer.append(el("span", "note", text(LABEL.appliesLive)));
  return null;
}

function buildMetrics(api, body, footer) {
  const { state, el, text } = api;
  if (!state.status.metrics_enabled) {
    body.append(el("p", "note", text(LABEL.metricsOff)));
    return null;
  }
  const table = el("table", "data");
  const heading = el("tr");
  heading.append(column(api, text(LABEL.stage)));
  for (const label of ["n", "p50 ms", "p95 ms", "max ms", "Hz"]) {
    heading.append(column(api, label, "n"));
  }
  const head = el("thead");
  head.append(heading);
  const list = el("tbody");
  table.append(head, list);
  body.append(table);
  footer.append(el("span", "note", text(LABEL.live)));

  const paint = () => {
    const series = state.metrics || {};
    const timings = series.timings || {};
    const counters = series.counters || {};
    list.textContent = "";
    for (const name of Object.keys(timings).sort()) {
      const entry = timings[name];
      const row = el("tr");
      row.append(el("td", "key", name), el("td", "n", String(entry.n)),
                 el("td", "n", entry.p50_ms.toFixed(2)),
                 el("td", "n", entry.p95_ms.toFixed(2)),
                 el("td", "n", entry.max_ms.toFixed(2)),
                 el("td", "n", entry.hz.toFixed(1)));
      list.append(row);
    }
    for (const name of Object.keys(counters).sort()) {
      const row = el("tr");
      row.append(el("td", "key", name), el("td", "n", String(counters[name])));
      row.append(el("td"), el("td"), el("td"), el("td"));
      list.append(row);
    }
    if (!list.childElementCount) {
      const row = el("tr");
      const cell = el("td", "key", text(LABEL.empty));
      cell.colSpan = 6;
      row.append(cell);
      list.append(row);
    }
  };
  paint();
  const timer = setInterval(paint, 1000);
  return () => clearInterval(timer);
}

function buildTree(api, name, body, footer) {
  const { state, el, text } = api;
  const tree = state.trees[name];
  if (!tree) {
    body.append(el("p", "note", text(LABEL.empty)));
    return null;
  }
  const writable = state.writable.has(name);

  const table = el("table", "data");
  const heading = el("tr");
  heading.append(column(api, text(LABEL.setting)), column(api, text(LABEL.value)));
  const head = el("thead");
  head.append(heading);
  const list = el("tbody");
  const rows = [];
  for (const [path, value] of leaves(tree)) {
    const row = el("tr");
    row.append(el("td", "key", path));
    const cell = el("td");
    cell.append(leafInput(api, name, path, value, writable));
    row.append(cell);
    list.append(row);
    rows.push([row, path]);
  }
  table.append(head, list);
  body.append(tools(api, rows, (shown, total) =>
    `${shown}/${total} ${text(LABEL.matches)}`), table);
  footer.append(el("span", "note",
                   text(writable ? LABEL.appliesLiveTree : LABEL.readonly)));
  return null;
}

function leaves(node, prefix = "") {
  const out = [];
  const entries = Array.isArray(node)
    ? node.map((value, index) => [String(index), value])
    : Object.entries(node);
  for (const [key, value] of entries) {
    const path = prefix ? `${prefix}/${key}` : key;
    if (value !== null && typeof value === "object") out.push(...leaves(value, path));
    else out.push([path, value]);
  }
  return out;
}
