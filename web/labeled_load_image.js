/**
 * Load Image (Labeled) - adds a color-swatch widget for background_color/
 * text_color (native STRING widgets replaced with <input type=color> DOM
 * widgets), an Edit Crop button that opens a maximized popup for dragging
 * out the crop_x/crop_y/crop_width/crop_height region on the raw source
 * image (via /moonpack/crop_source), and a Preview button that renders the
 * exact composited result (crop, label bar, arrow, border) via the backend's
 * /moonpack/label_preview route, so the thumbnail matches what execution
 * will actually output.
 */

import { app } from "../../scripts/app.js";
import { drawButton } from "./lib/canvas_draw.js";

const NODE_TYPE = "MoonPack_LabeledLoadImage";
const COLOR_WIDGETS = [
    { name: "background_color", fallback: "#000000" },
    { name: "text_color", fallback: "#ffffff" },
];
const MIN_CROP_PX = 8;
const HANDLE_HIT_PX = 10;

function replaceWithColorWidget(node, name, fallback) {
    const index = node.widgets.findIndex((w) => w.name === name);
    const initial = index !== -1 ? (node.widgets[index].value || fallback) : fallback;
    if (index !== -1) node.widgets.splice(index, 1);

    const input = document.createElement("input");
    input.type = "color";
    input.value = initial;
    Object.assign(input.style, {
        width: "100%", height: "20px", border: "none", padding: "0", background: "none",
    });

    const widget = node.addDOMWidget(name, "COLORPICKER", input, {
        getValue: () => input.value,
        setValue: (v) => { input.value = v; },
        serialize: true,
    });
    widget.value = initial;
    input.addEventListener("input", () => {
        widget.value = input.value;
        node.setDirtyCanvas(true, true);
    });
    return widget;
}

class PreviewButtonWidget {
    constructor() {
        this.name = "moonPreviewButton";
        this.type = "custom";
        this.value = null;
        this.options = { serialize: false };
        this.hitArea = [0, 0, 0, 0];
    }

    computeSize(width) {
        return [width, LiteGraph.NODE_WIDGET_HEIGHT + 4];
    }

    draw(ctx, node, width, posY, height) {
        const x = 10;
        const w = node.size[0] - 20;
        drawButton(ctx, x, posY + 2, w, height - 4, "🔍 Preview");
        this.hitArea = [x, posY + 2, w, height - 4];
    }

    mouse(event, pos, node) {
        if (String(event?.type || "").endsWith("up")) {
            const [x, y, w, h] = this.hitArea;
            if (pos[0] >= x && pos[0] <= x + w && pos[1] >= y && pos[1] <= y + h) {
                runPreview(node);
                return true;
            }
        }
        return false;
    }
}

class EditCropButtonWidget {
    constructor() {
        this.name = "moonEditCropButton";
        this.type = "custom";
        this.value = null;
        this.options = { serialize: false };
        this.hitArea = [0, 0, 0, 0];
    }

    computeSize(width) {
        return [width, LiteGraph.NODE_WIDGET_HEIGHT + 4];
    }

    draw(ctx, node, width, posY, height) {
        const x = 10;
        const w = node.size[0] - 20;
        drawButton(ctx, x, posY + 2, w, height - 4, "✂ Edit Crop");
        this.hitArea = [x, posY + 2, w, height - 4];
    }

    mouse(event, pos, node) {
        if (String(event?.type || "").endsWith("up")) {
            const [x, y, w, h] = this.hitArea;
            if (pos[0] >= x && pos[0] <= x + w && pos[1] >= y && pos[1] <= y + h) {
                openCropEditor(node);
                return true;
            }
        }
        return false;
    }
}

function widgetValue(node, name, fallback) {
    const w = node.widgets?.find((w) => w.name === name);
    return w ? w.value : fallback;
}

function showError(message) {
    console.error("[MoonPack] Load Image (Labeled) preview failed:", message);
    const toast = app.extensionManager?.toast;
    if (toast?.add) {
        toast.add({ severity: "error", summary: "Label preview failed", detail: message, life: 4000 });
    } else {
        alert(`Label preview failed: ${message}`);
    }
}

