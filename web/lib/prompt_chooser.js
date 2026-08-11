/**
 * Fetch/cache and DOM overlays for the Prompt Library node, backed by
 * MoonPack's /moonpack/prompt_library routes.
 */

import { api } from "../../../scripts/api.js";

const STYLE_ID = "moonpack-prompt-chooser-style";
const CSS = `
.moonpack-prompt-chooser {
    position: absolute;
    z-index: 10000;
    display: flex;
    flex-direction: column;
    width: 420px;
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
.moonpack-prompt-chooser input {
    flex: 0 0 auto;
    margin: 6px;
    padding: 6px 8px;
    background: var(--comfy-input-bg, #222);
    color: var(--input-text, #ddd);
    border: 1px solid var(--border-color, #4e4e4e);
    border-radius: 4px;
    outline: none;
}
.moonpack-prompt-chooser ul {
    flex: 1 1 auto;
    margin: 0;
    padding: 0 0 4px 0;
    list-style: none;
    overflow-y: auto;
}
.moonpack-prompt-chooser li {
    padding: 5px 10px;
    cursor: pointer;
}
.moonpack-prompt-chooser li:hover,
.moonpack-prompt-chooser li.selected {
    background: var(--comfy-menu-secondary-bg, #4a4a4a);
}
.moonpack-prompt-chooser .moonpack-entry-name {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.moonpack-prompt-chooser .moonpack-entry-desc {
    font-size: 11px;
    opacity: 0.65;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.moonpack-prompt-chooser .moonpack-empty {
    padding: 10px;
    opacity: 0.6;
    cursor: default;
}
.moonpack-prompt-dialog-backdrop {
    position: fixed;
    inset: 0;
    z-index: 10001;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
}
.moonpack-prompt-dialog {
    width: 380px;
    background: var(--comfy-menu-bg, #353535);
    color: var(--fg-color, #fff);
    border: 1px solid var(--border-color, #4e4e4e);
    border-radius: 6px;
    box-shadow: 0 6px 24px rgba(0, 0, 0, 0.5);
    font-family: sans-serif;
    font-size: 13px;
    padding: 14px;
}
.moonpack-prompt-dialog h3 {
    margin: 0 0 10px 0;
    font-size: 14px;
}
.moonpack-prompt-dialog label {
    display: block;
    margin: 8px 0 3px 0;
    opacity: 0.8;
}
.moonpack-prompt-dialog input {
    width: 100%;
    box-sizing: border-box;
    padding: 6px 8px;
    background: var(--comfy-input-bg, #222);
    color: var(--input-text, #ddd);
    border: 1px solid var(--border-color, #4e4e4e);
    border-radius: 4px;
    outline: none;
}
.moonpack-prompt-dialog input:disabled {
    opacity: 0.6;
}
.moonpack-prompt-dialog .moonpack-error {
    color: #e06868;
    margin-top: 8px;
    min-height: 1em;
}
.moonpack-prompt-dialog .moonpack-dialog-buttons {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 14px;
}
.moonpack-prompt-dialog button {
    padding: 6px 14px;
    background: var(--comfy-input-bg, #222);
    color: var(--input-text, #ddd);
    border: 1px solid var(--border-color, #4e4e4e);
    border-radius: 4px;
    cursor: pointer;
}
.moonpack-prompt-dialog button:hover {
    background: var(--comfy-menu-secondary-bg, #4a4a4a);
}
`;

function ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = CSS;
    document.head.appendChild(style);
}

let cache = null;
let inflight = null;

/** Returns every saved entry ({name, description, tags, text}), cached for the session. */
export function fetchPromptEntries(force = false) {
    if (force) {
        cache = null;
        inflight = null;
    }
    if (cache) return Promise.resolve(cache);
    if (!inflight) {
        inflight = api
            .fetchApi("/moonpack/prompt_library")
            .then((response) => response.json())
            .then((data) => {
                cache = Array.isArray(data?.entries) ? data.entries : [];
                return cache;
            })
            .catch((error) => {
                console.error("[MoonPack] could not load the prompt library:", error);
                inflight = null;
                return [];
            });
    }
    return inflight;
}

export function clearPromptCache() {
    cache = null;
    inflight = null;
}

