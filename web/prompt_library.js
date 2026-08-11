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

    nodeType.prototype.moonLoadEntry = function (name) {
        const entry = (this._moonEntries || []).find((e) => e.name === name);
        if (entry) this.moonTextWidget().value = entry.text ?? "";
        this.setDirtyCanvas(true, true);
    };

    nodeType.prototype.moonScheduleAutosave = function () {
        const name = this.moonComboWidget()?.value;
        if (!name) return;
        clearTimeout(this._moonSaveTimer);
        this._moonSaveTimer = setTimeout(() => {
            updatePromptEntry(name, { text: this.moonTextWidget().value ?? "" }).catch((err) => {
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
                createPromptEntry({ name, text: this.moonTextWidget().value ?? "" })
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

        const combo = this.addWidget("combo", "prompt", "", (name) => this.moonLoadEntry(name), {
            values: [],
        });
        this.widgets.splice(this.widgets.indexOf(combo), 1);
        this.widgets.unshift(combo);

        this.addWidget("button", "New Prompt", null, () => this.moonNewPrompt());
        this.addWidget("button", "Delete Prompt", null, () => this.moonDeletePrompt());

        const textWidget = this.moonTextWidget();
        const originalCallback = textWidget.callback;
        const node = this;
        textWidget.callback = function (...args) {
            originalCallback?.apply(this, args);
            node.moonScheduleAutosave();
        };

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
