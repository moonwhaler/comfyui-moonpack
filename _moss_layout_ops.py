"""MOSS-Image layout logic for the MOSS Regional Layout node (torch- and PIL-free).

Derived from ComfyUI-KJNodes by kijai (https://github.com/kijai/ComfyUI-KJNodes),
nodes/moss_image_nodes.py and nodes/ideogram4_nodes.py, licensed GPL-3.0.
Modified for MoonPack: hidden boxes, per-box LoRAs with trigger words, scene
LoRAs, and the conversion of boxes into regional LoRA assignments.

MOSS reads a layout as a JSON prompt: a summary caption plus items, each with a
label (object / character / text), a caption, the text to render, and a bbox in
absolute pixels measured from the canvas centre ([y_min, x_min, y_max, x_max];
bbox_coord_space "abs_centralized", bbox_format "yxyx").

Editor box: {x, y, w, h} fractions (0-1), type, text, desc, tags, palette[],
nobbox?, locked?, name?, hidden?, loras: [{on, lora, strength, text, start, end}].
Scene LoRA: same row shape plus target "all" | "outside".
"""

import json
import logging
import math
import re

try:
    from ._regional_lora_ops import BACKGROUND, GLOBAL
except ImportError:  # importable for tests without package context
    from _regional_lora_ops import BACKGROUND, GLOBAL

CANVASES = ("single", "multi_panel", "collage")  # summary.canvas values the official compiler accepts
TRIGGER_SEPARATOR = ", "


def strs(v):
    """A list of non-empty strings; a comma/newline separated string is split."""
    if isinstance(v, str):
        v = re.split(r"[,\n]", v)
    return [str(t).strip() for t in (v if isinstance(v, list) else []) if str(t).strip()]


def label_of(t):
    """Editor box type -> item label; "obj" (Ideogram templates) is an object."""
    return t if isinstance(t, str) and t.strip() and t != "obj" else "object"


def edges(box):
    """{x, y, w, h} fractions -> clamped (x1, y1, x2, y2) fractions, negative sizes normalized."""
    x, y, w, h = (float(box.get(k, 0.0) or 0.0) for k in ("x", "y", "w", "h"))
    x1, x2 = sorted((x, x + w))
    y1, y2 = sorted((y, y + h))
    return tuple(max(0.0, min(1.0, v)) for v in (x1, y1, x2, y2))


def moss_bbox(box, width, height):
    """Editor box -> [y_min, x_min, y_max, x_max] pixel edges enclosing it, origin at the canvas centre."""
    x1, y1, x2, y2 = edges(box)
    hx, hy = width // 2, height // 2
    return [math.floor(round(y1 * height, 9)) - hy, math.floor(round(x1 * width, 9)) - hx,
            math.ceil(round(y2 * height, 9)) - hy, math.ceil(round(x2 * width, 9)) - hx]


def from_moss_bbox(bb, width, height, space):
    """Layout bbox -> editor {x, y, w, h} fractions, or None."""
    if not isinstance(bb, (list, tuple)) or len(bb) != 4:
        return None
    try:
        y1, x1, y2, x2 = (float(v) for v in bb)
    except (TypeError, ValueError):
        return None
    if "central" in str(space or "abs_centralized"):
        y1, y2, x1, x2 = y1 + height // 2, y2 + height // 2, x1 + width // 2, x2 + width // 2
    x1, x2 = (max(0.0, min(1.0, v / width)) for v in (x1, x2))
    y1, y2 = (max(0.0, min(1.0, v / height)) for v in (y1, y2))
    return {"x": min(x1, x2), "y": min(y1, y2), "w": abs(x2 - x1), "h": abs(y2 - y1)}


def blank_box():
    return {"type": "object", "text": "", "desc": "", "tags": "", "palette": [], "loras": []}


def layout_to_boxes(cap, width, height):
    """Layout dict -> editor boxes. Imported layouts carry no LoRAs."""
    space = cap.get("bbox_coord_space")
    boxes = []
    for i, it in enumerate(cap.get("items") or []):
        if not isinstance(it, dict):
            continue
        box = {**blank_box(), "type": label_of(it.get("label")), "text": str(it.get("text") or ""),
               "desc": str(it.get("caption") or ""), "tags": ", ".join(strs(it.get("tags"))),
               "palette": strs(it.get("palette"))}
        bb = from_moss_bbox(it.get("bbox"), width, height, space)
        if bb:
            box.update(bb)
        else:  # no bbox: unplaced placeholder, skipped on export
            k = i % 6
            box.update(x=0.03 + k * 0.035, y=0.03 + k * 0.035, w=0.22, h=0.14, nobbox=True)
        boxes.append(box)
    return boxes


