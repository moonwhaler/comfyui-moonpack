/**
 * Prompt Library - a managed multiline text box with saved entries that live
 * entirely on the node, so they serialise into (and travel with) the
 * workflow file. No server-side storage, no HTTP routes.
 *
 * `text` (native multiline widget) is the output. Entries live in
 * `node.properties.entries` rather than a widget: this ComfyUI build's
 * node.serialize()/configure() write/read widget values by array position,
 * but serialize() skips serialize:false widgets by leaving a *hole* at
 * their index while configure() reads back with a *compacted* counter that
 * doesn't know about the hole - so any serialize:false widget positioned
 * before a serializable one shifts every value after it by one on the next
 * load. Properties are serialised as a plain named field instead, sidestepping
 * that entirely. The custom `PromptRowWidget` draws the dropdown and the
 * +/- buttons that manage the entries.
 */

import { app } from "../../scripts/app.js";
import { ARROW_WIDTH, drawArrow, drawButton, drawRowBox, fitString } from "./lib/canvas_draw.js";

const NODE_TYPE = "MoonPack_PromptLibrary";
const AUTOSAVE_DELAY_MS = 600;
const MARGIN = 10;
const BUTTON_WIDTH = 20;
const GAP = 4;

const lineHeight = () => LiteGraph.NODE_WIDGET_HEIGHT;

// LiteGraph does not hand the originating event to app.canvas.prompt calls
// triggered from a custom widget's onClick, so keep the last pointer event
// around to anchor menus/prompts on.
let lastPointerEvent = null;
document.addEventListener("pointerdown", (e) => (lastPointerEvent = e), true);

/**
 * Shared plumbing for canvas widgets: rectangular hit areas in widget-local
 * coordinates, and click-vs-drag discrimination. Duplicated in outline from
 * web/moonlora_loader.js and web/text_builder.js; if a fourth node needs it,
 * it moves to web/lib/.
 */
class BaseWidget {
    constructor(name) {
        this.name = name;
        this.type = "custom";
        this.options = { serialize: false };
        this.hitAreas = {};
        this._active = null;
    }

    computeSize(width) {
        return [width, lineHeight()];
    }

    clearBounds() {
        for (const key of Object.keys(this.hitAreas)) {
            this.hitAreas[key].bounds = [0, 0, 0, 0];
        }
    }

    hitTest(pos) {
        const localY = pos[1] - (this.last_y ?? 0);
        for (const key of Object.keys(this.hitAreas)) {
            const area = this.hitAreas[key];
            const [x, y, w, h] = area.bounds;
            if (w <= 0 || h <= 0) continue;
            if (pos[0] >= x && pos[0] <= x + w && localY >= y && localY <= y + h) {
                return area;
            }
        }
        return null;
    }

    mouse(event, pos, node) {
        const type = String(event?.type || "");
        if (type.endsWith("down")) {
            this._active = this.hitTest(pos);
            if (!this._active) return false;
            this._active.onDown?.call(this, event, pos, node);
            return true;
        }
        if (type.endsWith("up")) {
            const active = this._active;
            this._active = null;
            if (!active) return false;
            active.onClick?.call(this, event, pos, node);
            return true;
        }
        return false;
    }
}

/** The dropdown + +/- row that manages the saved entries. */
class PromptRowWidget extends BaseWidget {
    constructor(name) {
        super(name);
        this.hitAreas = {
            select: {
                bounds: [0, 0, 0, 0],
                onClick(event, pos, node) {
                    node.moonOpenPicker(event);
                },
            },
            add: {
                bounds: [0, 0, 0, 0],
                onClick(event, pos, node) {
                    node.moonNewPrompt(event);
                },
            },
            remove: {
                bounds: [0, 0, 0, 0],
                onClick(event, pos, node) {
                    node.moonDeletePrompt();
                },
            },
        };
    }

    draw(ctx, node, width, posY, height) {
        this.clearBounds();

        const boxX = MARGIN;
        const rightEdge = node.size[0] - MARGIN;

        ctx.save();

        let x = rightEdge - BUTTON_WIDTH;
        drawButton(ctx, x, posY, BUTTON_WIDTH, height, "−");
        this.hitAreas.remove.bounds = [x, 0, BUTTON_WIDTH, height];
        x -= BUTTON_WIDTH + GAP;

        drawButton(ctx, x, posY, BUTTON_WIDTH, height, "+");
        this.hitAreas.add.bounds = [x, 0, BUTTON_WIDTH, height];
        x -= GAP;

        const selectW = Math.max(0, x - boxX);
        this._drawSelect(ctx, node, boxX, posY, selectW, height);
        this.hitAreas.select.bounds = [boxX, 0, selectW, height];

        ctx.restore();
    }

