/**
 * Prompt Library - a managed multiline text box backed by a shared,
 * server-side JSON library (see prompt_library_routes.py).
 *
 * The node's native `text` widget IS the output; `entry_name` is a hidden
 * native widget that just remembers which library entry is loaded, so
 * reopening the workflow shows the right picker label. Everything else
 * (description, tags) lives server-side and is fetched fresh when needed.
 */

import { app } from "../../scripts/app.js";
import { drawButton } from "./lib/canvas_draw.js";
import {
    clearPromptCache,
    createPromptEntry,
    deletePromptEntry,
    fetchPromptEntries,
    showPromptChooser,
    showPromptEditDialog,
    updatePromptEntry,
} from "./lib/prompt_chooser.js";

const NODE_TYPE = "MoonPack_PromptLibrary";
const MARGIN = 10;

const lineHeight = () => LiteGraph.NODE_WIDGET_HEIGHT;

let lastPointerEvent = null;
document.addEventListener("pointerdown", (e) => (lastPointerEvent = e), true);

/** A full-width clickable button row; fires `onPress` on pointer-up inside it. */
class ClickWidget {
    constructor(name, getLabel, onPress) {
        this.name = name;
        this.type = "custom";
        this.value = null;
        this.options = { serialize: false };
        this.getLabel = getLabel;
        this.onPress = onPress;
        this._bounds = [0, 0, 0, 0];
        this._down = false;
        // Not part of INPUT_TYPES: must be stripped before LiteGraph's default
        // configure() restores widgets_values by raw index, and re-added after.
        this._moonExtra = true;
    }

    computeSize(width) {
        return [width, lineHeight() + 4];
    }

    draw(ctx, node, width, posY, height) {
        const x = MARGIN;
        const w = node.size[0] - MARGIN * 2;
        drawButton(ctx, x, posY + 2, w, height - 4, this.getLabel(node));
        this._bounds = [x, posY + 2, w, height - 4];
    }

    _hit(pos) {
        const localY = pos[1] - (this.last_y ?? 0);
        const [x, y, w, h] = this._bounds;
        return pos[0] >= x && pos[0] <= x + w && localY >= y && localY <= y + h;
    }

    mouse(event, pos, node) {
        const type = String(event?.type || "");
        if (type.endsWith("down")) {
            this._down = this._hit(pos);
            return this._down;
        }
        if (type.endsWith("up")) {
            const wasDown = this._down;
            this._down = false;
            if (wasDown && this._hit(pos)) this.onPress(event, node);
            return wasDown;
        }
        return false;
    }
}

/** Hides a native widget from layout/drawing while keeping it serialized. */
function hideWidget(widget) {
    widget.computeSize = () => [0, -4];
    widget.draw = () => {};
}

/** Inserts the picker before `text` and appends the action buttons at the end. */
function addExtraWidgets(node) {
    const picker = new ClickWidget(
        "moonPicker",
        (n) => n.moonEntryName() || "📋 Pick a Saved Prompt…",
        (event, n) => n.moonOpenChooser(event ?? lastPointerEvent),
    );
    const textIndex = node.widgets.findIndex((w) => w.name === "text");
    node.widgets.splice(textIndex === -1 ? 0 : textIndex, 0, picker);

    node.widgets.push(
        new ClickWidget("moonSaveAsNew", () => "💾 Save as New",
            (event, n) => n.moonSaveAsNew()),
        new ClickWidget("moonUpdateSelected", () => "✏️ Update Selected",
            (event, n) => n.moonUpdateSelected()),
        new ClickWidget("moonDeleteSelected", () => "🗑️ Delete Selected",
            (event, n) => n.moonDeleteSelected()),
    );
}

function setupPromptLibrary(nodeType) {
    nodeType.prototype.moonEntryName = function () {
        const widget = this.widgets?.find((w) => w.name === "entry_name");
        return widget ? String(widget.value ?? "") : "";
    };

    nodeType.prototype.moonSetEntryName = function (name) {
        const widget = this.widgets?.find((w) => w.name === "entry_name");
        if (widget) widget.value = name;
    };

    nodeType.prototype.moonTextWidget = function () {
        return this.widgets?.find((w) => w.name === "text");
    };

    nodeType.prototype.moonOpenChooser = function (event) {
        fetchPromptEntries().then((entries) => {
            showPromptChooser(event, entries, (entry) => {
                this.moonTextWidget().value = entry.text ?? "";
                this.moonSetEntryName(entry.name ?? "");
                this.setDirtyCanvas(true, true);
            });
        });
    };

    nodeType.prototype.moonSaveAsNew = function () {
        showPromptEditDialog(
            { title: "Save as New Prompt" },
            ({ name, description, tags }) => {
                if (!name) return Promise.reject(new Error("Name is required."));
                return createPromptEntry({
                    name, description, tags, text: this.moonTextWidget().value ?? "",
                }).then(() => {
                    this.moonSetEntryName(name);
                    this.setDirtyCanvas(true, true);
                });
            },
        );
    };

    nodeType.prototype.moonUpdateSelected = function () {
        const name = this.moonEntryName();
        if (!name) {
            alert("No prompt is loaded. Use 'Save as New' first.");
            return;
        }
        fetchPromptEntries(true).then((entries) => {
            const entry = entries.find((e) => e.name === name);
            if (!entry) {
                alert(`'${name}' no longer exists in the library. Use 'Save as New' instead.`);
                return;
            }
            showPromptEditDialog(
                {
                    title: "Update Prompt",
                    name: entry.name,
                    description: entry.description,
                    tags: entry.tags,
                    lockName: true,
                },
                ({ description, tags }) =>
                    updatePromptEntry(name, {
                        description, tags, text: this.moonTextWidget().value ?? "",
                    }),
            );
        });
    };

    nodeType.prototype.moonDeleteSelected = function () {
        const name = this.moonEntryName();
        if (!name) {
            alert("No prompt is loaded.");
            return;
        }
        if (!confirm(`Delete '${name}' from the prompt library? This cannot be undone.`)) return;
        deletePromptEntry(name)
            .then(() => {
                this.moonSetEntryName("");
                this.setDirtyCanvas(true, true);
            })
            .catch((err) => alert(err?.message || String(err)));
    };

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
        onNodeCreated?.apply(this, arguments);
        this.serialize_widgets = true;

        const entryNameWidget = this.widgets?.find((w) => w.name === "entry_name");
        if (entryNameWidget) hideWidget(entryNameWidget);

        addExtraWidgets(this);

        clearPromptCache();
        this.computeSize();
        this.setDirtyCanvas(true, true);
    };

    // Default configure() restores widgets_values onto this.widgets by raw
    // index; the picker/button widgets aren't in that saved array, so they
    // must be pulled out first and reinserted after the real values land.
    const configure = nodeType.prototype.configure;
    nodeType.prototype.configure = function (info) {
        this.widgets = (this.widgets || []).filter((w) => !w._moonExtra);
        configure?.apply(this, arguments);
        addExtraWidgets(this);
        this.computeSize();
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
