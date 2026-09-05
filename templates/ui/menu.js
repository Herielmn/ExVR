const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

let open = null;

function chevron() {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 12 12");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("class", "menu-chevron");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", "M3 4.6L6 7.6l3-3");
  svg.append(path);
  return svg;
}

function tick() {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 12 12");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("class", "menu-tick");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", "M2.4 6.4l2.4 2.4 4.8-5.2");
  svg.append(path);
  return svg;
}

function selected(select) {
  const option = select.options[select.selectedIndex];
  return option ? option.textContent : "";
}

export function syncMenu(select) {
  const wrap = select.closest(".menu-control");
  if (!wrap) return;
  const value = selected(select);
  wrap.querySelector(".menu-label").textContent = value;
  const button = wrap.querySelector(".menu-button");
  button.disabled = select.disabled;
  button.setAttribute("aria-label", wrap.dataset.name
    ? `${wrap.dataset.name}: ${value}` : value);
}

function place(popover, button) {
  const anchor = button.getBoundingClientRect();
  const margin = 8;
  popover.style.minWidth = `${Math.round(anchor.width)}px`;
  popover.style.left = "0px";
  popover.style.top = "0px";
  const box = { width: popover.offsetWidth, height: popover.offsetHeight };
  const room = window.innerHeight - anchor.bottom - margin;
  const above = room < box.height && anchor.top > room;
  const left = Math.max(margin,
                        Math.min(anchor.left, window.innerWidth - box.width - margin));
  popover.style.left = `${Math.round(left)}px`;
  if (above) {
    popover.style.top = `${Math.round(Math.max(margin, anchor.top - box.height - 4))}px`;
    popover.dataset.side = "above";
  } else {
    popover.style.top = `${Math.round(anchor.bottom + 4)}px`;
    popover.dataset.side = "below";
    popover.style.maxHeight = `${Math.round(room)}px`;
  }
}

function closeMenu(restoreFocus = true) {
  if (!open) return;
  const { popover, button, listeners } = open;
  open = null;
  for (const [target, type, handler, options] of listeners) {
    target.removeEventListener(type, handler, options);
  }
  button.setAttribute("aria-expanded", "false");
  popover.classList.add("closing");
  popover.addEventListener("animationend", () => popover.remove(), { once: true });
  setTimeout(() => popover.remove(), 400);
  if (restoreFocus) button.focus();
}

function pick(select, option) {
  const wanted = option.dataset.value;
  closeMenu();
  if (select.value === wanted) return;
  select.value = wanted;
  syncMenu(select);
  select.dispatchEvent(new Event("change", { bubbles: true }));
}

function openMenu(select, button) {
  closeMenu(false);
  const popover = el("div", "menu-popover");
  popover.role = "listbox";
  popover.tabIndex = -1;
  const name = button.closest(".menu-control").dataset.name;
  if (name) popover.setAttribute("aria-label", name);

  const items = [];
  for (const option of select.options) {
    const item = el("div", "menu-item");
    item.role = "option";
    item.dataset.value = option.value;
    item.tabIndex = -1;
    const chosen = option.value === select.value;
    item.setAttribute("aria-selected", String(chosen));
    item.append(tick(), el("span", "", option.textContent));
    item.onclick = () => pick(select, item);
    popover.append(item);
    items.push(item);
  }
  document.body.append(popover);
  place(popover, button);
  button.setAttribute("aria-expanded", "true");

  let at = Math.max(0, select.selectedIndex);
  const focus = (index) => {
    at = (index + items.length) % items.length;
    items[at].focus();
    items[at].scrollIntoView({ block: "nearest" });
  };
  if (items.length) focus(at);

  const onKey = (event) => {
    const key = event.key;
    const mine = () => { event.preventDefault(); event.stopPropagation(); };
    if (key === "Escape") { mine(); closeMenu(); return; }
    if (key === "Tab") { closeMenu(); return; }
    if (key === "ArrowDown") { mine(); focus(at + 1); return; }
    if (key === "ArrowUp") { mine(); focus(at - 1); return; }
    if (key === "Home") { mine(); focus(0); return; }
    if (key === "End") { mine(); focus(items.length - 1); return; }
    if (key === "Enter" || key === " ") {
      mine();
      if (items[at]) pick(select, items[at]);
      return;
    }
    if (key.length === 1 && !event.ctrlKey && !event.altKey && !event.metaKey) {
      const needle = key.toLowerCase();
      for (let step = 1; step <= items.length; step++) {
        const index = (at + step) % items.length;
        if (items[index].textContent.trim().toLowerCase().startsWith(needle)) {
          mine();
          focus(index);
          return;
        }
      }
    }
  };
  const onDown = (event) => {
    if (!popover.contains(event.target) && !button.contains(event.target)) closeMenu(false);
  };
  const onScroll = (event) => {
    if (!popover.contains(event.target)) closeMenu(false);
  };
  const listeners = [
    [document, "keydown", onKey, true],
    [document, "pointerdown", onDown, true],
    [document, "scroll", onScroll, true],
    [window, "resize", () => closeMenu(false), true],
  ];
  for (const [target, type, handler, options] of listeners) {
    target.addEventListener(type, handler, options);
  }
  open = { popover, button, select, listeners };
}

export function menuControl(select, name) {
  const wrap = el("div", "menu-control");
  if (name) wrap.dataset.name = name;
  select.classList.remove("menu");
  select.classList.add("menu-model");
  select.setAttribute("aria-hidden", "true");
  select.tabIndex = -1;

  const button = el("button", "menu-button");
  button.type = "button";
  button.setAttribute("aria-haspopup", "listbox");
  button.setAttribute("aria-expanded", "false");
  if (select.id) {
    button.id = select.id;
    select.removeAttribute("id");
  }
  button.append(el("span", "menu-label"), chevron());
  button.onclick = () => {
    if (open && open.select === select) closeMenu();
    else openMenu(select, button);
  };
  wrap.append(select, button);
  syncMenu(select);
  return wrap;
}

export function closeAnyMenu() {
  closeMenu(false);
}
