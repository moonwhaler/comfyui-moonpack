/**
 * Load Image (Labeled) - adds a color-swatch widget for background_color/
 * text_color (native STRING widgets replaced with <input type=color> DOM
 * widgets) and a Preview button that renders the exact composited result
 * (label bar, arrow, border) via the backend's /moonpack/label_preview route,
 * so the thumbnail matches what execution will actually output.
 */

import { app } from "../../scripts/app.js";
import { drawButton } from "./lib/canvas_draw.js";

const NODE_TYPE = "MoonPack_LabeledLoadImage";
const COLOR_WIDGETS = [
    { name: "background_color", fallback: "#000000" },
    { name: "text_color", fallback: "#ffffff" },
];

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

function setupLabeledLoadImage(nodeType) {
    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
        onNodeCreated?.apply(this, arguments);
        for (const { name, fallback } of COLOR_WIDGETS) {
            replaceWithColorWidget(this, name, fallback);
        }
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