def lora_rows(rows):
    """Enabled LoRA rows with a file and a non-zero strength."""
    out = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not row.get("on", True):
            continue
        name = row.get("lora")
        if not isinstance(name, str) or not name or name == "None":
            continue
        try:
            strength = float(row.get("strength", 1.0))
        except (TypeError, ValueError):
            strength = 1.0
        if strength == 0.0:
            continue
        out.append(row)
    return out


def with_triggers(text, rows):
    """Appends the trigger text of every enabled LoRA row to a caption."""
    parts = [text.strip()] if isinstance(text, str) and text.strip() else []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not row.get("on", True):
            continue
        trigger = row.get("text")
        if isinstance(trigger, str) and trigger.strip():
            parts.append(trigger.strip())
    return TRIGGER_SEPARATOR.join(parts)


EXTRA_KEYS = ("name", "hidden", "loras")
SIDECAR_KEY = "moonpack"


def strip_triggers(text, rows):
    """Removes the trigger suffix `with_triggers` added, so a re-import doesn't double it."""
    if not isinstance(text, str):
        return ""
    suffix = with_triggers("", rows)
    if not suffix:
        return text
    if text == suffix:
        return ""
    if text.endswith(TRIGGER_SEPARATOR + suffix):
        return text[:-len(TRIGGER_SEPARATOR + suffix)]
    return text


def sidecar(boxes, scene_loras):
    """Per-box extras the MOSS layout itself cannot carry (templates / Copy)."""
    return {"boxes": [{k: b.get(k) for k in EXTRA_KEYS if b.get(k) not in (None, "", [], False)}
                      for b in boxes if isinstance(b, dict) and not b.get("nobbox")],
            "scene_loras": list(scene_loras or [])}


def apply_extras(boxes, extras):
    """Copies name/hidden/loras by position onto imported boxes and strips their trigger suffixes."""
    extras = extras if isinstance(extras, list) else []
    placed = [b for b in boxes if not b.get("nobbox")]
    for box, extra in zip(placed, extras):
        if not isinstance(extra, dict):
            continue
        for k in EXTRA_KEYS:
            if k in extra:
                box[k] = extra[k]
        box["desc"] = strip_triggers(box.get("desc", ""), box.get("loras"))
    return boxes


def visible(box):
    return isinstance(box, dict) and not box.get("nobbox") and not box.get("hidden")


def summary(caption, meta, canvas, palette, scene_loras=None):
    """summary in the official field order; optional fields are omitted when empty."""
    s = {}
    if meta:
        s["meta"] = meta
    if canvas in CANVASES:
        s["canvas"] = canvas
    s["caption"] = with_triggers(caption or "", scene_loras)
    if palette:
        s["palette"] = palette
    return s


def layout(summ, boxes, width, height):
    """The layout dict, or None when there are no placed, visible boxes."""
    items = []
    for box in boxes:
        if not visible(box):
            continue
        label = label_of(box.get("type"))
        item = {"label": label, "caption": with_triggers(box.get("desc", "") or "", box.get("loras"))}
        if label == "text":
            item["text"] = box.get("text", "") or ""
        tags, palette = strs(box.get("tags")), strs(box.get("palette"))
        if tags:
            item["tags"] = tags
        if palette:
            item["palette"] = palette
        item["bbox"] = moss_bbox(box, width, height)
        items.append(item)
    if not items:
        return None
    return {"summary": summ, "items": items, "bbox_coord_space": "abs_centralized", "bbox_format": "yxyx"}


def regional_assignments(boxes, scene_loras):
    """Boxes + scene LoRAs -> ({box index: [ymin, xmin, ymax, xmax] on 0-1000}, entries).

    Box indices are positions in the full box list, so they match the editor's
    numbering. Entries are dicts with target (box index | GLOBAL | BACKGROUND),
    lora (name as stored), strength, start, end.
    """
    bboxes, entries = {}, []
    for index, box in enumerate(boxes if isinstance(boxes, list) else []):
        if not visible(box):
            continue
        x1, y1, x2, y2 = edges(box)
        bboxes[index] = [y1 * 1000.0, x1 * 1000.0, y2 * 1000.0, x2 * 1000.0]
        for row in lora_rows(box.get("loras")):
            entries.append(_entry(index, row))
    for row in lora_rows(scene_loras):
        entries.append(_entry(BACKGROUND if row.get("target") == "outside" else GLOBAL, row))
    return bboxes, entries


def _entry(target, row):
    def num(key, default):
        try:
            return float(row.get(key, default))
        except (TypeError, ValueError):
            return default
    start, end = max(0.0, min(1.0, num("start", 0.0))), max(0.0, min(1.0, num("end", 1.0)))
    return {"target": target, "lora": row["lora"], "strength": num("strength", 1.0),
            "start": min(start, end), "end": max(start, end)}


