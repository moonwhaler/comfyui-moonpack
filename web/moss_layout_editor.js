// MOSS Regional Layout editor: MOSS-Image layout boxes with per-box LoRAs.
//
// Derived from ComfyUI-KJNodes by kijai (https://github.com/kijai/ComfyUI-KJNodes, commit ab72eda),
// web/js/moss_image_prompt_builder.js, GPL-3.0. Modified for MoonPack (GPL-3.0): per-box and scene
// LoRAs with trigger words, box names, hide/solo, LoRA mask overlay, size presets, undo (core).
//
// Layout format (moss_regional_layout_node.py): {summary: {meta?, canvas?, caption, palette?}, items:
// [{label, caption, text?, tags?, palette?, bbox}], bbox_coord_space: "abs_centralized", bbox_format: "yxyx"}.

import { registerPromptBuilder, ideoFromEdges } from "./lib/moss_editor_core.js";
import { fetchLoras, showLoraChooser } from "./lib/lora_chooser.js";
import {
  TOKEN_PX, activeLoras, applyExtras, layoutMasks, presetSize, ASPECTS, MEGAPIXELS,
  sidecar, stripTriggers, withTriggers, pickExtras,
} from "./lib/moss_layout_math.js";

const CANVASES = ["single", "multi_panel", "collage"];
const strs = (v) => (typeof v === "string" ? v.split(/[,\n]/) : Array.isArray(v) ? v : []).map((s) => String(s).trim()).filter(Boolean);
const r9 = (v) => Math.round(v * 1e9) / 1e9;
const half = (v) => Math.floor(v / 2);
const round2 = (v) => Math.round(v * 100) / 100;

function edgesYX(b) {
  const c = (v) => Math.max(0, Math.min(1, v));
  return [c(Math.min(b.y, b.y + b.h)), c(Math.min(b.x, b.x + b.w)), c(Math.max(b.y, b.y + b.h)), c(Math.max(b.x, b.x + b.w))];
}
export function mossBbox(b, W, H) {
  const [y1, x1, y2, x2] = edgesYX(b);
  return [Math.floor(r9(y1 * H)) - half(H), Math.floor(r9(x1 * W)) - half(W), Math.ceil(r9(y2 * H)) - half(H), Math.ceil(r9(x2 * W)) - half(W)];
}
function fromMossBbox(bb, W, H, space) {
  if (!Array.isArray(bb) || bb.length !== 4) return null;
  let [y1, x1, y2, x2] = bb.map(Number);
  if (![y1, x1, y2, x2].every(Number.isFinite)) return null;
  if (String(space || "abs_centralized").includes("central")) { y1 += half(H); y2 += half(H); x1 += half(W); x2 += half(W); }
  return ideoFromEdges([y1, x1, y2, x2], W, H);
}
const labelOf = (t) => (typeof t === "string" && t.trim() && t !== "obj") ? t : "object";
const loraLabel = (name) => String(name || "").replace(/\\/g, "/").split("/").pop().replace(/\.safetensors$/i, "") || "(pick LoRA)";
const newRow = (extra = {}) => ({ on: true, lora: "", strength: 1.0, text: "", start: 0, end: 1, ...extra });

// ── scene LoRAs (whole image / outside the LoRA boxes), kept on the node and in scene_loras_data ──
function sceneOf(node) { return (node._sceneLoras = Array.isArray(node._sceneLoras) ? node._sceneLoras : []); }
function saveScene(ed) {
  const w = ed.findW("scene_loras_data");
  const rows = sceneOf(ed.node);
  if (w) w.value = rows.length ? JSON.stringify(rows) : "";
}
function loadScene(ed) {
  const w = ed.findW("scene_loras_data");
  let rows = [];
  try { const v = JSON.parse(w?.value || "[]"); if (Array.isArray(v)) rows = v; } catch (e) {}
  ed.node._sceneLoras = rows;
}

