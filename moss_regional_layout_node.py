"""MOSS Regional Layout: box editor, MOSS layout prompt and regional LoRAs in one node.

The editor (web/moss_layout_editor.js) is derived from ComfyUI-KJNodes by kijai
(https://github.com/kijai/ComfyUI-KJNodes), GPL-3.0. The preview renderer below
is derived from the same project's nodes/ideogram4_nodes.py.
"""

import logging

try:
    from . import _moss_layout_ops as layout_ops
    from . import moss_regional_lora_node as engine
except ImportError:  # importable for tests without package context
    import _moss_layout_ops as layout_ops
    import moss_regional_lora_node as engine

log = logging.getLogger("MoonPack")

PREVIEW_LONG_EDGE = 1024


def _hex_rgb(h):
    h = str(h).lstrip("#")
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)) if len(h) == 6 else (255, 255, 255)
    except ValueError:
        return (255, 255, 255)


def _readable(rgb):
    """Lightens toward white if too dark, so box-coloured text stays legible."""
    r, g, b = rgb
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    if lum < 130:
        t = (130 - lum) / (255 - lum)
        r, g, b = round(r + (255 - r) * t), round(g + (255 - g) * t), round(b + (255 - b) * t)
    return (r, g, b)


def _font(size):
    try:
        from ._label_ops import _load_font
    except ImportError:
        from _label_ops import _load_font
    return _load_font(size)[0]


def _wrap(draw, text, font, max_w):
    lines = []
    for para in text.split("\n"):
        line = ""
        for word in para.split():
            test = word if not line else line + " " + word
            if line and draw.textlength(test, font=font) > max_w:
                lines.append(line)
                line = word
            else:
                line = test
        lines.append(line)
    return lines


def _lora_label(row):
    name = str(row.get("lora", "")).replace("\\", "/").rsplit("/", 1)[-1]
    if name.lower().endswith(".safetensors"):
        name = name[:-len(".safetensors")]
    return f"{name} {float(row.get('strength', 1.0)):.2f}"


