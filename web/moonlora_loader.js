/**
 * MoonLoRA Loader - canvas-drawn LoRA rows with a per-LoRA trigger text.
 *
 * Each row serialises itself into the prompt as an undeclared `lora_N` input;
 * the Python side accepts it because MoonLoraLoader uses
 * FlexibleOptionalInputType. Row order in `node.widgets` is the order the
 * backend applies the LoRAs and concatenates their texts.
 */

import { app } from "../../scripts/app.js";
import {
    drawButton,
    drawDivider,
    drawRemoveIcon,
    drawRowBox,
    drawStepper,
    drawToggle,
    fitString,
    fitStringEnd,
    STEPPER_WIDTH,
} from "./lib/canvas_draw.js";
import { clearLoraCache, fetchLoras, showLoraChooser } from "./lib/lora_chooser.js";

const NODE_TYPE = "MoonPack_MoonLoraLoader";

const PROP_SHOW_STRENGTHS = "Show Strengths";
const SHOW_SINGLE = "Single Strength";
const SHOW_SEPARATE = "Separate Model & Clip";

const MARGIN = 10;
const INNER = 5;
const STRENGTH_STEP = 0.05;
const LOW_QUALITY_SCALE = 0.6;
// Horizontal space the remove button occupies, so header labels line up with
// the steppers underneath them.
const REMOVE_SLOT = 20;

const lineHeight = () => LiteGraph.NODE_WIDGET_HEIGHT;
const rowHeight = () => lineHeight() * 2 + 6;

/** ComfyUI degrades its own widgets when zoomed out; match that. */
function isLowQuality() {
    return (app.canvas?.ds?.scale ?? 1) <= LOW_QUALITY_SCALE;
}

function round2(value) {
    return Math.round(value * 100) / 100;
}

function moveArrayItem(array, item, toIndex) {
    const from = array.indexOf(item);
    if (from === -1) return;
    array.splice(from, 1);
    array.splice(toIndex > from ? toIndex - 1 : toIndex, 0, item);
}

// LiteGraph does not hand the originating event to getSlotMenuOptions, so keep
// the last pointer event around for the row context menu to anchor on.
let lastPointerEvent = null;
document.addEventListener("pointerdown", (e) => (lastPointerEvent = e), true);


/* -------------------------------------------------------------------------- */
/* Widget base                                                                */
/* -------------------------------------------------------------------------- */

/**
 * Shared plumbing for canvas widgets: rectangular hit areas in widget-local
 * coordinates, and click-vs-drag discrimination.
 *
 * A hit area is `{bounds: [x, y, w, h], onDown?, onClick?, onDrag?}` where x is
 * node-local and y is relative to the widget's own top edge. onClick only fires
 * if the pointer did not move meaningfully between down and up.
 */
