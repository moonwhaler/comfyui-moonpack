/**
 * Minimal canvas drawing helpers for MoonPack's custom widgets.
 *
 * Every helper works in node-local coordinates (LiteGraph translates the
 * context so the node's top-left is 0,0 while widgets draw) and returns the
 * horizontal bounds it occupied as [startX, width], so callers can turn them
 * straight into hit areas.
 *
 * No ComfyUI imports here on purpose - this file is pure canvas work.
 */

export const STEPPER_ARROW_WIDTH = 12;
export const STEPPER_VALUE_WIDTH = 42;
export const STEPPER_WIDTH = STEPPER_ARROW_WIDTH * 2 + STEPPER_VALUE_WIDTH;
export const REMOVE_WIDTH = 14;

const TEXT_COLOR = () => (globalThis.LiteGraph?.WIDGET_TEXT_COLOR ?? "#ddd");
const BG_COLOR = () => (globalThis.LiteGraph?.WIDGET_BGCOLOR ?? "#222");
const OUTLINE_COLOR = () => (globalThis.LiteGraph?.WIDGET_OUTLINE_COLOR ?? "#666");

/** Truncates with a trailing ellipsis so the start of the string stays readable. */
export function fitString(ctx, str, maxWidth) {
    if (maxWidth <= 0) return "";
    if (ctx.measureText(str).width <= maxWidth) return str;
    const ellipsisWidth = ctx.measureText("…").width;
    if (maxWidth <= ellipsisWidth) return "";
    let lo = 0;
    let hi = str.length;
    while (lo < hi) {
        const mid = Math.ceil((lo + hi) / 2);
        if (ctx.measureText(str.slice(0, mid)).width + ellipsisWidth <= maxWidth) lo = mid;
        else hi = mid - 1;
    }
    return str.slice(0, lo) + "…";
}

/** Truncates with a leading ellipsis - for paths, where the filename matters most. */
export function fitStringEnd(ctx, str, maxWidth) {
    if (maxWidth <= 0) return "";
    if (ctx.measureText(str).width <= maxWidth) return str;
    const ellipsisWidth = ctx.measureText("…").width;
    if (maxWidth <= ellipsisWidth) return "";
    let lo = 0;
    let hi = str.length;
    while (lo < hi) {
        const mid = Math.ceil((lo + hi) / 2);
        if (ctx.measureText(str.slice(str.length - mid)).width + ellipsisWidth <= maxWidth) lo = mid;
        else hi = mid - 1;
    }
    return "…" + str.slice(str.length - lo);
}

export function roundedRectPath(ctx, x, y, w, h, radius) {
    const r = Math.max(0, Math.min(radius, w * 0.5, h * 0.5));
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
}

/** The container box one LoRA row sits in. */
export function drawRowBox(ctx, x, y, w, h) {
    ctx.save();
    roundedRectPath(ctx, x, y, w, h, 6);
    ctx.fillStyle = BG_COLOR();
    ctx.fill();
    ctx.strokeStyle = OUTLINE_COLOR();
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.restore();
}

/** A thin horizontal rule spanning the node. */
export function drawDivider(ctx, x, y, w) {
    ctx.save();
    ctx.strokeStyle = OUTLINE_COLOR();
    ctx.globalAlpha = 0.5;
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x + w, y);
    ctx.stroke();
    ctx.restore();
}

/**
 * A pill toggle. `value` is true (on), false (off) or null (mixed).
 * Returns [startX, width].
 */