def render_preview(boxes, width, height, bg=None, brightness=50):
    """Boxes, captions and LoRAs over the background (or black), long edge <= 1024 px."""
    import numpy as np
    import torch
    from PIL import Image, ImageDraw, ImageEnhance

    if bg is not None:
        iw, ih = bg.size
        long_edge = max(iw, ih)
        scale = min(1.0, PREVIEW_LONG_EDGE / long_edge) if long_edge > 0 else 1.0
        rw, rh = max(1, round(iw * scale)), max(1, round(ih * scale))
        base = bg.convert("RGB").resize((rw, rh), Image.LANCZOS)
        if brightness < 100:
            base = ImageEnhance.Brightness(base).enhance(max(0.0, brightness / 100.0))
        img = base.convert("RGBA")
    else:
        long_edge = max(width, height)
        scale = min(1.0, PREVIEW_LONG_EDGE / long_edge) if long_edge > 0 else 1.0
        rw, rh = max(1, round(width * scale)), max(1, round(height * scale))
        img = Image.new("RGBA", (rw, rh), (0, 0, 0, 255))
    overlay = Image.new("RGBA", (rw, rh), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    fs = max(10, round(rh / 64))
    font = _font(fs)
    tag_font = _font(max(9, fs - 2))
    lh = fs + 2

    for i, box in enumerate(boxes):
        if not layout_ops.visible(box):
            continue
        palette = [c for c in (box.get("palette") or []) if c]
        r, g, b = _hex_rgb(palette[0]) if palette else (140, 140, 140)
        x1, y1, x2, y2 = layout_ops.edges(box)
        x1, x2 = round(x1 * rw), round(x2 * rw)
        y1, y2 = round(y1 * rh), round(y2 * rh)
        draw.rectangle([x1, y1, x2, y2], outline=(r, g, b, 255), width=2)

        pal5 = palette[:5]
        if pal5 and (x2 - x1) > 2:
            sh = max(5, fs // 2)
            seg = (x2 - x1) / len(pal5)
            for p, hexc in enumerate(pal5):
                draw.rectangle([x1 + round(p * seg), y1, x1 + round((p + 1) * seg), y1 + sh], fill=_hex_rgb(hexc))

        tag = str(i + 1).zfill(2)
        name = str(box.get("name") or "").strip()
        if name:
            tag = f"{tag} {name}"
        tw = draw.textlength(tag, font=tag_font)
        draw.rectangle([x1, y1, x1 + tw + 6, y1 + fs + 2], fill=(r, g, b, 255))
        tagfill = (0, 0, 0, 255) if (0.299 * r + 0.587 * g + 0.114 * b) > 140 else (255, 255, 255, 255)
        draw.text((x1 + 3, y1 + 1), tag, fill=tagfill, font=tag_font)

        body = box.get("desc", "") or ""
        if box.get("type") == "text" and box.get("text"):
            body = '"%s"%s' % (box["text"], " — " + body if body else "")
        loras = layout_ops.lora_rows(box.get("loras"))
        ty = y1 + fs + 5
        if body and (x2 - x1) > 8:
            for line in _wrap(draw, body, font, x2 - x1 - 8):
                if ty > y2 - (lh * len(loras)):
                    break
                draw.text((x1 + 4, ty), line, fill=_readable((r, g, b)) + (255,), font=font)
                ty += lh
        # LoRAs listed at the bottom of the box
        ly = y2 - 4 - lh * len(loras)
        for row in loras:
            if ly > y1 + fs:
                draw.text((x1 + 4, ly), "◆ " + _lora_label(row), fill=(255, 214, 102, 255), font=tag_font)
            ly += lh

    img = Image.alpha_composite(img, overlay).convert("RGB")
    arr = np.asarray(img, dtype=np.float32) / 255.0
    return torch.from_numpy(arr).unsqueeze(0)


def _bg_image(image):
    if image is None:
        return None
    try:
        import numpy as np
        from PIL import Image
        return Image.fromarray((image[0].detach().cpu().numpy() * 255).clip(0, 255).astype(np.uint8))
    except Exception:
        return None


def resolve_entries(entries, available):
    """Maps every entry's LoRA name onto a file in the loras folder (raises with suggestions)."""
    return [{**e, "lora": engine._resolve_lora(e["lora"], available)} for e in entries]


class MOSSRegionalLayout:
    DESCRIPTION = (
        "Draw MOSS-Image layout boxes, caption them and give each box its own LoRAs. Outputs the "
        "MOSS layout prompt and a MODEL whose LoRAs only act inside their box (token-masked bypass). "
        "Scene LoRAs act on the whole image or only outside the LoRA boxes. Editor based on "
        "kijai's MOSS-Image Prompt Builder (KJNodes)."
    )
    SEARCH_ALIASES = ["moss", "layout", "regional lora", "bounding box", "prompt builder"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "width": ("INT", {"default": 1024, "min": 64, "max": 16384, "step": 16,
                                  "tooltip": "Generation width: the boxes are placed in its pixels."}),
                "height": ("INT", {"default": 1024, "min": 64, "max": 16384, "step": 16,
                                   "tooltip": "Generation height: the boxes are placed in its pixels."}),
                "prompt": ("STRING", {"multiline": True, "default": "",
                                      "tooltip": "Description of the whole scene and its style (summary.caption)."}),
                "meta": ("STRING", {"default": "", "tooltip": "Optional comma-separated summary.meta tags."}),
                "canvas": (["none", *layout_ops.CANVASES], {"default": "none",
                                                             "tooltip": "Optional summary.canvas."}),
                "feather": ("FLOAT", {"default": 0.1, "min": 0.0, "max": 0.3, "step": 0.01,
                                      "tooltip": "Soft LoRA mask edge, as a fraction of the box's shorter side."}),
                "skirt": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 0.25, "step": 0.01,
                                    "tooltip": "Grows every LoRA mask by this fraction of the image's shorter side."}),
                "text_tokens": (["masked", "global"], {
                    "tooltip": "masked: box LoRAs skip the text tokens (least bleed). "
                               "global: box LoRAs also act on the text tokens (more bleed)."}),
                # Data widgets, hidden and managed by the editor.
                "elements_data": ("STRING", {"default": "", "socketless": True}),
                "scene_loras_data": ("STRING", {"default": "", "socketless": True}),
                "style_palette_data": ("STRING", {"default": "", "socketless": True}),
                "bg_brightness": ("INT", {"default": 25, "min": 0, "max": 100, "socketless": True}),
                "import_mode": (["when empty", "always"], {"default": "when empty"}),
                "output_format": ("STRING", {"default": "compact", "socketless": True}),
            },
            "optional": {
                "image": ("IMAGE", {"tooltip": "Optional background for the editor and the preview."}),
                "import_json": ("STRING", {"forceInput": True,
                                           "tooltip": "Optional MOSS-Image layout JSON to load into the editor."}),
                "bboxes": ("BOUNDING_BOX", {"forceInput": True,
                                            "tooltip": "Optional pixel boxes to seed an empty editor."}),
            },
        }

    RETURN_TYPES = ("MODEL", "STRING", "IMAGE", "MASK", "BOUNDING_BOX", "INT", "INT")
    RETURN_NAMES = ("MODEL", "prompt", "preview", "mask_preview", "bboxes", "width", "height")
    FUNCTION = "build"
    CATEGORY = "MoonPack/lora"
    OUTPUT_NODE = False

    def build(self, model, width, height, prompt="", meta="", canvas="none", feather=0.1, skirt=0.0,
              text_tokens="masked", elements_data="", scene_loras_data="", style_palette_data="",
              bg_brightness=25, import_mode="when empty", output_format="compact",
              image=None, import_json=None, bboxes=None):
        import json

        boxes = layout_ops.parse_json_list(elements_data)
        boxes_seeded = False
        if not boxes and bboxes:
            boxes = layout_ops.seed_boxes(bboxes, width, height)
            boxes_seeded = bool(boxes)

        imported = layout_ops.loads_caption(import_json) if import_json else None
        if imported is not None and not isinstance(imported.get("items"), list):
            imported = None
        used_import = imported is not None and (import_mode == "always" or not boxes)
        scene_loras = layout_ops.parse_json_list(scene_loras_data)
        if used_import:
            # Extras come from the layout's own MoonPack sidecar (templates / Copy) or, when a wired
            # layout replaces the boxes on every run ("always"), from the current boxes by position.
            side = imported.get(layout_ops.SIDECAR_KEY) if isinstance(imported.get(layout_ops.SIDECAR_KEY), dict) else None
            if side is not None:
                extras, scene_loras = side.get("boxes"), side.get("scene_loras") or scene_loras
            else:
                extras = [{k: b.get(k) for k in layout_ops.EXTRA_KEYS if k in b}
                          for b in boxes if isinstance(b, dict) and not b.get("nobbox")]
            s = imported.get("summary") if isinstance(imported.get("summary"), dict) else {}
            prompt = layout_ops.strip_triggers(str(s.get("caption") or ""), scene_loras)
            summ = layout_ops.summary(prompt, layout_ops.strs(s.get("meta")), s.get("canvas"),
                                      layout_ops.strs(s.get("palette")), scene_loras)
            boxes = layout_ops.apply_extras(layout_ops.layout_to_boxes(imported, width, height), extras)
        else:
            summ = layout_ops.summary(prompt, layout_ops.strs(meta), canvas,
                                      layout_ops.strs(layout_ops.parse_json_list(style_palette_data)), scene_loras)

        lay = layout_ops.layout(summ, boxes, width, height)
        if lay is None:
            out = summ["caption"]
        elif output_format == "pretty":
            out = layout_ops.dumps(lay)
        else:
            out = json.dumps(lay, ensure_ascii=False, separators=(",", ":"))

        box_bboxes, entries = layout_ops.regional_assignments(boxes, scene_loras)
        if entries:
            import folder_paths
            entries = resolve_entries(entries, folder_paths.get_filename_list("loras"))
        patched = engine.apply_regional_loras(model, box_bboxes, entries, feather, skirt, text_tokens == "global")

        preview = render_preview(boxes, width, height, _bg_image(image), bg_brightness)
        masks = engine.preview_masks(box_bboxes, entries, feather, skirt, width, height)

        ui = {"dims": [width, height]}
        if used_import:  # caption fills the summary widgets, boxes (with their extras) replace the editor's
            ui["caption"] = [layout_ops.dumps(imported)]
        if boxes_seeded or used_import:
            ui["boxes"] = [json.dumps(boxes)]
            if used_import:
                ui["scene_loras"] = [json.dumps(scene_loras)]
        return {"ui": ui, "result": (patched, out, preview, masks,
                                     layout_ops.bbox_outputs(boxes, width, height), width, height)}


NODE_CLASS_MAPPINGS = {
    "MoonPack_MOSSRegionalLayout": MOSSRegionalLayout,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MoonPack_MOSSRegionalLayout": "MOSS Regional Layout",
}
