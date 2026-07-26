/**
 * Text Builder - stacked multiline text blocks joined by a separator.
 *
 * Each block is two widgets kept adjacent in `node.widgets`: a canvas-drawn
 * control strip serialising as `ctl_N` ({on}) and a native ComfyUI multiline
 * STRING widget serialising as `entry_N`. The Python side accepts both because
 * TextBuilder uses FlexibleOptionalInputType. Widget order - not the numeric
 * suffix - is the order the backend joins the texts in, so the pair always
 * moves, and is removed, as a unit.
 */

import { app } from "../../scripts/app.js";
import { ComfyWidgets } from "../../scripts/widgets.js";
import {
    ARROW_WIDTH,
    drawArrow,
    drawButton,
    drawDivider,
    drawRemoveIcon,
    drawRowBox,
    drawToggle,
} from "./lib/canvas_draw.js";

const NODE_TYPE = "MoonPack_TextBuilder";

const MARGIN = 10;
const INNER = 5;
const LOW_QUALITY_SCALE = 0.6;

const lineHeight = () => LiteGraph.NODE_WIDGET_HEIGHT;

/** ComfyUI degrades its own widgets when zoomed out; match that. */
function isLowQuality() {
    return (app.canvas?.ds?.scale ?? 1) <= LOW_QUALITY_SCALE;
}

// LiteGraph does not hand the originating event to getSlotMenuOptions, so keep
// the last pointer event around for the block context menu to anchor on.
let lastPointerEvent = null;
document.addEventListener("pointerdown", (e) => (lastPointerEvent = e), true);


/* -------------------------------------------------------------------------- */
/* Widget base                                                                */
/* -------------------------------------------------------------------------- */

/**
 * Shared plumbing for canvas widgets: rectangular hit areas in widget-local
 * coordinates. A hit area is `{bounds: [x, y, w, h], onDown?, onClick?}` where
 * x is node-local and y is relative to the widget's own top edge.
 */