def dumps(v, lvl=0, ind="    "):
    """Like json.dumps(ensure_ascii=False, indent=ind), but scalar arrays stay on one line."""
    pad, end = ind * (lvl + 1), ind * lvl
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, list):
        if not v:
            return "[]"
        if all(not isinstance(x, (dict, list)) for x in v):
            return "[" + ", ".join(dumps(x, lvl, ind) for x in v) + "]"
        return "[\n" + ",\n".join(pad + dumps(x, lvl + 1, ind) for x in v) + "\n" + end + "]"
    if isinstance(v, dict):
        if not v:
            return "{}"
        items = [pad + json.dumps(k, ensure_ascii=False) + ": " + dumps(val, lvl + 1, ind) for k, val in v.items()]
        return "{\n" + ",\n".join(items) + "\n" + end + "}"
    return json.dumps(v, ensure_ascii=False)


def parse_json_list(s):
    if s:
        try:
            v = json.loads(s)
            if isinstance(v, list):
                return v
        except (json.JSONDecodeError, TypeError):
            pass
    return []


def repair_json(s):
    """Slices out the outermost {...} and strips trailing commas outside strings."""
    t = s.strip()
    if t.startswith('"'):  # bare "key": ... list (outer braces lost in a copy)
        bare = re.sub(r'"(?:[^"\\]|\\.)*"', "", t)
        t = "{" + t + ("}" if bare.count("{") >= bare.count("}") else "")
    i, j = t.find("{"), t.rfind("}")
    t = t[i:j + 1] if (i != -1 and j > i) else t
    return re.sub(r'("(?:[^"\\]|\\.)*")|,(\s*[}\]])', lambda m: m.group(1) or m.group(2), t)


def loads_caption(s, tag="MOSS Regional Layout"):
    """Parses a caption dict; on failure retries once with the lenient repair. Returns dict or None."""
    for cand in ((s, repair_json(s)) if isinstance(s, str) and s.strip() else ()):
        try:
            v = json.loads(cand)
            if isinstance(v, dict):
                if cand is not s:
                    logging.getLogger("MoonPack").warning("[%s] import_json had errors; recovered with lenient parse", tag)
                return v
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def seed_boxes(bboxes, width, height):
    """BoundingBox input (pixel {x, y, width, height}) -> editor boxes."""
    if isinstance(bboxes, dict):
        frame = [bboxes]
    elif bboxes and isinstance(bboxes[0], (list, tuple)):
        frame = bboxes[0]
    else:
        frame = bboxes or []
    return [{"x": bb.get("x", 0) / width, "y": bb.get("y", 0) / height,
             "w": bb.get("width", 0) / width, "h": bb.get("height", 0) / height, **blank_box()}
            for bb in frame if isinstance(bb, dict)]


def bbox_outputs(boxes, width, height):
    """Pixel-space bboxes ({x, y, width, height}) of visible boxes, per-frame nested."""
    out = []
    for box in boxes:
        if not visible(box):
            continue
        x, y = box.get("x", 0.0), box.get("y", 0.0)
        bw, bh = box.get("w", 0.0), box.get("h", 0.0)
        if bw < 0:
            x += bw
            bw = -bw
        if bh < 0:
            y += bh
            bh = -bh
        out.append({"x": round(x * width), "y": round(y * height),
                    "width": round(bw * width), "height": round(bh * height)})
    return [out] if out else []


def caption_spans(decoded, offsets, captions):
    """Token spans of the item captions inside the tokenized layout prompt.

    decoded:  the token sequence decoded to text (special tokens kept)
    offsets:  len(n_tokens + 1) char offsets, offsets[i] = len(decode(ids[:i]))
    captions: the item captions in item order (as they appear in the JSON)

    Returns a list of (t0, t1) token spans covering each caption's text, or None
    when a caption can't be found (the prompt was changed after this node).
    """
    spans, pos = [], 0
    n = len(offsets) - 1
    for caption in captions:
        quoted = json.dumps(caption, ensure_ascii=False)
        # compact ("caption":"…") and pretty ("caption": "…") output both occur
        m = re.compile(r'"caption"\s*:\s*' + re.escape(quoted)).search(decoded, pos)
        if m is None:
            return None
        c0 = m.end() - len(quoted) + 1
        c1 = m.end() - 1
        pos = c1
        t0 = max(i for i in range(n + 1) if offsets[i] <= c0)
        t1 = min(i for i in range(n + 1) if offsets[i] >= c1)
        spans.append((min(t0, n), max(t1, t0 + 1)))
    return spans