// ── DOM helpers ──
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
function button(ed, label, title, onClick, active = false) {
  const b = el("button", "moonmoss-btn" + (active ? " active" : ""), label);
  if (title) b.title = title;
  ed.stopProp(b);
  b.addEventListener("click", onClick);
  return b;
}
function injectStyle() {
  if (document.getElementById("moonmoss-lora-style")) return;
  const s = el("style");
  s.id = "moonmoss-lora-style";
  s.textContent = `
    .moonmoss-lora { display:flex; flex-direction:column; gap:3px; padding:4px; border:1px solid #444; border-radius:5px; background:#202020; }
    .moonmoss-lora.off { opacity:0.5; }
    .moonmoss-lora-line { display:flex; align-items:center; gap:5px; }
    .moonmoss-lora-name { flex:1 1 auto; min-width:60px; text-align:left; overflow:hidden; text-overflow:ellipsis; }
    .moonmoss-lora-val { min-width:38px; text-align:center; cursor:ew-resize; user-select:none; color:#ffd666; font:11px monospace; }
    .moonmoss-lora input[type=text], .moonmoss-name { flex:1 1 auto; background:#151515; color:#ddd; border:1px solid #444; border-radius:3px; font:11px sans-serif; padding:2px 4px; min-width:40px; }
    .moonmoss-lora input[type=number] { width:48px; background:#151515; color:#ddd; border:1px solid #444; border-radius:3px; font:11px sans-serif; }
    .moonmoss-sect { color:#888; font:11px sans-serif; margin-top:4px; }
    .moonmoss-scene { min-width:360px; max-width:440px; display:flex; flex-direction:column; gap:4px; padding:6px; }
    .moonmoss-presets td { padding:1px; }
  `;
  document.head.appendChild(s);
}

// One LoRA row (box or scene). onChange(structural) persists: structural → commit, else touch.
function loraRow(ed, row, { onChange, onRemove, scene = false }) {
  const box = el("div", "moonmoss-lora" + (row.on === false ? " off" : ""));
  const line = el("div", "moonmoss-lora-line");
  const cb = el("input"); cb.type = "checkbox"; cb.checked = row.on !== false; cb.title = "Enable this LoRA";
  ed.stopProp(cb);
  cb.addEventListener("change", () => { row.on = cb.checked; onChange(true); });
  line.appendChild(cb);

  const name = button(ed, loraLabel(row.lora), row.lora || "Pick a LoRA", async (e) => {
    const loras = await fetchLoras();
    showLoraChooser(e, loras, (picked) => { row.lora = picked; onChange(true); });
  });
  name.classList.add("moonmoss-lora-name");
  line.appendChild(name);

  if (scene) {
    const tgt = button(ed, row.target === "outside" ? "outside" : "all", "Whole image, or only outside the LoRA boxes", () => {
      row.target = row.target === "outside" ? "all" : "outside"; onChange(true);
    });
    line.appendChild(tgt);
  }

  const val = el("span", "moonmoss-lora-val", Number(row.strength ?? 1).toFixed(2));
  val.title = "Strength — drag sideways, wheel, or double-click to type";
  ed.stopProp(val);
  const setStrength = (v, structural) => { row.strength = round2(Math.max(-10, Math.min(10, v))); val.textContent = row.strength.toFixed(2); onChange(structural); };
  const dec = button(ed, "−", "−0.05", () => setStrength((row.strength ?? 1) - 0.05, true));
  const inc = button(ed, "+", "+0.05", () => setStrength((row.strength ?? 1) + 0.05, true));
  val.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    const x0 = e.clientX, s0 = Number(row.strength ?? 1);
    let moved = false;
    val.setPointerCapture(e.pointerId);
    const move = (ev) => { const dx = ev.clientX - x0; if (Math.abs(dx) > 1) moved = true; if (moved) setStrength(s0 + dx * 0.01, false); };
    const up = () => { val.removeEventListener("pointermove", move); val.removeEventListener("pointerup", up); if (moved) onChange(true); };
    val.addEventListener("pointermove", move);
    val.addEventListener("pointerup", up);
  });
  val.addEventListener("wheel", (e) => { e.preventDefault(); setStrength((row.strength ?? 1) + (e.deltaY < 0 ? 0.05 : -0.05), true); });
  val.addEventListener("dblclick", () => {
    const v = parseFloat(window.prompt("Strength", String(row.strength ?? 1)));
    if (Number.isFinite(v)) setStrength(v, true);
  });
  line.appendChild(dec); line.appendChild(val); line.appendChild(inc);

  const more = button(ed, "⋯", "Schedule (start/end of sampling)", () => { row._open = !row._open; onChange(true); }, !!row._open || row.start > 0 || row.end < 1);
  line.appendChild(more);
  line.appendChild(button(ed, "✕", "Remove this LoRA", onRemove));
  box.appendChild(line);

  const trig = el("input"); trig.type = "text"; trig.value = row.text || "";
  trig.placeholder = scene ? "trigger words (appended to the scene caption)" : "trigger words (appended to this box's caption)";
  ed.stopProp(trig);
  trig.addEventListener("input", () => { row.text = trig.value; onChange(false); });
  trig.addEventListener("change", () => onChange(true));
  box.appendChild(trig);

  if (row._open || row.start > 0 || row.end < 1) {
    const sch = el("div", "moonmoss-lora-line");
    sch.appendChild(el("span", "moonmoss-sect", "active from"));
    const num = (key, def) => {
      const n = el("input"); n.type = "number"; n.min = 0; n.max = 1; n.step = 0.05; n.value = row[key] ?? def;
      ed.stopProp(n);
      n.addEventListener("change", () => { const v = parseFloat(n.value); row[key] = Number.isFinite(v) ? Math.max(0, Math.min(1, v)) : def; onChange(true); });
      return n;
    };
    sch.appendChild(num("start", 0)); sch.appendChild(el("span", "moonmoss-sect", "to")); sch.appendChild(num("end", 1));
    sch.appendChild(el("span", "moonmoss-sect", "of sampling"));
    box.appendChild(sch);
  }
  return box;
}