async function runPreview(node) {
    const body = {
        image: widgetValue(node, "image", ""),
        text: widgetValue(node, "text", ""),
        text_position: widgetValue(node, "text_position", "top"),
        show_label: !!widgetValue(node, "show_label", true),
        show_arrow: !!widgetValue(node, "show_arrow", true),
        background_color: widgetValue(node, "background_color", "#000000"),
        text_color: widgetValue(node, "text_color", "#ffffff"),
        border_width: Number(widgetValue(node, "border_width", 0)) || 0,
        crop_x: Number(widgetValue(node, "crop_x", 0)) || 0,
        crop_y: Number(widgetValue(node, "crop_y", 0)) || 0,
        crop_width: Number(widgetValue(node, "crop_width", 0)) || 0,
        crop_height: Number(widgetValue(node, "crop_height", 0)) || 0,
    };

    if (!body.image) {
        showError("no image selected yet.");
        return;
    }

    let response;
    try {
        response = await fetch("/moonpack/label_preview", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
    } catch (e) {
        showError(String(e));
        return;
    }

    if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        showError(detail.error || `HTTP ${response.status}`);
        return;
    }

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const img = new Image();
    img.onload = () => {
        if (node._moonPreviewUrl) URL.revokeObjectURL(node._moonPreviewUrl);
        node._moonPreviewUrl = url;
        node.imgs = [img];
        node.setDirtyCanvas(true, true);
    };
    img.src = url;
}

function setWidgetValue(node, name, value) {
    const w = node.widgets?.find((w) => w.name === name);
    if (!w) return;
    w.value = value;
}

/** Clamps a rect's corners into the image bounds, allowing it to shrink. */
function clampRect(rect, naturalW, naturalH) {
    let x1 = rect.x;
    let y1 = rect.y;
    let x2 = rect.x + rect.w;
    let y2 = rect.y + rect.h;
    x1 = Math.max(0, x1);
    y1 = Math.max(0, y1);
    x2 = Math.min(naturalW, x2);
    y2 = Math.min(naturalH, y2);
    let w = Math.max(MIN_CROP_PX, x2 - x1);
    let h = Math.max(MIN_CROP_PX, y2 - y1);
    x1 = Math.min(x1, naturalW - w);
    y1 = Math.min(y1, naturalH - h);
    return { x: x1, y: y1, w, h };
}

/** Translates a rect without letting it shrink, clamped to image bounds. */
function clampMove(x, y, w, h, naturalW, naturalH) {
    return {
        x: Math.max(0, Math.min(x, naturalW - w)),
        y: Math.max(0, Math.min(y, naturalH - h)),
        w, h,
    };
}

function currentCropRect(node, naturalW, naturalH) {
    const x = Number(widgetValue(node, "crop_x", 0)) || 0;
    const y = Number(widgetValue(node, "crop_y", 0)) || 0;
    const wRaw = Number(widgetValue(node, "crop_width", 0)) || 0;
    const hRaw = Number(widgetValue(node, "crop_height", 0)) || 0;
    const w = wRaw > 0 ? wRaw : naturalW - x;
    const h = hRaw > 0 ? hRaw : naturalH - y;
    return clampRect({ x, y, w, h }, naturalW, naturalH);
}

function handlePoints(x, y, w, h) {
    return [
        ["nw", x, y], ["n", x + w / 2, y], ["ne", x + w, y],
        ["w", x, y + h / 2], ["e", x + w, y + h / 2],
        ["sw", x, y + h], ["s", x + w / 2, y + h], ["se", x + w, y + h],
    ];
}

function cursorForMode(mode) {
    switch (mode) {
        case "nw": case "se": return "nwse-resize";
        case "ne": case "sw": return "nesw-resize";
        case "n": case "s": return "ns-resize";
        case "e": case "w": return "ew-resize";
        case "move": return "move";
        default: return "crosshair";
    }
}

function computeDragRect(mode, startRect, anchorImg, curX, curY, naturalW, naturalH) {
    if (mode === "move") {
        const dx = curX - anchorImg.x;
        const dy = curY - anchorImg.y;
        return clampMove(startRect.x + dx, startRect.y + dy, startRect.w, startRect.h, naturalW, naturalH);
    }
    if (mode === "new") {
        const x = Math.min(anchorImg.x, curX);
        const y = Math.min(anchorImg.y, curY);
        return clampRect({ x, y, w: Math.abs(curX - anchorImg.x), h: Math.abs(curY - anchorImg.y) }, naturalW, naturalH);
    }
    let x = startRect.x, y = startRect.y;
    let x2 = startRect.x + startRect.w, y2 = startRect.y + startRect.h;
    if (mode.includes("w")) x = curX;
    if (mode.includes("e")) x2 = curX;
    if (mode.includes("n")) y = curY;
    if (mode.includes("s")) y2 = curY;
    return clampRect({ x: Math.min(x, x2), y: Math.min(y, y2), w: Math.abs(x2 - x), h: Math.abs(y2 - y) }, naturalW, naturalH);
}