class BaseWidget {
    constructor(name) {
        this.name = name;
        this.type = "custom";
        this.options = {};
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
            const [x, y, w, h] = this.hitAreas[key].bounds;
            if (w <= 0 || h <= 0) continue;
            if (pos[0] >= x && pos[0] <= x + w && localY >= y && localY <= y + h) {
                return this.hitAreas[key];
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


/* -------------------------------------------------------------------------- */
/* Chrome widgets                                                             */
/* -------------------------------------------------------------------------- */

class DividerWidget extends BaseWidget {
    constructor(name) {
        super(name);
        this.value = null;
        this.options = { serialize: false };
        this._moonChrome = true;
    }

    computeSize(width) {
        return [width, 6];
    }

    draw(ctx, node, width, posY) {
        drawDivider(ctx, MARGIN, posY + 3, node.size[0] - MARGIN * 2);
    }
}

class HeaderWidget extends BaseWidget {
    constructor(name) {
        super(name);
        this.value = null;
        this.options = { serialize: false };
        this._moonChrome = true;
        this.hitAreas = {
            toggleAll: {
                bounds: [0, 0, 0, 0],
                onClick(event, pos, node) {
                    node.moonToggleAllEntries();
                    node.setDirtyCanvas(true, false);
                },
            },
        };
    }

    draw(ctx, node, width, posY, height) {
        this.clearBounds();
        if (!node.moonEntries().length || isLowQuality()) return;

        let posX = MARGIN + INNER;
        ctx.save();
        const [, toggleWidth] = drawToggle(ctx, posX, posY, height, node.moonAllEntriesState());
        this.hitAreas.toggleAll.bounds = [posX, 0, toggleWidth, height];
        posX += toggleWidth + INNER;

        ctx.globalAlpha = (app.canvas.editor_alpha ?? 1) * 0.6;
        ctx.fillStyle = LiteGraph.WIDGET_TEXT_COLOR;
        ctx.textAlign = "left";
        ctx.textBaseline = "middle";
        ctx.fillText("Toggle All", posX, posY + height * 0.5);
        ctx.restore();
    }
}

class ButtonWidget extends BaseWidget {
    constructor(name, label, onPress) {
        super(name);
        this.value = null;
        this.label = label;
        this.options = { serialize: false };
        this._moonChrome = true;
        this.hitAreas = {
            button: {
                bounds: [0, 0, 0, 0],
                onClick(event, pos, node) {
                    onPress(event, node);
                },
            },
        };
    }

    computeSize(width) {
        return [width, lineHeight() + 4];
    }

    draw(ctx, node, width, posY, height) {
        this.clearBounds();
        const x = MARGIN * 2;
        const w = node.size[0] - MARGIN * 4;
        drawButton(ctx, x, posY + 2, w, height - 4, this.label);
        this.hitAreas.button.bounds = [x, 2, w, height - 4];
    }
}


/* -------------------------------------------------------------------------- */
/* Block control strip                                                        */
/* -------------------------------------------------------------------------- */

const DEFAULT_ENTRY = { on: true };

class EntryControlWidget extends BaseWidget {
    constructor(name) {
        super(name);
        this.value = { ...DEFAULT_ENTRY };
        this._isMoonEntry = true;
        // Set by moonAddEntry; the textarea this strip controls.
        this.textWidget = null;
        this.hitAreas = {
            toggle: {
                bounds: [0, 0, 0, 0],
                onDown(event, pos, node) {
                    this.value.on = !this.value.on;
                    node.setDirtyCanvas(true, false);
                },
            },
            moveUp: {
                bounds: [0, 0, 0, 0],
                onClick(event, pos, node) {
                    node.moonMoveEntry(this, -1);
                },
            },
            moveDown: {
                bounds: [0, 0, 0, 0],
                onClick(event, pos, node) {
                    node.moonMoveEntry(this, 1);
                },
            },
            remove: {
                bounds: [0, 0, 0, 0],
                onClick(event, pos, node) {
                    node.moonRemoveEntry(this);
                },
            },
        };
    }

    draw(ctx, node, width, posY, height) {
        this.clearBounds();

        const boxX = MARGIN;
        const boxW = node.size[0] - MARGIN * 2;

        ctx.save();
        drawRowBox(ctx, boxX, posY, boxW, height);

        let posX = boxX + INNER;
        const [, toggleWidth] = drawToggle(ctx, posX, posY, height, !!this.value.on);
        this.hitAreas.toggle.bounds = [posX, 0, toggleWidth, height];
        posX += toggleWidth + INNER;

        if (isLowQuality()) {
            ctx.restore();
            return;
        }

        const entries = node.moonEntries();
        const position = entries.indexOf(this);

        ctx.globalAlpha = (app.canvas.editor_alpha ?? 1) * (this.value.on ? 1 : 0.4);
        ctx.fillStyle = LiteGraph.WIDGET_TEXT_COLOR;
        ctx.textAlign = "left";
        ctx.textBaseline = "middle";
        ctx.fillText(`#${position + 1}`, posX, posY + height * 0.5);

        let rightX = boxX + boxW - INNER;
        const [removeX, removeW] = drawRemoveIcon(ctx, rightX, posY, height);
        this.hitAreas.remove.bounds = [removeX, 0, removeW, height];
        rightX = removeX - INNER * 2;

        const downX = rightX - ARROW_WIDTH;
        drawArrow(ctx, downX, posY, height, 1, position >= entries.length - 1);
        this.hitAreas.moveDown.bounds = [downX, 0, ARROW_WIDTH, height];

        const upX = downX - ARROW_WIDTH;
        drawArrow(ctx, upX, posY, height, -1, position <= 0);
        this.hitAreas.moveUp.bounds = [upX, 0, ARROW_WIDTH, height];

        ctx.restore();
    }

    serializeValue() {
        return { on: !!this.value.on };
    }
}


/* -------------------------------------------------------------------------- */
/* Node wiring                                                                */
/* -------------------------------------------------------------------------- */

function setupTextBuilder(nodeType) {
    nodeType.prototype.moonEntries = function () {
        return (this.widgets || []).filter((w) => w._isMoonEntry);
    };

    /** true / false / null when the blocks disagree. */
    nodeType.prototype.moonAllEntriesState = function () {
        const entries = this.moonEntries();
        if (!entries.length) return false;
        const first = !!entries[0].value.on;
        return entries.every((e) => !!e.value.on === first) ? first : null;
    };

    nodeType.prototype.moonToggleAllEntries = function () {
        const next = this.moonAllEntriesState() !== true;
        for (const entry of this.moonEntries()) entry.value.on = next;
    };

    nodeType.prototype.moonRemoveDynamicWidgets = function () {
        if (!this.widgets) return;
        // The textareas are DOM elements; they leak unless torn down explicitly.
        for (const widget of this.widgets) {
            if (widget._isMoonEntryText) widget.onRemove?.();
        }
        this.widgets = this.widgets.filter(
            (w) => !w._isMoonEntry && !w._isMoonEntryText && !w._moonChrome,
        );
        this._moonHeader = null;
        this._moonButton = null;
        this._moonDividerBottom = null;
    };

    nodeType.prototype.moonAddChrome = function () {
        this.addCustomWidget(new DividerWidget("moonDividerTop"));
        this._moonHeader = this.addCustomWidget(new HeaderWidget("moonHeader"));
        this._moonDividerBottom = this.addCustomWidget(new DividerWidget("moonDividerBottom"));
        this._moonButton = this.addCustomWidget(
            new ButtonWidget("moonAddButton", "➕ Add Text", (event, node) => {
                node.moonAddEntry("");
                node.moonResize();
            }),
        );
    };

    nodeType.prototype.moonAddEntry = function (text) {
        this._entryCounter = (this._entryCounter || 0) + 1;
        const suffix = this._entryCounter;

        const ctl = new EntryControlWidget(`ctl_${suffix}`);
        this.addCustomWidget(ctl);

        const created = ComfyWidgets.STRING(
            this, `entry_${suffix}`, ["STRING", { multiline: true }], app,
        );
        const textWidget = created?.widget ?? this.widgets[this.widgets.length - 1];
        textWidget._isMoonEntryText = true;
        textWidget.value = typeof text === "string" ? text : "";
        ctl.textWidget = textWidget;

        // Both were appended at the end; move the pair above the bottom divider
        // so the chrome stays put.
        const pair = this.widgets.splice(this.widgets.length - 2, 2);
        const anchor = this.widgets.indexOf(this._moonDividerBottom);
        this.widgets.splice(anchor === -1 ? this.widgets.length : anchor, 0, ...pair);

        return ctl;
    };

    nodeType.prototype.moonRemoveEntry = function (ctl) {
        const index = this.widgets.indexOf(ctl);
        if (index === -1) return;
        const [, textWidget] = this.widgets.splice(index, 2);
        textWidget?.onRemove?.();
        this.moonResize();
    };

    /** Moves a block one position up (-1) or down (1), textarea included. */
    nodeType.prototype.moonMoveEntry = function (ctl, delta) {
        const entries = this.moonEntries();
        const position = entries.indexOf(ctl);
        const target = position + delta;
        if (position === -1 || target < 0 || target >= entries.length) return;

        const from = this.widgets.indexOf(ctl);
        const pair = this.widgets.splice(from, 2);
        const neighbour = this.widgets.indexOf(entries[target]);
        // Moving down has to clear the neighbour's own two widgets.
        this.widgets.splice(delta < 0 ? neighbour : neighbour + 2, 0, ...pair);
        this.setDirtyCanvas(true, true);
    };

    nodeType.prototype.moonResize = function () {
        const computed = this.computeSize();
        // Grow only: shrinking would squash textareas the user widened.
        this.size[0] = Math.max(this.size[0] || 0, computed[0]);
        this.size[1] = Math.max(this.size[1] || 0, computed[1]);
        this.setDirtyCanvas(true, true);
    };

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
        onNodeCreated?.apply(this, arguments);
        this.serialize_widgets = true;
        this._entryCounter = 0;
        this.moonAddChrome();
        // A fresh node with zero blocks looks broken; start with one.
        this.moonAddEntry("");
        this.moonResize();
    };
}


app.registerExtension({
    name: "comfyui.moonpack.text-builder",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name === NODE_TYPE) {
            setupTextBuilder(nodeType);
        }
    },
});
