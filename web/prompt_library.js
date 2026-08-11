/**
 * Prompt Library - a managed multiline text box backed by a shared,
 * server-side JSON library (see prompt_library_routes.py).
 *
 * Uses only native LiteGraph widgets (combo + buttons) - no hand-drawn canvas
 * UI. The `text` widget is the output; `prompt` (a combo) just remembers
 * which library entry is loaded. Editing the text auto-saves to that entry
 * after a short pause; there is no separate "update" step.
 */

import { app } from "../../scripts/app.js";
import {
    createPromptEntry,
    deletePromptEntry,
    fetchPromptEntries,
    updatePromptEntry,
} from "./lib/prompt_library_api.js";

const NODE_TYPE = "MoonPack_PromptLibrary";
const AUTOSAVE_DELAY_MS = 600;

let lastPointerEvent = null;
document.addEventListener("pointerdown", (e) => (lastPointerEvent = e), true);

function setupPromptLibrary(nodeType) {
    nodeType.prototype.moonTextWidget = function () {
        return this.widgets?.find((w) => w.name === "text");
    };

    /**
     * The multiline widget's `.value` can lag one keystroke behind the actual
     * textarea while it's focused; `.inputEl` (the real <textarea>) is always
     * current, so read that directly wherever a save is about to happen.
     */
    nodeType.prototype.moonCurrentText = function () {
        const widget = this.moonTextWidget();
        return widget?.inputEl?.value ?? widget?.value ?? "";
    };

    nodeType.prototype.moonComboWidget = function () {
        return this.widgets?.find((w) => w.name === "prompt");
    };

    /** Re-pulls the library from the server and repopulates the dropdown in place. */
    nodeType.prototype.moonRefreshEntries = function (selectName) {
        fetchPromptEntries(true).then((entries) => {
            this._moonEntries = entries;
            const combo = this.moonComboWidget();
            if (!combo) return;
            combo.options.values.length = 0;
            combo.options.values.push(...entries.map((e) => e.name));
            if (selectName !== undefined) combo.value = selectName;
            this.setDirtyCanvas(true, true);
        });
    };

    /**
     * Reads the combo's own `.value` rather than trusting the callback argument:
     * some LiteGraph/ComfyUI builds don't reliably pass the clicked value through
     * to combo callbacks, while `.value` itself is always kept correct by the
     * framework (same defensive pattern rgthree-comfy uses for its combos).
     */
    nodeType.prototype.moonLoadEntry = function () {
        const name = this.moonComboWidget()?.value;
        const entry = (this._moonEntries || []).find((e) => e.name === name);
        if (entry) this.moonTextWidget().value = entry.text ?? "";
        this.setDirtyCanvas(true, true);
    };

    nodeType.prototype.moonScheduleAutosave = function () {
        const name = this.moonComboWidget()?.value;
        if (!name) return;
        clearTimeout(this._moonSaveTimer);
        this._moonSaveTimer = setTimeout(() => {
            updatePromptEntry(name, { text: this.moonCurrentText() }).catch((err) => {
                console.error("[MoonPack] Prompt Library autosave failed:", err);
            });
        }, AUTOSAVE_DELAY_MS);
    };

    nodeType.prototype.moonNewPrompt = function () {
        app.canvas.prompt(
            "New prompt name",
            "",
            (entered) => {
                const name = String(entered ?? "").trim();
                if (!name) return;
                createPromptEntry({ name, text: this.moonCurrentText() })
                    .then(() => this.moonRefreshEntries(name))
                    .catch((err) => alert(err?.message || String(err)));
            },
            lastPointerEvent,
        );
    };

    nodeType.prototype.moonDeletePrompt = function () {
        const name = this.moonComboWidget()?.value;
        if (!name) {
            alert("No prompt is selected.");
            return;
        }
        if (!confirm(`Delete '${name}' from the prompt library? This cannot be undone.`)) return;
        deletePromptEntry(name)
            .then(() => this.moonRefreshEntries(""))
            .catch((err) => alert(err?.message || String(err)));
    };

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
        onNodeCreated?.apply(this, arguments);
        this.serialize_widgets = true;
        this._moonEntries = [];

        const combo = this.addWidget("combo", "prompt", "", () => this.moonLoadEntry(), {
            values: [],
        });
        this.widgets.splice(this.widgets.indexOf(combo), 1);
        this.widgets.unshift(combo);

        this.addWidget("button", "New Prompt", null, () => this.moonNewPrompt());
        this.addWidget("button", "Delete Prompt", null, () => this.moonDeletePrompt());

        // Prefer a direct DOM listener over wrapping widget.callback: it fires
        // on every keystroke regardless of how this ComfyUI build's widget
        // bridge wires (or doesn't wire) callback dispatch for text areas.
        const textWidget = this.moonTextWidget();
        const node = this;
        if (textWidget.inputEl) {
            textWidget.inputEl.addEventListener("input", () => node.moonScheduleAutosave());
        } else {
            const originalCallback = textWidget.callback;
            textWidget.callback = function (...args) {
                originalCallback?.apply(this, args);
                node.moonScheduleAutosave();
            };
        }

        this.moonRefreshEntries();
        this.setDirtyCanvas(true, true);
    };
}

app.registerExtension({
    name: "comfyui.moonpack.prompt-library",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name === NODE_TYPE) {
            setupPromptLibrary(nodeType);
        }
    },
});
