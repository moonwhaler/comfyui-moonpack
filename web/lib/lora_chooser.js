/**
 * Filterable LoRA picker overlay, backed by MoonPack's /moonpack/loras route.
 *
 * ComfyUI has no built-in filterable menu and a plain ContextMenu is unusable
 * with a large library, so this is a small DOM overlay: search box on top,
 * scrollable list below, keyboard navigable.
 */

import { api } from "../../../scripts/api.js";

const STYLE_ID = "moonpack-lora-chooser-style";
const CSS = `
.moonpack-lora-chooser {
    position: absolute;
    z-index: 10000;
    display: flex;
    flex-direction: column;
    width: 380px;
    max-height: 60vh;
    background: var(--comfy-menu-bg, #353535);
    color: var(--fg-color, #fff);
    border: 1px solid var(--border-color, #4e4e4e);
    border-radius: 6px;
    box-shadow: 0 6px 24px rgba(0, 0, 0, 0.5);
    font-family: sans-serif;
    font-size: 13px;
    overflow: hidden;
}
.moonpack-lora-chooser input {
    flex: 0 0 auto;
    margin: 6px;
    padding: 6px 8px;
    background: var(--comfy-input-bg, #222);
    color: var(--input-text, #ddd);
    border: 1px solid var(--border-color, #4e4e4e);
    border-radius: 4px;
    outline: none;
}
.moonpack-lora-chooser ul {
    flex: 1 1 auto;
    margin: 0;
    padding: 0 0 4px 0;
    list-style: none;
    overflow-y: auto;
}
.moonpack-lora-chooser li {
    padding: 5px 10px;
    cursor: pointer;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    direction: rtl;
    text-align: left;
}
.moonpack-lora-chooser li:hover,
.moonpack-lora-chooser li.selected {
    background: var(--comfy-menu-secondary-bg, #4a4a4a);
}
.moonpack-lora-chooser .moonpack-empty {
    padding: 10px;
    opacity: 0.6;
    cursor: default;
}
`;

let cache = null;
let inflight = null;

function ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = CSS;
    document.head.appendChild(style);
}

/** Returns every lora file, cached for the session. */
export function fetchLoras(force = false) {
    if (force) {
        cache = null;
        inflight = null;
    }
    if (cache) return Promise.resolve(cache);
    if (!inflight) {
        inflight = api
            .fetchApi("/moonpack/loras")
            .then((response) => response.json())
            .then((data) => {
                cache = Array.isArray(data?.loras) ? data.loras : [];
                return cache;
            })
            .catch((error) => {
                console.error("[MoonPack] could not load the lora list:", error);
                inflight = null;
                return [];
            });
    }
    return inflight;
}

export function clearLoraCache() {
    cache = null;
    inflight = null;
}

/**
 * Opens the picker near the given mouse event.
 * `onPick` is called with the chosen path; cancelling calls nothing.
 */
export function showLoraChooser(event, loras, onPick) {
    ensureStyle();

    const root = document.createElement("div");
    root.className = "moonpack-lora-chooser";

    const input = document.createElement("input");
    input.type = "text";
    input.placeholder = "Filter LoRAs…";
    input.spellcheck = false;

    const list = document.createElement("ul");
    root.append(input, list);
    document.body.appendChild(root);

    // Keep the overlay on screen regardless of where the node was clicked.
    const left = Math.min(event?.clientX ?? 100, window.innerWidth - 400);
    const top = Math.min(event?.clientY ?? 100, window.innerHeight - 260);
    root.style.left = `${Math.max(8, left)}px`;
    root.style.top = `${Math.max(8, top)}px`;

    let shown = [];
    let selected = 0;

    function close() {
        document.removeEventListener("pointerdown", onOutside, true);
        root.remove();
    }

    function pick(value) {
        close();
        if (value != null) onPick(value);
    }

    function onOutside(e) {
        if (!root.contains(e.target)) close();
    }

    function render() {
        const filter = input.value.trim().toLowerCase();
        shown = filter
            ? loras.filter((name) => name.toLowerCase().includes(filter))
            : loras.slice();
        selected = 0;
        list.replaceChildren();

        if (!shown.length) {
            const empty = document.createElement("li");
            empty.className = "moonpack-empty";
            // direction:rtl on li would mangle this message
            empty.style.direction = "ltr";
            empty.textContent = loras.length ? "No match" : "No LoRAs found";
            list.appendChild(empty);
            return;
        }

        shown.forEach((name, index) => {
            const item = document.createElement("li");
            // rtl keeps the filename visible when the path overflows; the
            // bidi isolate stops it from reordering the path itself.
            item.textContent = `⁦${name}⁩`;
            item.title = name;
            if (index === selected) item.classList.add("selected");
            item.addEventListener("click", () => pick(name));
            list.appendChild(item);
        });
    }

    function moveSelection(delta) {
        if (!shown.length) return;
        const items = list.querySelectorAll("li");
        items[selected]?.classList.remove("selected");
        selected = Math.max(0, Math.min(shown.length - 1, selected + delta));
        items[selected]?.classList.add("selected");
        items[selected]?.scrollIntoView({ block: "nearest" });
    }

    input.addEventListener("input", render);
    input.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            e.preventDefault();
            close();
        } else if (e.key === "ArrowDown") {
            e.preventDefault();
            moveSelection(1);
        } else if (e.key === "ArrowUp") {
            e.preventDefault();
            moveSelection(-1);
        } else if (e.key === "Enter") {
            e.preventDefault();
            if (shown.length) pick(shown[selected]);
        }
        e.stopPropagation();
    });

    render();
    // Deferred so the click that opened the chooser does not immediately close it.
    setTimeout(() => document.addEventListener("pointerdown", onOutside, true), 0);
    input.focus();
}
