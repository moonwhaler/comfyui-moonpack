import math

import torch

from ._image_ops import FILL_PRESETS as _FILL_PRESETS
from ._image_ops import match_channels as _match_channels
from ._image_ops import normalize_refs as _normalize_refs
from ._image_ops import resize as _resize

CATEGORY = "MoonPack/image"


class ReferenceConcat:
    DESCRIPTION = (
        "Concatenates a batch of reference images into a strip alongside a main image, "
        "for feeding identity references to video models without losing subject identity. "
        "The strip is placed on the main image's longest side, sized to exactly match that "
        "side's length (no resolution cap), and the main image is never shrunk. 'offset' "
        "slides the strip further into the main image (overlap) or further outside it (gap). "
        "If main_image is left unconnected, outputs a contact-sheet grid of just the "
        "reference images instead (side/ref_scale/offset are ignored in that mode). "
        "Accepts either a MoonPack Image List (keeps each reference's native resolution) or "
        "a plain stacked IMAGE batch."
    )
    SEARCH_ALIASES = ["concat", "reference", "identity", "first frame", "kjnodes", "video", "contact sheet"]
    INPUT_IS_LIST = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "reference_images": ("IMAGE", {
                    "tooltip": (
                        "Reference images to concatenate. Connect a MoonPack Image List to keep each "
                        "image's native resolution (recommended for mixed-resolution references), or a "
                        "plain stacked IMAGE batch."
                    ),
                }),
                "side": (["top", "bottom", "left", "right"], {
                    "default": "top",
                    "tooltip": (
                        "Which side of the main image the strip goes on. By default the strip's "
                        "row-vs-column layout is auto-picked from the main image's longest side, and "
                        "'top'/'left' place the strip before the main image along that axis while "
                        "'bottom'/'right' place it after. Enable force_side to make this side always "
                        "win instead. Ignored if main_image is unconnected."
                    ),
                }),
                "force_side": ("BOOLEAN", {
                    "default": False,
                    "tooltip": (
                        "Force the strip onto the exact side chosen above, overriding the automatic "
                        "row-vs-column pick: 'left'/'right' always stack the strip as a full-height "
                        "column, 'top'/'bottom' always stack it as a full-width row. The resulting strip "
                        "may end up thin if this fights the main image's orientation. Ignored if "
                        "main_image is unconnected."
                    ),
                }),
                "ref_scale": ("FLOAT", {
                    "default": 0.5, "min": 0.01, "max": 4.0, "step": 0.01,
                    "tooltip": (
                        "Strip thickness as a fraction of the main image's cross-side. The main image's "
                        "long side is a cap: the strip is only scaled down (never stretched) if it would "
                        "overflow. Ignored if main_image is unconnected."
                    ),
                }),
                "offset": ("INT", {
                    "default": 0, "min": -8192, "max": 8192, "step": 1,
                    "tooltip": (
                        "Positive: slide the strip into the main image, covering that many pixels of it. "
                        "Negative: pull the strip away from the main image, leaving a filled gap. "
                        "Clamped so the main image is never cropped or shrunk. Ignored if main_image is unconnected."
                    ),
                }),
                "fill": (["black", "white", "gray", "edge_average"], {
                    "default": "black",
                    "tooltip": (
                        "Background color for any gap/leftover space. 'edge_average' samples the main "
                        "image's edge nearest the strip, or the average of all references when main_image "
                        "is unconnected."
                    ),
                }),
                "interpolation": (["nearest", "bilinear", "bicubic", "lanczos"], {
                    "default": "bicubic",
                    "tooltip": (
                        "Resampling filter used whenever a reference image is resized, including "
                        "upscaling references smaller than the target size."
                    ),
                }),
                "max_ref_side": ("INT", {
                    "default": 0, "min": 0, "max": 8192, "step": 1,
                    "tooltip": (
                        "Caps each reference's longest side to this many pixels before any other "
                        "processing (downscale only, never upscales). Keeps one oversized reference "
                        "from blowing up the contact-sheet or strip size. 0 = no cap."
                    ),
                }),
                "invert_mask": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "Flip the output mask (main-image/empty-cell area becomes 1.0 instead of the reference area).",
                }),
            },
            "optional": {
                "main_image": ("IMAGE", {
                    "tooltip": (
                        "Main / first-frame image. If a batch is passed, only the first frame is used. "
                        "Leave unconnected to instead output a contact-sheet grid of the reference images."
                    ),
                }),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("image", "mask")
    FUNCTION = "concat"
    CATEGORY = CATEGORY

    def concat(self, reference_images, side, force_side, ref_scale, offset, fill, interpolation, max_ref_side,
               invert_mask, main_image=None):
        side = side[0]
        force_side = force_side[0]
        ref_scale = ref_scale[0]
        offset = offset[0]
        fill = fill[0]
        interpolation = interpolation[0]
        max_ref_side = max_ref_side[0]
        invert_mask = invert_mask[0]
        main = main_image[0][:1] if main_image is not None else None

        refs = _normalize_refs(reference_images, max_ref_side, interpolation)

        if main is None:
            if not refs:
                raise ValueError("ReferenceConcat: connect main_image, reference_images, or both.")
            return self._build_sheet(refs, fill, interpolation, invert_mask)

        _, main_h, main_w, channels = main.shape
        device, dtype = main.device, main.dtype

        if not refs:
            mask = torch.zeros((1, main_h, main_w), device=device, dtype=dtype)
            if invert_mask:
                mask = 1.0 - mask
            return (main, mask)

        if force_side:
            axis = "column" if side in ("left", "right") else "row"
        else:
            axis = "row" if main_w >= main_h else "column"
        before = side in ("top", "left")
        main_cross = main_h if axis == "row" else main_w
        target_length = main_w if axis == "row" else main_h

        nominal_thickness = max(1, round(ref_scale * main_cross))

        # length-per-unit-thickness for each ref: width/height for a row strip, height/width for a column strip.
        ratios = []
        for ref in refs:
            _, rh, rw, _ = ref.shape
            ratios.append((rw / rh) if axis == "row" else (rh / rw))

        if fill == "edge_average":
            edge_side = ("top" if axis == "row" else "left") if before else ("bottom" if axis == "row" else "right")
            if edge_side == "top":
                fill_rgb = main[0, 0, :, :].mean(dim=0)
            elif edge_side == "bottom":
                fill_rgb = main[0, -1, :, :].mean(dim=0)
            elif edge_side == "left":
                fill_rgb = main[0, :, 0, :].mean(dim=0)
            else:
                fill_rgb = main[0, :, -1, :].mean(dim=0)
        else:
            fill_rgb = torch.tensor(_FILL_PRESETS[fill], device=device, dtype=dtype)
            if channels != 3:
                fill_rgb = fill_rgb.mean().expand(channels)

        # ref_scale sets the nominal thickness directly. target_length is a cap, not a
        # forced fit: only scale down (never stretch) if the natural strip would overflow it.
        natural_total_length = sum(ratios) * nominal_thickness
        if natural_total_length > target_length:
            final_thickness = max(1, round(nominal_thickness * (target_length / natural_total_length)))
        else:
            final_thickness = nominal_thickness

        lengths = [max(1, round(final_thickness * ratio)) for ratio in ratios]
        strip_length = sum(lengths)
        if strip_length > target_length:
            # Rounding pushed a couple pixels past the cap; trim the last tile back to it.
            lengths[-1] = max(1, lengths[-1] - (strip_length - target_length))
            strip_length = sum(lengths)

        tiles = []
        for ref, length in zip(refs, lengths):
            ref = _match_channels(ref, channels)
            if axis == "row":
                tiles.append(_resize(ref, final_thickness, length, interpolation))
            else:
                tiles.append(_resize(ref, length, final_thickness, interpolation))

        strip = torch.cat(tiles, dim=2 if axis == "row" else 1)

        pad = target_length - strip_length
        if pad > 0:
            pad_shape = (1, final_thickness, pad, channels) if axis == "row" else (1, pad, final_thickness, channels)
            pad_tile = fill_rgb.view(1, 1, 1, channels).expand(pad_shape).clone()
            strip = torch.cat([strip, pad_tile], dim=2 if axis == "row" else 1)

        max_offset = min(final_thickness, main_cross)
        clamped_offset = min(offset, max_offset)

        if axis == "row":
            canvas_h = main_h + final_thickness - clamped_offset
            canvas_w = main_w
        else:
            canvas_h = main_h
            canvas_w = main_w + final_thickness - clamped_offset

        canvas = fill_rgb.view(1, 1, 1, channels).expand(1, canvas_h, canvas_w, channels).clone()
        mask = torch.zeros((1, canvas_h, canvas_w), device=device, dtype=dtype)

        if axis == "row":
            if before:
                main_start, strip_start = final_thickness - clamped_offset, 0
            else:
                main_start, strip_start = 0, main_h - clamped_offset
            canvas[:, main_start:main_start + main_h, :, :] = main
            canvas[:, strip_start:strip_start + final_thickness, :, :] = strip
            mask[:, strip_start:strip_start + final_thickness, :] = 1.0
        else:
            if before:
                main_start, strip_start = final_thickness - clamped_offset, 0
            else:
                main_start, strip_start = 0, main_w - clamped_offset
            canvas[:, :, main_start:main_start + main_w, :] = main
            canvas[:, :, strip_start:strip_start + final_thickness, :] = strip
            mask[:, :, strip_start:strip_start + final_thickness] = 1.0

        if invert_mask:
            mask = 1.0 - mask

        return (canvas, mask)

    def _build_sheet(self, refs, fill, interpolation, invert_mask):
        # Justified-row layout (the algorithm behind Flickr/Google-Photos style contact
        # sheets): each row's images are scaled to a shared row height derived from their
        # own aspect ratios, so a wide reference gets a wide (or standalone) row and a tall
        # one gets a narrow row - never squeezed to match an unrelated reference's cell size.
        n = len(refs)
        channels = refs[0].shape[-1]
        device, dtype = refs[0].device, refs[0].dtype

        if fill == "edge_average":
            fill_rgb = torch.cat([ref.reshape(-1, ref.shape[-1]) for ref in refs], dim=0).mean(dim=0)
        else:
            fill_rgb = torch.tensor(_FILL_PRESETS[fill], device=device, dtype=dtype)
            if channels != 3:
                fill_rgb = fill_rgb.mean().expand(channels)

        aspects = [ref.shape[2] / ref.shape[1] for ref in refs]
        avg_h = sum(ref.shape[1] for ref in refs) / n
        avg_w = sum(ref.shape[2] for ref in refs) / n
        cols = max(1, math.ceil(math.sqrt(n)))
        # Target width of a fully justified row, and the row height below which a row is
        # considered "full" - both derived from the references themselves, so the overall
        # canvas stays in the same ballpark as the old sqrt(n) grid without hardcoding a size.
        target_width = avg_w * cols
        target_row_height = avg_h

        row_groups = []
        current, aspect_sum = [], 0.0
        for i, a in enumerate(aspects):
            current.append(i)
            aspect_sum += a
            natural_height = target_width / aspect_sum
            if natural_height <= target_row_height:
                row_groups.append((current, natural_height))
                current, aspect_sum = [], 0.0
        if current:
            # Leftover row too sparse to fill target_width at target_row_height - use the
            # target height directly rather than stretching it taller to force-justify.
            row_groups.append((current, target_row_height))

        rows = []
        for group, height in row_groups:
            row_height = max(1, round(height))
            widths = [max(1, round(row_height * aspects[i])) for i in group]
            rows.append((group, row_height, widths))

        canvas_h = sum(row_height for _, row_height, _ in rows)
        canvas_w = max(sum(widths) for _, _, widths in rows)
        canvas = fill_rgb.view(1, 1, 1, channels).expand(1, canvas_h, canvas_w, channels).clone()
        mask = torch.zeros((1, canvas_h, canvas_w), device=device, dtype=dtype)

        y = 0
        for group, row_height, widths in rows:
            x = 0
            for i, width in zip(group, widths):
                tile = _resize(_match_channels(refs[i], channels), row_height, width, interpolation)
                canvas[:, y:y + row_height, x:x + width, :] = tile
                mask[:, y:y + row_height, x:x + width] = 1.0
                x += width
            y += row_height

        if invert_mask:
            mask = 1.0 - mask

        return (canvas, mask)


NODE_CLASS_MAPPINGS = {
    "MoonPack_ReferenceConcat": ReferenceConcat,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MoonPack_ReferenceConcat": "Reference Concat",
}