    _drawSelect(ctx, node, x, y, w, h) {
        drawRowBox(ctx, x, y, w, h);

        const label = node._moonSelected || "Select a prompt…";
        const textX = x + 8;
        const caretX = x + w - GAP - ARROW_WIDTH;
        const maxTextWidth = Math.max(0, caretX - textX - GAP);

        ctx.save();
        ctx.fillStyle = LiteGraph.WIDGET_TEXT_COLOR;
        ctx.globalAlpha = node._moonSelected ? 1 : 0.6;
        ctx.textAlign = "left";
        ctx.textBaseline = "middle";
        ctx.fillText(fitString(ctx, label, maxTextWidth), textX, y + h * 0.5);
        ctx.restore();

        drawArrow(ctx, caretX, y, h, 1, !node._moonEntries?.length);
    }
}

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

    /** Reads `properties.entries` into the live `_moonEntries` array. */
    nodeType.prototype.moonLoadEntries = function () {
        const entries = this.properties?.entries;
        this._moonEntries = Array.isArray(entries) ? entries : [];
    };

    /** Writes the live `_moonEntries` array back into `properties.entries`. */
    nodeType.prototype.moonSaveEntries = function () {
        if (!this.properties) this.properties = {};
        this.properties.entries = this._moonEntries;
    };

    nodeType.prototype.moonOpenPicker = function (event) {
        const names = this._moonEntries.map((e) => e.name);
        if (!names.length) return;
        new LiteGraph.ContextMenu(names, {
            // The event this widget's mouse() handler forwards isn't always a
            // real PointerEvent/MouseEvent instance; ContextMenu silently
            // discards anything else and falls back to positioning at (0,0),
            // which reads as "nothing happened". lastPointerEvent is captured
            // straight off the document, so it always passes that check.
            event: lastPointerEvent || event,
            callback: (name) => this.moonSelectEntry(name),
        });
    };

    nodeType.prototype.moonSelectEntry = function (name) {
        const entry = this._moonEntries.find((e) => e.name === name);
        if (!entry) return;
        this._moonSelected = name;
        const text = entry.text ?? "";
        const widget = this.moonTextWidget();
        widget.value = text;
        // Belt and suspenders: go straight to the DOM element too, in case
        // this ComfyUI build's widget.value setter doesn't write through.
        const el = widget.element ?? widget.inputEl;
        if (el) el.value = text;
        this.setDirtyCanvas(true, true);
    };

    nodeType.prototype.moonScheduleAutosave = function () {
        if (!this._moonSelected) return;
        clearTimeout(this._moonSaveTimer);
        this._moonSaveTimer = setTimeout(() => {
            const entry = this._moonEntries.find((e) => e.name === this._moonSelected);
            if (!entry) return;
            entry.text = this.moonCurrentText();
            this.moonSaveEntries();
        }, AUTOSAVE_DELAY_MS);
    };

    nodeType.prototype.moonNewPrompt = function (event) {
        app.canvas.prompt(
            "New prompt name",
            "",
            (entered) => {
                const name = String(entered ?? "").trim();
                if (!name) return;
                if (this._moonEntries.some((e) => e.name === name)) {
                    alert(`An entry named '${name}' already exists.`);
                    return;
                }
                this._moonEntries.push({ name, text: this.moonCurrentText() });
                this.moonSaveEntries();
                this._moonSelected = name;
                this.setDirtyCanvas(true, true);
            },
            lastPointerEvent || event,
        );
    };

    nodeType.prototype.moonDeletePrompt = function () {
        const name = this._moonSelected;
        if (!name) {
            alert("No prompt is selected.");
            return;
        }
        if (!confirm(`Delete '${name}' from the prompt library? This cannot be undone.`)) return;
        this._moonEntries = this._moonEntries.filter((e) => e.name !== name);
        this._moonSelected = null;
        this.moonSaveEntries();
        this.setDirtyCanvas(true, true);
    };

    nodeType.prototype.moonAddRowWidget = function () {
        const row = new PromptRowWidget("moonPromptRow");
        this.addCustomWidget(row);
        this.widgets.splice(this.widgets.indexOf(row), 1);
        this.widgets.unshift(row);
    };

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
        onNodeCreated?.apply(this, arguments);
        this.serialize_widgets = true;
        this._moonSelected = null;
        if (!this.properties) this.properties = {};

        this.moonLoadEntries();
        this.moonAddRowWidget();

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

        this.setDirtyCanvas(true, true);
    };

    // NOT removing the row widget here (unlike similar MoonPack nodes): this
    // node.configure() writes/reads widgets_values by array position keyed
    // off each widget's own `.serialize` flag, and the row widget never sets
    // that flag (only the ineffective `options.serialize`), so it quietly
    // consumes slot 0 on both save and load, keeping `text` correctly
    // aligned at slot 1. Removing the row before calling through would only
    // consume slot 0 on the load side, shifting `text` onto the wrong value.
    const configure = nodeType.prototype.configure;
    nodeType.prototype.configure = function (info) {
        configure?.apply(this, arguments);
        this.moonLoadEntries();
        this._moonSelected = null;
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
