"""Compositing for the Load Image (Labeled) node.

Shared by the node's own execution (`labeled_load_image_node.py`) and the
`/moonpack/label_preview` HTTP route, so the editor preview is pixel-identical
to what actually gets queued - one implementation, not two.
"""

from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont

BAR_HEIGHT_RATIO = 0.08
MIN_BAR_PX = 32
ARROW_ZONE_RATIO = 0.4
MIN_FONT_PX = 8
TEXT_WIDTH_RATIO = 0.92


def _hex_to_rgb(hex_str, fallback=(0, 0, 0)):
    if not isinstance(hex_str, str):
        return fallback
    s = hex_str.strip().lstrip("#")
    if len(s) != 6:
        return fallback
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except ValueError:
        return fallback


def _fit_text(draw, text, max_width, max_font_px):
    """Shrinks font size to fit max_width, then truncates with an ellipsis if
    even the floor size overflows. Returns (font, drawn_text)."""
    size = max(MIN_FONT_PX, max_font_px)
    font = ImageFont.load_default(size=size)
    while size > MIN_FONT_PX and draw.textlength(text, font=font) > max_width:
        size -= 1
        font = ImageFont.load_default(size=size)

    if draw.textlength(text, font=font) <= max_width:
        return font, text

    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        candidate = text[:mid] + "…"
        if draw.textlength(candidate, font=font) <= max_width:
            lo = mid
        else:
            hi = mid - 1
    return font, (text[:lo] + "…" if lo > 0 else "…")


def _draw_arrow(draw, center_x, zone_top, zone_h, point_down, color_rgb):
    zone_h = max(1, zone_h)
    arrow_h = max(4, round(zone_h * 0.55))
    arrow_w = round(arrow_h * 1.8)
    center_y = zone_top + zone_h / 2

    if point_down:
        points = [
            (center_x - arrow_w / 2, center_y - arrow_h / 2),
            (center_x + arrow_w / 2, center_y - arrow_h / 2),
            (center_x, center_y + arrow_h / 2),
        ]
    else:
        points = [
            (center_x - arrow_w / 2, center_y + arrow_h / 2),
            (center_x + arrow_w / 2, center_y + arrow_h / 2),
            (center_x, center_y - arrow_h / 2),
        ]
    draw.polygon(points, fill=color_rgb)


def compose_labeled_image(img, text, position, show_label, show_arrow,
                           background_hex, text_color_hex, border_width):
    """img must already be a converted RGB PIL.Image. Returns a new RGB PIL.Image
    with the label bar (text and/or arrow) added as extra top/bottom space, and
    an optional inset border - never changes width, never adds height beyond the
    bar itself."""
    width, height = img.size
    bg_rgb = _hex_to_rgb(background_hex, (0, 0, 0))
    text_rgb = _hex_to_rgb(text_color_hex, (255, 255, 255))

    bar_height = max(MIN_BAR_PX, round(height * BAR_HEIGHT_RATIO)) if (show_label or show_arrow) else 0
    canvas = PILImage.new("RGB", (width, height + bar_height), bg_rgb)
    canvas.paste(img, (0, bar_height if position == "top" else 0))

    if bar_height:
        bar_top = 0 if position == "top" else height
        draw = ImageDraw.Draw(canvas)
        point_down = position == "top"  # bar sits above the photo either way it needs to point toward it

        if show_label and show_arrow:
            arrow_zone_h = max(8, round(bar_height * ARROW_ZONE_RATIO))
            text_zone_h = bar_height - arrow_zone_h
            if position == "top":
                text_zone_top, arrow_zone_top = bar_top, bar_top + text_zone_h
            else:
                arrow_zone_top, text_zone_top = bar_top, bar_top + arrow_zone_h
        elif show_arrow:
            arrow_zone_h, text_zone_h = bar_height, 0
            arrow_zone_top = bar_top
        else:
            text_zone_h, arrow_zone_h = bar_height, 0
            text_zone_top = bar_top

        if show_arrow:
            _draw_arrow(draw, width / 2, arrow_zone_top, arrow_zone_h, point_down, text_rgb)

        if show_label and text:
            max_font_px = max(MIN_FONT_PX, round(text_zone_h * 0.62))
            font, shown = _fit_text(draw, text, width * TEXT_WIDTH_RATIO, max_font_px)
            stroke_width = max(1, round(font.size / 18))
            draw.text(
                (width / 2, text_zone_top + text_zone_h / 2),
                shown, font=font, fill=text_rgb, stroke_width=stroke_width,
                stroke_fill=text_rgb, anchor="mm",
            )

    if border_width > 0:
        bw = min(border_width, min(canvas.size) // 4)
        draw = ImageDraw.Draw(canvas)
        for i in range(bw):
            draw.rectangle(
                [i, i, canvas.width - 1 - i, canvas.height - 1 - i],
                outline=bg_rgb,
            )

    return canvas
