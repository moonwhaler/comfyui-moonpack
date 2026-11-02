// Pure helpers for the MOSS Regional Layout editor (no DOM, no ComfyUI imports).
// Mirrors _regional_lora_ops.py (masks) and _moss_layout_ops.py (triggers, extras) so the
// editor's overlay and caption match what the node computes.

export const TOKEN_PX = 16;                 // pixels per MOSS token edge
export const TRIGGER_SEPARATOR = ", ";
export const EXTRA_KEYS = ["name", "hidden", "loras"];
export const SIDECAR_KEY = "moonpack";

// Clamped [y1, x1, y2, x2] fractions, negative sizes normalized (mirrors edges()).
export function edges(b) {
  const c = (v) => Math.max(0, Math.min(1, v));
  const x = +b.x || 0, y = +b.y || 0, w = +b.w || 0, h = +b.h || 0;
  return [c(Math.min(y, y + h)), c(Math.min(x, x + w)), c(Math.max(y, y + h)), c(Math.max(x, x + w))];
}

// Box -> [ymin, xmin, ymax, xmax] on the 0-1000 grid, floats (mirrors regional_assignments()).
export function grid1000(b) {
  return edges(b).map((v) => v * 1000);
}

// ── masks (mirror _regional_lora_ops.py) ──
function axisProfile(lo, hi, size, feather) {
  const profile = new Array(size);
  for (let i = 0; i < size; i++) {
    const c = i + 0.5;
    let v;
    if (feather > 0) {
      v = Math.min(c - lo, hi - c) / feather + 0.5;
      v = v < 0 ? 0 : v > 1 ? 1 : v;
    } else {
      v = lo <= c && c < hi ? 1 : 0;
    }
    profile[i] = v;
  }
  if (hi > lo && size > 0) profile[Math.min(size - 1, Math.max(0, Math.floor((lo + hi) / 2)))] = 1;
  return profile;
}

export function boxRectTokens(bbox, gh, gw, skirt = 0) {
  const [ymin, xmin, ymax, xmax] = bbox.map((v) => v / 1000);
  const [y0, y1] = [ymin * gh, ymax * gh].sort((a, b) => a - b);
  const [x0, x1] = [xmin * gw, xmax * gw].sort((a, b) => a - b);
  const grow = Math.max(0, skirt) * Math.min(gh, gw);
  return [Math.max(0, y0 - grow), Math.max(0, x0 - grow), Math.min(gh, y1 + grow), Math.min(gw, x1 + grow)];
}

// Flat row-major mask (gh * gw) of one box; feather = fraction of the box's shorter side (cap 0.3).
export function boxMask(bbox, gh, gw, feather = 0, skirt = 0) {
  const [y0, x0, y1, x1] = boxRectTokens(bbox, gh, gw, skirt);
  const width = Math.max(0, Math.min(feather, 0.3)) * Math.min(y1 - y0, x1 - x0);
  const ys = axisProfile(y0, y1, gh, width), xs = axisProfile(x0, x1, gw, width);
  const out = new Array(gh * gw);
  for (let r = 0; r < gh; r++) for (let c = 0; c < gw; c++) out[r * gw + c] = ys[r] * xs[c];
  return out;
}

// Painter's order: masks[last] on top. Returns {owned, background}.
export function composeMasks(masks) {
  if (!masks.length) return { owned: [], background: null };
  const n = masks[0].length;
  let remaining = new Array(n).fill(1);
  const owned = new Array(masks.length);
  for (let r = masks.length - 1; r >= 0; r--) {
    const m = masks[r];
    owned[r] = m.map((v, i) => v * remaining[i]);
    remaining = remaining.map((v, i) => v * (1 - m[i]));
  }
  return { owned, background: remaining };
}

// Enabled rows with a file and a non-zero strength (mirrors lora_rows()).
export function activeLoras(rows) {
  return (Array.isArray(rows) ? rows : []).filter((r) => r && r.on !== false && typeof r.lora === "string"
    && r.lora && r.lora !== "None" && Number(r.strength ?? 1) !== 0);
}

const isVisible = (b) => b && !b.nobbox && !b.hidden;

// Owned masks of every visible LoRA box (box 0 = front-most) plus the background, on a gh × gw grid.
// Returns {boxes: [{index, mask}], background} — mirrors RegionalLoraManager.image_masks().
export function layoutMasks(boxes, gh, gw, feather, skirt) {
  const used = [];
  boxes.forEach((b, i) => { if (isVisible(b) && activeLoras(b.loras).length) used.push(i); });
  const backToFront = [...used].reverse();
  const { owned, background } = composeMasks(backToFront.map((i) => boxMask(grid1000(boxes[i]), gh, gw, feather, skirt)));
  return {
    boxes: backToFront.map((index, k) => ({ index, mask: owned[k] })).reverse(),
    background: background || new Array(gh * gw).fill(1),
  };
}

// ── captions ──
export function withTriggers(text, rows) {
  const parts = typeof text === "string" && text.trim() ? [text.trim()] : [];
  for (const r of Array.isArray(rows) ? rows : []) {
    if (!r || r.on === false) continue;
    if (typeof r.text === "string" && r.text.trim()) parts.push(r.text.trim());
  }
  return parts.join(TRIGGER_SEPARATOR);
}

export function stripTriggers(text, rows) {
  if (typeof text !== "string") return "";
  const suffix = withTriggers("", rows);
  if (!suffix) return text;
  if (text === suffix) return "";
  if (text.endsWith(TRIGGER_SEPARATOR + suffix)) return text.slice(0, -(TRIGGER_SEPARATOR + suffix).length);
  return text;
}

export function pickExtras(b) {
  const o = {};
  for (const k of EXTRA_KEYS) {
    const v = b?.[k];
    if (v === undefined || v === null || v === "" || v === false || (Array.isArray(v) && !v.length)) continue;
    o[k] = JSON.parse(JSON.stringify(v));
  }
  return o;
}

export function sidecar(boxes, sceneLoras) {
  return { boxes: boxes.filter((b) => b && !b.nobbox).map(pickExtras), scene_loras: JSON.parse(JSON.stringify(sceneLoras || [])) };
}

// Copies extras by position onto (placed) boxes and strips the trigger suffixes (mirrors apply_extras()).
export function applyExtras(boxes, extras) {
  if (!Array.isArray(extras)) return boxes;
  const placed = boxes.filter((b) => !b.nobbox);
  placed.forEach((b, i) => {
    const e = extras[i];
    if (!e || typeof e !== "object") return;
    for (const k of EXTRA_KEYS) if (k in e) b[k] = JSON.parse(JSON.stringify(e[k]));
    b.desc = stripTriggers(b.desc || "", b.loras);
  });
  return boxes;
}

// ── size presets ──
export const ASPECTS = [[1, 1], [4, 5], [3, 4], [2, 3], [9, 16], [5, 4], [4, 3], [3, 2], [16, 9], [21, 9]];
export const MEGAPIXELS = [1.0, 1.5, 2.0, 2.5];

// Width/height for an aspect at ~mp megapixels (1 MP = 1024²), multiples of 16.
export function presetSize(aw, ah, mp) {
  const px = mp * 1024 * 1024, r16 = (v) => Math.max(16, Math.round(v / 16) * 16);
  return [r16(Math.sqrt(px * aw / ah)), r16(Math.sqrt(px * ah / aw))];
}