export function drawToggle(ctx, x, y, h, value) {
    const height = Math.round(h * 0.68);
    const width = Math.round(height * 1.8);
    const top = y + (h - height) / 2;
    const radius = height / 2;

    ctx.save();
    roundedRectPath(ctx, x, top, width, height, radius);
    ctx.fillStyle = value === true ? "#3d7fbf" : value === null ? "#5a5a5a" : "#2b2b2b";
    ctx.fill();
    ctx.strokeStyle = OUTLINE_COLOR();
    ctx.lineWidth = 1;
    ctx.stroke();

    const knobRadius = radius - 2;
    const knobX = value === true
        ? x + width - radius
        : value === null
            ? x + width / 2
            : x + radius;
    ctx.beginPath();
    ctx.arc(knobX, top + radius, knobRadius, 0, Math.PI * 2);
    ctx.fillStyle = value === false ? "#8a8a8a" : "#f0f0f0";
    ctx.fill();
    ctx.restore();

    return [x, width];
}

function triangle(ctx, centerX, centerY, size, direction) {
    ctx.beginPath();
    if (direction < 0) {
        ctx.moveTo(centerX + size * 0.5, centerY - size);
        ctx.lineTo(centerX - size * 0.5, centerY);
        ctx.lineTo(centerX + size * 0.5, centerY + size);
    } else {
        ctx.moveTo(centerX - size * 0.5, centerY - size);
        ctx.lineTo(centerX + size * 0.5, centerY);
        ctx.lineTo(centerX - size * 0.5, centerY + size);
    }
    ctx.closePath();
    ctx.fill();
}

/**
 * A ◀ value ▶ stepper, right-aligned so it ends at `rightX`.
 * Returns the hit bounds of each part plus the x it started at.
 */
export function drawStepper(ctx, rightX, y, h, value, textColor) {
    const startX = rightX - STEPPER_WIDTH;
    const midY = y + h * 0.5;
    const arrowSize = Math.max(3, h * 0.2);

    ctx.save();
    ctx.fillStyle = textColor || TEXT_COLOR();
    triangle(ctx, startX + STEPPER_ARROW_WIDTH * 0.5, midY, arrowSize, -1);
    triangle(ctx, rightX - STEPPER_ARROW_WIDTH * 0.5, midY, arrowSize, 1);

    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    const shown = Number.isFinite(Number(value)) ? Number(value).toFixed(2) : "1.00";
    ctx.fillText(shown, startX + STEPPER_ARROW_WIDTH + STEPPER_VALUE_WIDTH * 0.5, midY);
    ctx.restore();

    return {
        startX,
        dec: [startX, STEPPER_ARROW_WIDTH],
        val: [startX + STEPPER_ARROW_WIDTH, STEPPER_VALUE_WIDTH],
        inc: [rightX - STEPPER_ARROW_WIDTH, STEPPER_ARROW_WIDTH],
    };
}

/** An ✕ button, right-aligned so it ends at `rightX`. Returns [startX, width]. */
export function drawRemoveIcon(ctx, rightX, y, h) {
    const size = Math.min(REMOVE_WIDTH, h * 0.5);
    const startX = rightX - REMOVE_WIDTH;
    const centerX = startX + REMOVE_WIDTH * 0.5;
    const centerY = y + h * 0.5;
    const arm = size * 0.5;

    ctx.save();
    ctx.strokeStyle = TEXT_COLOR();
    ctx.lineWidth = 1.5;
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.moveTo(centerX - arm, centerY - arm);
    ctx.lineTo(centerX + arm, centerY + arm);
    ctx.moveTo(centerX + arm, centerY - arm);
    ctx.lineTo(centerX - arm, centerY + arm);
    ctx.stroke();
    ctx.restore();

    return [startX, REMOVE_WIDTH];
}

/** A full-width button face with centred label. Returns [startX, width]. */
export function drawButton(ctx, x, y, w, h, label) {
    ctx.save();
    roundedRectPath(ctx, x, y, w, h, 6);
    ctx.fillStyle = BG_COLOR();
    ctx.fill();
    ctx.strokeStyle = OUTLINE_COLOR();
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.fillStyle = TEXT_COLOR();
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(label, x + w * 0.5, y + h * 0.5);
    ctx.restore();
    return [x, w];
}