async function request(method, path, body) {
    const response = await api.fetchApi(path, {
        method,
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(data?.error || `Request failed (${response.status}).`);
    }
    clearPromptCache();
    return data.entries;
}

export const createPromptEntry = (entry) => request("POST", "/moonpack/prompt_library", entry);
export const updatePromptEntry = (name, entry) =>
    request("PUT", `/moonpack/prompt_library/${encodeURIComponent(name)}`, entry);
export const deletePromptEntry = (name) =>
    request("DELETE", `/moonpack/prompt_library/${encodeURIComponent(name)}`);

/**
 * Opens the searchable entry picker near the given mouse event.
 * `onPick` is called with the chosen entry; cancelling calls nothing.
 */
export function showPromptChooser(event, entries, onPick) {
    ensureStyle();

    const root = document.createElement("div");
    root.className = "moonpack-prompt-chooser";

    const input = document.createElement("input");
    input.type = "text";
    input.placeholder = "Filter prompts…";
    input.spellcheck = false;

    const list = document.createElement("ul");
    root.append(input, list);
    document.body.appendChild(root);

    const left = Math.min(event?.clientX ?? 100, window.innerWidth - 440);
    const top = Math.min(event?.clientY ?? 100, window.innerHeight - 260);
    root.style.left = `${Math.max(8, left)}px`;
    root.style.top = `${Math.max(8, top)}px`;

    let shown = [];
    let selected = 0;

    function close() {
        document.removeEventListener("pointerdown", onOutside, true);
        root.remove();
    }

    function pick(entry) {
        close();
        if (entry != null) onPick(entry);
    }

    function onOutside(e) {
        if (!root.contains(e.target)) close();
    }

    function render() {
        const filter = input.value.trim().toLowerCase();
        shown = filter
            ? entries.filter((entry) => (entry.name || "").toLowerCase().includes(filter))
            : entries.slice();
        selected = 0;
        list.replaceChildren();

        if (!shown.length) {
            const empty = document.createElement("li");
            empty.className = "moonpack-empty";
            empty.textContent = entries.length ? "No match" : "Library is empty";
            list.appendChild(empty);
            return;
        }

        shown.forEach((entry, index) => {
            const item = document.createElement("li");
            const nameLine = document.createElement("div");
            nameLine.className = "moonpack-entry-name";
            nameLine.textContent = entry.name;
            item.appendChild(nameLine);
            if (entry.description) {
                const descLine = document.createElement("div");
                descLine.className = "moonpack-entry-desc";
                descLine.textContent = entry.description;
                item.appendChild(descLine);
            }
            item.title = [entry.description, entry.tags].filter(Boolean).join(" · ");
            if (index === selected) item.classList.add("selected");
            item.addEventListener("click", () => pick(entry));
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
    setTimeout(() => document.addEventListener("pointerdown", onOutside, true), 0);
    input.focus();
}

/**
 * Opens a small modal with name/description/tags fields.
 * `onSubmit` receives {name, description, tags} and may return a Promise;
 * a rejection's message is shown inline and the dialog stays open.
 */
export function showPromptEditDialog({ title, name = "", description = "", tags = "", lockName = false }, onSubmit) {
    ensureStyle();

    const backdrop = document.createElement("div");
    backdrop.className = "moonpack-prompt-dialog-backdrop";

    const dialog = document.createElement("div");
    dialog.className = "moonpack-prompt-dialog";
    backdrop.appendChild(dialog);
    document.body.appendChild(backdrop);

    const heading = document.createElement("h3");
    heading.textContent = title;
    dialog.appendChild(heading);

    function field(labelText, value, disabled) {
        const label = document.createElement("label");
        label.textContent = labelText;
        const box = document.createElement("input");
        box.type = "text";
        box.value = value;
        box.disabled = !!disabled;
        dialog.append(label, box);
        return box;
    }

    const nameInput = field("Name", name, lockName);
    const descInput = field("Description", description);
    const tagsInput = field("Tags (comma-separated)", tags);

    const error = document.createElement("div");
    error.className = "moonpack-error";
    dialog.appendChild(error);

    const buttons = document.createElement("div");
    buttons.className = "moonpack-dialog-buttons";
    const cancelBtn = document.createElement("button");
    cancelBtn.textContent = "Cancel";
    const submitBtn = document.createElement("button");
    submitBtn.textContent = "Save";
    buttons.append(cancelBtn, submitBtn);
    dialog.appendChild(buttons);

    function close() {
        backdrop.remove();
    }

    cancelBtn.addEventListener("click", close);
    backdrop.addEventListener("pointerdown", (e) => {
        if (e.target === backdrop) close();
    });

    submitBtn.addEventListener("click", () => {
        error.textContent = "";
        const result = onSubmit({
            name: nameInput.value.trim(),
            description: descInput.value.trim(),
            tags: tagsInput.value.trim(),
        });
        Promise.resolve(result)
            .then(close)
            .catch((err) => {
                error.textContent = err?.message || String(err);
            });
    });

    (lockName ? descInput : nameInput).focus();
}