class BaseWidget {
    constructor(name) {
        this.name = name;
        this.type = "custom";
        this.options = {};
        this.hitAreas = {};
        this._active = null;
        this._lastX = 0;
        this._dragged = false;
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
            this._lastX = pos[0];
            this._dragged = false;
            if (!this._active) return false;
            this._active.onDown?.call(this, event, pos, node);
            return true;
        }
        if (type.endsWith("move")) {
            if (!this._active?.onDrag) return false;
            const delta = pos[0] - this._lastX;
            this._lastX = pos[0];
            if (Math.abs(delta) > 0) {
                this._dragged = true;
                this._active.onDrag.call(this, delta, node);
            }
            return true;
        }
        if (type.endsWith("up")) {
            const active = this._active;
            this._active = null;
            if (!active) return false;
            if (!this._dragged) active.onClick?.call(this, event, pos, node);
            this._dragged = false;
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
                    node.moonToggleAllRows();
                    node.setDirtyCanvas(true, false);
                },
            },
        };
    }

    draw(ctx, node, width, posY, height) {
        this.clearBounds();
        if (!node.moonRows().length || isLowQuality()) return;

        const dual = node.properties?.[PROP_SHOW_STRENGTHS] === SHOW_SEPARATE;
        const midY = posY + height * 0.5;
        let posX = MARGIN + INNER;

        ctx.save();
        const [, toggleWidth] = drawToggle(ctx, posX, posY, height, node.moonAllRowsState());
        this.hitAreas.toggleAll.bounds = [posX, 0, toggleWidth, height];
        posX += toggleWidth + INNER;

        ctx.globalAlpha = (app.canvas.editor_alpha ?? 1) * 0.6;
        ctx.fillStyle = LiteGraph.WIDGET_TEXT_COLOR;
        ctx.textAlign = "left";
        ctx.textBaseline = "middle";
        ctx.fillText("Toggle All", posX, midY);

        ctx.textAlign = "center";
        // Column labels sit above the steppers, which are right-aligned and
        // offset by the remove button's slot.
        let rightX = node.size[0] - MARGIN - INNER - REMOVE_SLOT;
        ctx.fillText(dual ? "Clip" : "Strength", rightX - STEPPER_WIDTH * 0.5, midY);
        if (dual) {
            rightX -= STEPPER_WIDTH + INNER;
            ctx.fillText("Model", rightX - STEPPER_WIDTH * 0.5, midY);
        }
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
/* LoRA row                                                                   */
/* -------------------------------------------------------------------------- */

const DEFAULT_ROW = { on: true, lora: null, strength: 1, strengthTwo: null, text: "" };

class LoraRowWidget extends BaseWidget {
    constructor(name) {
        super(name);
        this.value = { ...DEFAULT_ROW };
        this._isMoonLoraRow = true;
        this.hitAreas = {
            toggle: {
                bounds: [0, 0, 0, 0],
                onDown(event, pos, node) {
                    this.value.on = !this.value.on;
                    node.setDirtyCanvas(true, false);
                },
            },
            remove: {
                bounds: [0, 0, 0, 0],
                onClick(event, pos, node) {
                    node.moonRemoveRow(this);
                },
            },
            strengthDec: {
                bounds: [0, 0, 0, 0],
                onClick(event, pos, node) {
                    this.step("strength", -1);
                    node.setDirtyCanvas(true, false);
                },
            },
            strengthInc: {
                bounds: [0, 0, 0, 0],
                onClick(event, pos, node) {
                    this.step("strength", 1);
                    node.setDirtyCanvas(true, false);
                },
            },
            strengthVal: {
                bounds: [0, 0, 0, 0],
                onClick(event, pos, node) {
                    this.promptValue("strength", event, node);
                },
                onDrag(delta, node) {
                    this.scrub("strength", delta);
                    node.setDirtyCanvas(true, false);
                },
            },
            strengthTwoDec: {
                bounds: [0, 0, 0, 0],
                onClick(event, pos, node) {
                    this.step("strengthTwo", -1);
                    node.setDirtyCanvas(true, false);
                },
            },
            strengthTwoInc: {
                bounds: [0, 0, 0, 0],
                onClick(event, pos, node) {
                    this.step("strengthTwo", 1);
                    node.setDirtyCanvas(true, false);
                },
            },
            strengthTwoVal: {
                bounds: [0, 0, 0, 0],
                onClick(event, pos, node) {
                    this.promptValue("strengthTwo", event, node);
                },
                onDrag(delta, node) {
                    this.scrub("strengthTwo", delta);
                    node.setDirtyCanvas(true, false);
                },
            },
            text: {
                bounds: [0, 0, 0, 0],
                onClick(event, pos, node) {
                    this.promptText(event, node);
                },
            },
            // Declared last so the narrower controls above win the hit test.
            lora: {
                bounds: [0, 0, 0, 0],
                onClick(event, pos, node) {
                    this.chooseLora(event, node);
                },
            },
        };
    }

    computeSize(width) {
        return [width, rowHeight()];
    }

    /** Falls back to the model strength so dual mode starts from a sane value. */
    strengthOf(prop) {
        const raw = prop === "strengthTwo"
            ? this.value.strengthTwo ?? this.value.strength
            : this.value.strength;
        const num = Number(raw);
        return Number.isFinite(num) ? num : 1;
    }

    step(prop, direction) {
        this.value[prop] = round2(this.strengthOf(prop) + STRENGTH_STEP * direction);
    }

    scrub(prop, delta) {
        this.value[prop] = round2(this.strengthOf(prop) + delta * 0.01);
    }

    promptValue(prop, event, node) {
        app.canvas.prompt(
            prop === "strengthTwo" ? "Clip strength" : "Strength",
            this.strengthOf(prop),
            (entered) => {
                const num = Number(entered);
                if (Number.isFinite(num)) this.value[prop] = num;
                node.setDirtyCanvas(true, true);
            },
            event,
        );
    }

    promptText(event, node) {
        app.canvas.prompt(
            "Trigger text",
            this.value.text ?? "",
            (entered) => {
                this.value.text = String(entered ?? "");
                node.setDirtyCanvas(true, true);
            },
            event,
        );
    }

    chooseLora(event, node) {
        fetchLoras().then((loras) => {
            showLoraChooser(event, loras, (picked) => {
                this.value.lora = picked;
                node.setDirtyCanvas(true, true);
            });
        });
    }

    draw(ctx, node, width, posY, height) {
        this.clearBounds();

        const dual = node.properties?.[PROP_SHOW_STRENGTHS] === SHOW_SEPARATE;
        const boxX = MARGIN;
        const boxW = node.size[0] - MARGIN * 2;
        const line = lineHeight();
        const line1Local = 2;
        const line2Local = line1Local + line + 2;

        ctx.save();
        drawRowBox(ctx, boxX, posY, boxW, height);

        let posX = boxX + INNER;
        const [, toggleWidth] = drawToggle(ctx, posX, posY + line1Local, line, !!this.value.on);
        this.hitAreas.toggle.bounds = [posX, line1Local, toggleWidth, line];
        posX += toggleWidth + INNER;

        if (isLowQuality()) {
            ctx.restore();
            return;
        }

        const baseAlpha = (app.canvas.editor_alpha ?? 1) * (this.value.on ? 1 : 0.4);
        ctx.globalAlpha = baseAlpha;
        ctx.fillStyle = LiteGraph.WIDGET_TEXT_COLOR;

        let rightX = boxX + boxW - INNER;
        const [removeX, removeW] = drawRemoveIcon(ctx, rightX, posY + line1Local, line);
        this.hitAreas.remove.bounds = [removeX, line1Local, removeW, line];
        rightX = removeX - INNER;

        // Rightmost stepper is clip in dual mode, otherwise the single strength.
        const primary = drawStepper(
            ctx, rightX, posY + line1Local, line,
            dual ? this.strengthOf("strengthTwo") : this.strengthOf("strength"),
        );
        const primaryKey = dual ? "strengthTwo" : "strength";
        this.hitAreas[`${primaryKey}Dec`].bounds = [primary.dec[0], line1Local, primary.dec[1], line];
        this.hitAreas[`${primaryKey}Val`].bounds = [primary.val[0], line1Local, primary.val[1], line];
        this.hitAreas[`${primaryKey}Inc`].bounds = [primary.inc[0], line1Local, primary.inc[1], line];
        rightX = primary.startX - INNER;

        if (dual) {
            const model = drawStepper(ctx, rightX, posY + line1Local, line, this.strengthOf("strength"));
            this.hitAreas.strengthDec.bounds = [model.dec[0], line1Local, model.dec[1], line];
            this.hitAreas.strengthVal.bounds = [model.val[0], line1Local, model.val[1], line];
            this.hitAreas.strengthInc.bounds = [model.inc[0], line1Local, model.inc[1], line];
            rightX = model.startX - INNER;
        }

        ctx.textAlign = "left";
        ctx.textBaseline = "middle";
        const nameWidth = Math.max(0, rightX - posX);
        const hasLora = !!this.value.lora;
        ctx.globalAlpha = baseAlpha * (hasLora ? 1 : 0.5);
        ctx.fillText(
            fitStringEnd(ctx, hasLora ? String(this.value.lora) : "Click to choose a LoRA…", nameWidth),
            posX,
            posY + line1Local + line * 0.5,
        );
        this.hitAreas.lora.bounds = [posX, line1Local, nameWidth, line];

        const textX = boxX + INNER + 12;
        const textWidth = Math.max(0, boxX + boxW - INNER - textX);
        const trigger = String(this.value.text ?? "").trim();
        ctx.globalAlpha = baseAlpha * (trigger ? 0.85 : 0.4);
        ctx.font = `${Math.max(9, LiteGraph.NODE_TEXT_SIZE - 2)}px Arial`;
        ctx.fillText(
            fitString(ctx, trigger || "(no trigger text)", textWidth),
            textX,
            posY + line2Local + line * 0.5,
        );
        this.hitAreas.text.bounds = [textX, line2Local, textWidth, line];

        ctx.restore();
    }

    serializeValue(node) {
        const dual = node?.properties?.[PROP_SHOW_STRENGTHS] === SHOW_SEPARATE;
        const serialized = {
            on: !!this.value.on,
            lora: this.value.lora ?? null,
            strength: this.strengthOf("strength"),
            text: String(this.value.text ?? ""),
        };
        if (dual) serialized.strengthTwo = this.strengthOf("strengthTwo");
        return serialized;
    }
}


/* -------------------------------------------------------------------------- */
/* Node wiring                                                                */
/* -------------------------------------------------------------------------- */

function setupMoonLoraLoader(nodeType) {
    nodeType[`@${PROP_SHOW_STRENGTHS}`] = {
        type: "combo",
        values: [SHOW_SINGLE, SHOW_SEPARATE],
    };

    nodeType.prototype.moonRows = function () {
        return (this.widgets || []).filter((w) => w._isMoonLoraRow);
    };

    /** true / false / null when the rows disagree. */
    nodeType.prototype.moonAllRowsState = function () {
        const rows = this.moonRows();
        if (!rows.length) return false;
        const first = !!rows[0].value.on;
        return rows.every((r) => !!r.value.on === first) ? first : null;
    };

    nodeType.prototype.moonToggleAllRows = function () {
        const next = this.moonAllRowsState() !== true;
        for (const row of this.moonRows()) row.value.on = next;
    };

    nodeType.prototype.moonRemoveDynamicWidgets = function () {
        if (!this.widgets) return;
        this.widgets = this.widgets.filter((w) => !w._isMoonLoraRow && !w._moonChrome);
        this._moonHeader = null;
        this._moonButton = null;
    };

    nodeType.prototype.moonAddChrome = function () {
        this.addCustomWidget(new DividerWidget("moonDividerTop"));
        this._moonHeader = this.addCustomWidget(new HeaderWidget("moonHeader"));
        this.addCustomWidget(new DividerWidget("moonDividerBottom"));
        this._moonButton = this.addCustomWidget(
            new ButtonWidget("moonAddButton", "➕ Add LoRA", (event, node) => {
                fetchLoras().then((loras) => {
                    showLoraChooser(event, loras, (picked) => {
                        node.moonAddRow(picked);
                        node.moonResize();
                    });
                });
            }),
        );
    };

    nodeType.prototype.moonAddRow = function (lora) {
        this._loraCounter = (this._loraCounter || 0) + 1;
        const row = this.addCustomWidget(new LoraRowWidget(`lora_${this._loraCounter}`));
        if (lora) row.value.lora = lora;
        // Rows live above the bottom divider and the Add button.
        const anchor = this.widgets.indexOf(this._moonButton) - 1;
        if (anchor > 0) moveArrayItem(this.widgets, row, anchor);
        return row;
    };

    nodeType.prototype.moonRemoveRow = function (row) {
        const index = this.widgets.indexOf(row);
        if (index === -1) return;
        this.widgets.splice(index, 1);
        this.moonResize();
    };

    nodeType.prototype.moonResize = function () {
        const computed = this.computeSize();
        this.size[0] = Math.max(this.size[0] || 0, computed[0]);
        this.size[1] = computed[1];
        this.setDirtyCanvas(true, true);
    };

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
        onNodeCreated?.apply(this, arguments);
        this.serialize_widgets = true;
        if (!this.properties) this.properties = {};
        if (this.properties[PROP_SHOW_STRENGTHS] === undefined) {
            this.properties[PROP_SHOW_STRENGTHS] = SHOW_SINGLE;
        }
        this._loraCounter = 0;
        this.moonAddChrome();
        this.moonResize();
    };

    // Overriding configure (not onConfigure) so the custom widgets are gone
    // while LiteGraph restores widgets_values by index - otherwise the native
    // `separator` widget at index 0 would be handed a row object.
    const configure = nodeType.prototype.configure;
    nodeType.prototype.configure = function (info) {
        this.moonRemoveDynamicWidgets();
        configure?.apply(this, arguments);

        this.moonAddChrome();
        this._loraCounter = 0;

        let values = info?.widgets_values ?? [];
        if (!Array.isArray(values)) values = Object.values(values);
        for (const value of values) {
            if (value && typeof value === "object" && value.lora !== undefined) {
                const row = this.moonAddRow();
                row.value = { ...DEFAULT_ROW, ...value };
            }
        }
        this.moonResize();
    };

    const onPropertyChanged = nodeType.prototype.onPropertyChanged;
    nodeType.prototype.onPropertyChanged = function (name, value) {
        onPropertyChanged?.apply(this, arguments);
        if (name !== PROP_SHOW_STRENGTHS) return;
        const dual = value === SHOW_SEPARATE;
        for (const row of this.moonRows()) {
            if (dual) {
                if (row.value.strengthTwo == null) row.value.strengthTwo = row.strengthOf("strength");
            } else {
                row.value.strengthTwo = null;
            }
        }
        this.setDirtyCanvas(true, true);
    };

    // Right-clicking a row: LiteGraph asks for the "slot" under the cursor
    // first, so claim the row there and answer with our own menu.
    const getSlotInPosition = nodeType.prototype.getSlotInPosition;
    nodeType.prototype.getSlotInPosition = function (canvasX, canvasY) {
        const slot = getSlotInPosition?.apply(this, arguments);
        if (slot) return slot;
        const localY = canvasY - this.pos[1];
        for (const row of this.moonRows()) {
            if (row.last_y == null) continue;
            if (localY >= row.last_y && localY <= row.last_y + rowHeight()) {
                return { widget: row, output: { type: "MOONLORA ROW" } };
            }
        }
        return slot;
    };

    const getSlotMenuOptions = nodeType.prototype.getSlotMenuOptions;
    nodeType.prototype.getSlotMenuOptions = function (slot) {
        const row = slot?.widget;
        if (!row?._isMoonLoraRow) return getSlotMenuOptions?.apply(this, arguments);

        const node = this;
        const rows = this.moonRows();
        const position = rows.indexOf(row);

        new LiteGraph.ContextMenu(
            [
                {
                    content: `${row.value.on ? "⚫" : "🟢"} Toggle ${row.value.on ? "Off" : "On"}`,
                    callback: () => {
                        row.value.on = !row.value.on;
                        node.setDirtyCanvas(true, false);
                    },
                },
                {
                    content: "✏️ Edit Text",
                    callback: () => row.promptText(lastPointerEvent, node),
                },
                null,
                {
                    content: "⬆️ Move Up",
                    disabled: position <= 0,
                    callback: () => {
                        const target = node.widgets.indexOf(rows[position - 1]);
                        moveArrayItem(node.widgets, row, target);
                        node.setDirtyCanvas(true, true);
                    },
                },
                {
                    content: "⬇️ Move Down",
                    disabled: position === -1 || position >= rows.length - 1,
                    callback: () => {
                        const target = node.widgets.indexOf(rows[position + 1]) + 1;
                        moveArrayItem(node.widgets, row, target);
                        node.setDirtyCanvas(true, true);
                    },
                },
                null,
                {
                    content: "🗑️ Remove",
                    callback: () => node.moonRemoveRow(row),
                },
            ],
            { title: "LORA ROW", event: lastPointerEvent },
        );
        return undefined;
    };

    // ComfyUI's "Refresh Node Definitions" should pick up newly added files.
    nodeType.prototype.refreshComboInNode = function () {
        clearLoraCache();
        fetchLoras(true);
    };
}


app.registerExtension({
    name: "comfyui.moonpack.moonlora-loader",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name === NODE_TYPE) {
            setupMoonLoraLoader(nodeType);
        }
    },
});