// Drops the UI-only _open flag before the rows are saved.
const cleanRows = (rows) => rows.forEach((r) => { if (r && !r._open) delete r._open; });

registerPromptBuilder({
  nodeName: "MoonPack_MOSSRegionalLayout",
  label: "MOSS-Image",
  title: "MOSS Regional Layout",
  noun: "box",
  nounPlural: "boxes",
  tplDir: "moonpack/moss_layout/templates",
  captionKey: "items",
  frontFirst: true,
  maxElemColors: 8,
  maxStyleColors: 16,
  styleColorsLabel: "Summary palette:",
  format: "compact",
  indent: "    ",
  compactTip: "Compact output (what the model is given). Uncheck for pretty/indented.",
  tokenCap: 0,
  typeToggle: ["object", "character", "text"],
  captionWidgets: ["prompt", "meta", "canvas"],
  dataWidgets: ["scene_loras_data"],
  fields: [
    { key: "text", placeholder: "text to render (verbatim)", when: (b) => b.type === "text" },
    { key: "desc", placeholder: "caption: what this box looks like" },
    { key: "tags", placeholder: "tags, comma separated (optional)" },
  ],
  coords: {
    px: {
      hint: "ymin, xmin, ymax, xmax", title: "Pixel bbox from the top-left: ymin, xmin, ymax, xmax — editable",
      get: (b, W, H) => [Math.round(b.y * H), Math.round(b.x * W), Math.round((b.y + b.h) * H), Math.round((b.x + b.w) * W)],
      set: (n, W, H) => ideoFromEdges(n, W, H),
    },
    out: {
      hint: "ymin, xmin, ymax, xmax", title: "Exported bbox: pixels from the canvas centre, ymin, xmin, ymax, xmax — editable",
      get: (b, W, H) => mossBbox(b, W, H),
      set: (n, W, H) => ideoFromEdges([n[0] + half(H), n[1] + half(W), n[2] + half(H), n[3] + half(W)], W, H),
    },
  },
  blankBox: () => ({ type: "object", text: "", desc: "", tags: "", palette: [], loras: [] }),
  tagText: (b, i) => String(i + 1).padStart(2, "0") + (b.name ? " " + b.name : "") + (b.hidden ? " (hidden)" : ""),
  elements: (cap) => (Array.isArray(cap.items) ? cap.items.map((it) => (it && typeof it === "object" ? { ...it, _space: cap.bbox_coord_space } : it)) : []),
  elemToBox(e, idx, ed) {
    if (!e || typeof e !== "object") return null;
    const box = { type: labelOf(e.label), text: String(e.text || ""), desc: String(e.caption || ""),
      tags: strs(e.tags).join(", "), palette: strs(e.palette), loras: [] };
    const [W, H] = ed.dims();
    const bb = fromMossBbox(e.bbox, W, H, e._space);
    if (bb) Object.assign(box, bb);
    else {
      const k = (idx || 0) % 6;
      Object.assign(box, { x: 0.03 + k * 0.035, y: 0.03 + k * 0.035, w: 0.22, h: 0.14, nobbox: true });
    }
    return box;
  },
  // Mirrors MOSSRegionalLayout.build: hidden boxes left out, trigger words appended.
  buildCaption(ed, opts = {}) {
    const { getW, node } = ed, [W, H] = ed.dims();
    const items = node._boxes.filter((b) => !b.nobbox && !b.hidden).map((b) => {
      const label = labelOf(b.type);
      const it = { label, caption: withTriggers(b.desc || "", b.loras) };
      if (label === "text") it.text = b.text || "";
      const tags = strs(b.tags), pal = strs(b.palette);
      if (tags.length) it.tags = tags;
      if (pal.length) it.palette = pal;
      it.bbox = mossBbox(b, W, H);
      return it;
    });
    const meta = strs(getW("meta")), canvas = getW("canvas"), pal = strs(node._stylePalette);
    const summary = {};
    if (meta.length) summary.meta = meta;
    if (CANVASES.includes(canvas)) summary.canvas = canvas;
    summary.caption = withTriggers(getW("prompt") || "", sceneOf(node));
    if (pal.length) summary.palette = pal;
    const cap = { summary, items, bbox_coord_space: "abs_centralized", bbox_format: "yxyx" };
    if (opts.extras) cap.moonpack = sidecar(node._boxes, sceneOf(node));   // templates / Copy keep the LoRAs
    return cap;
  },
  afterLoad(boxes, cap, ed, { prev, full }) {
    const side = cap && typeof cap.moonpack === "object" ? cap.moonpack : null;
    const extras = side?.boxes ?? (prev ? prev.filter((b) => !b.nobbox).map(pickExtras) : null);
    for (const b of boxes) if (!Array.isArray(b.loras)) b.loras = [];
    applyExtras(boxes, extras);
    if (full && Array.isArray(side?.scene_loras)) { ed.node._sceneLoras = JSON.parse(JSON.stringify(side.scene_loras)); saveScene(ed); }
  },
  applyCaption(cap, ed) {
    const s = (cap.summary && typeof cap.summary === "object") ? cap.summary : {};
    ed.setW("prompt", stripTriggers(s.caption || "", sceneOf(ed.node)));
    ed.setW("meta", strs(s.meta).join(", "));
    ed.setW("canvas", CANVASES.includes(s.canvas) ? s.canvas : "none");
    ed.node._stylePalette = strs(s.palette);
  },
  snapshotExtra: (ed) => sceneOf(ed.node),
  restoreExtra(x, ed) { ed.node._sceneLoras = Array.isArray(x) ? x : []; saveScene(ed); ed.node._moonUpdateScene?.(); },
  onConfigure(ed) { loadScene(ed); ed.node._soloSaved = null; },

  // ── toolbar: scene LoRAs, size presets, mask overlay ──
  toolbar(bar, ed) {
    injectStyle();
    const { node } = ed;
    loadScene(ed);
    // Redraw the overlay when its inputs change.
    for (const n of ["feather", "skirt", "width", "height"]) {
      const w = ed.findW(n);
      if (!w) continue;
      const cb = w.callback;
      w.callback = function (...a) { const r = cb?.apply(this, a); ed.draw(); return r; };
    }

    const popup = (btn, fill) => {
      const menu = el("div", "moonmoss-menu");
      menu.style.display = "none";
      document.body.appendChild(menu);
      const dismiss = ed.outsideDismiss(menu, () => close(), btn);
      const close = () => { menu.style.display = "none"; dismiss.disarm(); };
      const open = () => {
        menu.innerHTML = ""; fill(menu, close);
        menu.style.display = "";
        const r = btn.getBoundingClientRect();
        menu.style.left = Math.max(4, Math.min(r.left, window.innerWidth - menu.offsetWidth - 4)) + "px";
        menu.style.top = Math.min(r.bottom + 4, window.innerHeight - menu.offsetHeight - 4) + "px";
        dismiss.arm();
      };
      btn.addEventListener("click", () => (menu.style.display !== "none" ? close() : open()));
      const prevRemoved = node.onRemoved;
      node.onRemoved = function () { menu.remove(); return prevRemoved?.apply(this, arguments); };
      return { refresh: () => { if (menu.style.display !== "none") { menu.innerHTML = ""; fill(menu, close); } } };
    };

    // Scene LoRAs
    const sceneBtn = button(ed, "Scene LoRAs ▾", "LoRAs for the whole image, or only outside the LoRA boxes", () => {});
    const updateSceneBtn = () => { const n = activeLoras(sceneOf(node)).length; sceneBtn.textContent = `Scene LoRAs${n ? " (" + n + ")" : ""} ▾`; };
    let scenePop;
    const fillScene = (menu) => {
      menu.classList.add("moonmoss-scene");
      const rows = sceneOf(node);
      const persist = (structural) => {
        saveScene(ed); updateSceneBtn();
        if (structural) { cleanRows(rows); ed.commit(); scenePop.refresh(); } else ed.touch();
      };
      rows.forEach((row, k) => menu.appendChild(loraRow(ed, row, {
        scene: true, onChange: persist, onRemove: () => { rows.splice(k, 1); persist(true); },
      })));
      if (!rows.length) menu.appendChild(el("div", "moonmoss-sect", "No scene LoRAs. They act on the whole image like a normal LoRA, or only outside the LoRA boxes."));
      menu.appendChild(button(ed, "+ Scene LoRA", "Add a LoRA for the whole image", async (e) => {
        const loras = await fetchLoras();
        showLoraChooser(e, loras, (picked) => { rows.push(newRow({ lora: picked, target: "all" })); persist(true); });
      }));
    };
    scenePop = popup(sceneBtn, fillScene);
    updateSceneBtn();
    node._moonUpdateScene = updateSceneBtn;
    bar.appendChild(sceneBtn);

    // Size presets
    const sizeBtn = button(ed, "Size ▾", "MOSS-friendly width/height presets (multiples of 16)", () => {});
    popup(sizeBtn, (menu, close) => {
      if (ed.isLinked("width") || ed.isLinked("height") || ed.hasBg()) {
        menu.appendChild(el("div", "moonmoss-sect", "Width/height come from a link or the background image."));
        return;
      }
      const t = el("table", "moonmoss-presets");
      const head = el("tr"); head.appendChild(el("td"));
      for (const mp of MEGAPIXELS) head.appendChild(el("td", "moonmoss-sect", mp + " MP"));
      t.appendChild(head);
      for (const [aw, ah] of ASPECTS) {
        const tr = el("tr");
        tr.appendChild(el("td", "moonmoss-sect", `${aw}:${ah}`));
        for (const mp of MEGAPIXELS) {
          const [w, h] = presetSize(aw, ah, mp);
          const td = el("td");
          td.appendChild(button(ed, `${w}×${h}`, `${aw}:${ah}, ${(w * h / 1048576).toFixed(2)} MP`, () => {
            ed.setW("width", w); ed.setW("height", h); ed.commit(); close();
          }));
          tr.appendChild(td);
        }
        t.appendChild(tr);
      }
      menu.appendChild(t);
    });
    bar.appendChild(sizeBtn);

    // Mask overlay toggle
    const maskBtn = button(ed, "Masks", "Show where each box's LoRAs act (token grid, feather, skirt, overlaps). With ownership = attention these are the masks used while measuring; overlaps and spill are decided during sampling.", () => {
      node.properties.maskOverlay = !node.properties.maskOverlay;
      maskBtn.classList.toggle("active", !!node.properties.maskOverlay);
      ed.draw();
    });
    requestAnimationFrame(() => maskBtn.classList.toggle("active", !!node.properties.maskOverlay));
    bar.appendChild(maskBtn);
  },

  // ── panel: name, hide/solo, LoRAs of the active box ──
  panelExtra(panel, b, ed) {
    injectStyle();
    const { node } = ed;
    if (!Array.isArray(b.loras)) b.loras = [];
    const idx = node._boxes.indexOf(b);

    const head = el("div", "moonmoss-row");
    head.appendChild(el("span", null, "name:"));
    const name = el("input", "moonmoss-name"); name.type = "text"; name.value = b.name || "";
    name.placeholder = "label on the canvas (not sent to the model)";
    ed.stopProp(name);
    name.addEventListener("input", () => { b.name = name.value.trim(); ed.touch(); });
    name.addEventListener("change", () => ed.commit());
    head.appendChild(name);
    head.appendChild(button(ed, b.hidden ? "hidden" : "visible", "Hide: leave this box out of the prompt, masks and bboxes", () => {
      b.hidden = !b.hidden; node._soloSaved = null; ed.commit();
    }, !!b.hidden));
    const soloOn = node._soloSaved && node._soloSaved.idx === idx;
    head.appendChild(button(ed, "solo", "Hide every other box (click again to restore)", () => {
      if (soloOn) {
        node._boxes.forEach((o, i) => { o.hidden = !!node._soloSaved.hidden[i]; });
        node._soloSaved = null;
      } else {
        const hidden = node._soloSaved ? node._soloSaved.hidden : node._boxes.map((o) => !!o.hidden);
        node._soloSaved = { idx, hidden };
        node._boxes.forEach((o, i) => { o.hidden = i !== idx; });
      }
      ed.commit();
    }, soloOn));
    panel.appendChild(head);

    const sect = el("div", "moonmoss-row");
    sect.appendChild(el("span", "moonmoss-sect", "LoRAs (act only inside this box):"));
    sect.appendChild(button(ed, "+ LoRA", "Add a LoRA to this box", async (e) => {
      const loras = await fetchLoras();
      showLoraChooser(e, loras, (picked) => { b.loras.push(newRow({ lora: picked })); ed.commit(); });
    }));
    panel.appendChild(sect);
    const persist = (structural) => { if (structural) { cleanRows(b.loras); ed.commit(); } else ed.touch(); };
    b.loras.forEach((row, k) => panel.appendChild(loraRow(ed, row, {
      onChange: persist, onRemove: () => { b.loras.splice(k, 1); ed.commit(); },
    })));
  },

  // ── canvas: LoRA chips at the bottom of each box ──
  drawBox(ctx, b, i, x1, y1, w, h) {
    const rows = (b.loras || []).filter((r) => r && r.lora);
    if (!rows.length || w < 30 || h < 30) return;
    ctx.font = "10px monospace";
    let y = y1 + h - 4 - 13 * rows.length;
    for (const r of rows) {
      const label = `◆ ${loraLabel(r.lora)} ${Number(r.strength ?? 1).toFixed(2)}`;
      const tw = Math.min(w - 8, ctx.measureText(label).width + 6);
      ctx.fillStyle = r.on === false ? "rgba(60,60,60,0.75)" : "rgba(40,32,8,0.85)";
      ctx.fillRect(x1 + 4, y, tw, 12);
      ctx.fillStyle = r.on === false ? "#888" : "#ffd666";
      ctx.fillText(label, x1 + 7, y + 9, tw - 6);
      y += 13;
    }
  },

  // ── canvas: LoRA mask overlay on the token grid (same math as the node) ──
  drawUnder(ctx, W, H, ed) {
    const { node } = ed;
    if (!node.properties.maskOverlay) return;
    const pw = Number(ed.getW("width")) || 1024, ph = Number(ed.getW("height")) || 1024;
    const gw = Math.max(1, Math.round(pw / TOKEN_PX)), gh = Math.max(1, Math.round(ph / TOKEN_PX));
    const feather = Number(ed.getW("feather")) || 0, skirt = Number(ed.getW("skirt")) || 0;
    const outside = activeLoras(sceneOf(node)).some((r) => r.target === "outside");
    const key = JSON.stringify([node._boxes.map((b) => [b.x, b.y, b.w, b.h, b.hidden, b.nobbox, activeLoras(b.loras).length]), gw, gh, feather, skirt]);
    if (node._maskKey !== key) { node._maskKey = key; node._maskCache = layoutMasks(node._boxes, gh, gw, feather, skirt); }
    const { boxes, background } = node._maskCache;
    const cw = W / gw, ch = H / gh;
    const paint = (mask, rgb, alpha) => {
      for (let r = 0; r < gh; r++) for (let c = 0; c < gw; c++) {
        const v = mask[r * gw + c];
        if (v <= 0.001) continue;
        ctx.fillStyle = `rgba(${rgb},${(alpha * v).toFixed(3)})`;
        ctx.fillRect(c * cw, r * ch, Math.ceil(cw), Math.ceil(ch));
      }
    };
    const hex = (h) => { const m = /^#?([0-9a-f]{6})$/i.exec(h || ""); const n = m ? parseInt(m[1], 16) : 0xffd666; return `${n >> 16},${(n >> 8) & 255},${n & 255}`; };
    if (outside) paint(background, "120,170,255", 0.25);
    for (const { index, mask } of boxes) {
      const pal = (node._boxes[index].palette || []).filter(Boolean);
      paint(mask, hex(pal[0] || "#ffd666"), 0.45);
    }
  },
});