async function openCropEditor(node) {
    const imageValue = widgetValue(node, "image", "");
    if (!imageValue) {
        showError("no image selected yet.");
        return;
    }

    let response;
    try {
        response = await fetch("/moonpack/crop_source", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ image: imageValue }),
        });
    } catch (e) {
        showError(String(e));
        return;
    }

    if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        showError(detail.error || `HTTP ${response.status}`);
        return;
    }

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const img = new Image();
    try {
        await new Promise((resolve, reject) => {
            img.onload = resolve;
            img.onerror = () => reject(new Error("could not decode source image"));
            img.src = url;
        });
    } catch (e) {
        URL.revokeObjectURL(url);
        showError(String(e));
        return;
    }

    showCropModal(node, img, url);
}

function showCropModal(node, img, url) {
    const naturalW = img.naturalWidth;
    const naturalH = img.naturalHeight;
    let rect = currentCropRect(node, naturalW, naturalH);
    let drag = null;

    const overlay = document.createElement("div");
    Object.assign(overlay.style, {
        position: "fixed", inset: "0", background: "rgba(0,0,0,0.75)",
        display: "flex", alignItems: "center", justifyContent: "center", zIndex: "10000",
    });

    const panel = document.createElement("div");
    Object.assign(panel.style, {
        background: "#222", border: "1px solid #444", borderRadius: "8px", padding: "12px",
        display: "flex", flexDirection: "column", gap: "8px", maxWidth: "92vw", maxHeight: "92vh",
    });

    const title = document.createElement("div");
    title.textContent = "Drag to select the crop region. Drag a handle to resize, drag inside to move.";
    Object.assign(title.style, { color: "#ccc", fontSize: "12px" });

    const canvas = document.createElement("canvas");
    Object.assign(canvas.style, { cursor: "crosshair", display: "block" });

    const maxW = Math.max(200, window.innerWidth * 0.85);
    const maxH = Math.max(200, window.innerHeight * 0.72);
    const displayScale = Math.min(1, maxW / naturalW, maxH / naturalH);
    const displayW = Math.round(naturalW * displayScale);
    const displayH = Math.round(naturalH * displayScale);
    const dpr = window.devicePixelRatio || 1;
    canvas.width = displayW * dpr;
    canvas.height = displayH * dpr;
    canvas.style.width = `${displayW}px`;
    canvas.style.height = `${displayH}px`;
    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);

    const readout = document.createElement("div");
    Object.assign(readout.style, { color: "#9c9", fontSize: "12px", fontFamily: "monospace" });

    const buttons = document.createElement("div");
    Object.assign(buttons.style, { display: "flex", justifyContent: "flex-end", gap: "8px" });

    function makeButton(label) {
        const b = document.createElement("button");
        b.textContent = label;
        Object.assign(b.style, {
            padding: "6px 14px", borderRadius: "4px", border: "1px solid #555",
            background: "#333", color: "#eee", cursor: "pointer",
        });
        return b;
    }
    const resetBtn = makeButton("Reset");
    const cancelBtn = makeButton("Cancel");
    const applyBtn = makeButton("Apply");
    Object.assign(applyBtn.style, { background: "#3d7fbf", borderColor: "#3d7fbf" });

    buttons.append(resetBtn, cancelBtn, applyBtn);
    panel.append(title, canvas, readout, buttons);
    overlay.append(panel);
    document.body.append(overlay);

    const toScreen = (v) => v * displayScale;
    const toImage = (v) => v / displayScale;

    function eventPos(e) {
        const r = canvas.getBoundingClientRect();
        return [e.clientX - r.left, e.clientY - r.top];
    }

    function handleAt(px, py) {
        const rx = toScreen(rect.x), ry = toScreen(rect.y);
        const rw = toScreen(rect.w), rh = toScreen(rect.h);
        for (const [name, hx, hy] of handlePoints(rx, ry, rw, rh)) {
            if (Math.abs(px - hx) <= HANDLE_HIT_PX && Math.abs(py - hy) <= HANDLE_HIT_PX) return name;
        }
        if (px >= rx && px <= rx + rw && py >= ry && py <= ry + rh) return "move";
        return null;
    }

    function redraw() {
        ctx.clearRect(0, 0, displayW, displayH);
        ctx.drawImage(img, 0, 0, displayW, displayH);

        const rx = toScreen(rect.x), ry = toScreen(rect.y);
        const rw = toScreen(rect.w), rh = toScreen(rect.h);

        ctx.fillStyle = "rgba(0,0,0,0.55)";
        ctx.fillRect(0, 0, displayW, ry);
        ctx.fillRect(0, ry + rh, displayW, displayH - ry - rh);
        ctx.fillRect(0, ry, rx, rh);
        ctx.fillRect(rx + rw, ry, displayW - rx - rw, rh);

        ctx.strokeStyle = "#3d7fbf";
        ctx.lineWidth = 2;
        ctx.strokeRect(rx, ry, rw, rh);

        ctx.fillStyle = "#3d7fbf";
        for (const [, hx, hy] of handlePoints(rx, ry, rw, rh)) {
            ctx.fillRect(hx - 4, hy - 4, 8, 8);
        }

        readout.textContent =
            `x=${Math.round(rect.x)}  y=${Math.round(rect.y)}  ` +
            `width=${Math.round(rect.w)}  height=${Math.round(rect.h)}  (source: ${naturalW}×${naturalH})`;
    }

    function close() {
        document.removeEventListener("keydown", onKeyDown);
        overlay.remove();
        URL.revokeObjectURL(url);
    }
    function onKeyDown(e) {
        if (e.key === "Escape") close();
    }
    document.addEventListener("keydown", onKeyDown);

    canvas.addEventListener("pointerdown", (e) => {
        const [px, py] = eventPos(e);
        const mode = handleAt(px, py) || "new";
        canvas.setPointerCapture(e.pointerId);
        const anchorImg = { x: toImage(px), y: toImage(py) };
        if (mode === "new") {
            rect = clampRect({ x: anchorImg.x, y: anchorImg.y, w: MIN_CROP_PX, h: MIN_CROP_PX }, naturalW, naturalH);
        }
        drag = { mode, anchorImg, startRect: { ...rect } };
        redraw();
    });

    canvas.addEventListener("pointermove", (e) => {
        const [px, py] = eventPos(e);
        if (!drag) {
            canvas.style.cursor = cursorForMode(handleAt(px, py));
            return;
        }
        const curX = toImage(px), curY = toImage(py);
        rect = computeDragRect(drag.mode, drag.startRect, drag.anchorImg, curX, curY, naturalW, naturalH);
        redraw();
    });

    function endDrag() {
        drag = null;
    }
    canvas.addEventListener("pointerup", endDrag);
    canvas.addEventListener("pointercancel", endDrag);

    resetBtn.addEventListener("click", () => {
        rect = clampRect({ x: 0, y: 0, w: naturalW, h: naturalH }, naturalW, naturalH);
        redraw();
    });
    cancelBtn.addEventListener("click", close);
    applyBtn.addEventListener("click", () => {
        setWidgetValue(node, "crop_x", Math.round(rect.x));
        setWidgetValue(node, "crop_y", Math.round(rect.y));
        setWidgetValue(node, "crop_width", Math.round(rect.w));
        setWidgetValue(node, "crop_height", Math.round(rect.h));
        node.setDirtyCanvas(true, true);
        close();
    });

    redraw();
}

function setupLabeledLoadImage(nodeType) {
    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
        onNodeCreated?.apply(this, arguments);
        for (const { name, fallback } of COLOR_WIDGETS) {
            replaceWithColorWidget(this, name, fallback);
        }
        this.addCustomWidget(new EditCropButtonWidget());
        this.addCustomWidget(new PreviewButtonWidget());
    };

    const onRemoved = nodeType.prototype.onRemoved;
    nodeType.prototype.onRemoved = function () {
        if (this._moonPreviewUrl) URL.revokeObjectURL(this._moonPreviewUrl);
        onRemoved?.apply(this, arguments);
    };
}

app.registerExtension({
    name: "comfyui.moonpack.labeled-load-image",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name === NODE_TYPE) {
            setupLabeledLoadImage(nodeType);
        }
    },
});
