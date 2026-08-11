import math

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image as PILImage

CATEGORY = "MoonPack/image"

_FILL_PRESETS = {
    "black": (0.0, 0.0, 0.0),
    "white": (1.0, 1.0, 1.0),
    "gray": (0.5, 0.5, 0.5),
}

_TORCH_MODES = ("nearest", "bilinear", "bicubic")


def _resize(img, height, width, mode="bicubic"):
    # img: [1, H, W, C] -> resize to [1, height, width, C]
    _, h, w, c = img.shape
    if h == height and w == width:
        return img.clamp(0.0, 1.0)
    if mode == "lanczos" and c == 3:
        return _resize_lanczos(img, height, width)
    torch_mode = mode if mode in _TORCH_MODES else "bicubic"
    t = img.permute(0, 3, 1, 2)
    kwargs = {} if torch_mode == "nearest" else {"align_corners": False}
    t = F.interpolate(t, size=(height, width), mode=torch_mode, **kwargs)
    return t.clamp(0.0, 1.0).permute(0, 2, 3, 1)


def _resize_lanczos(img, height, width):
    arr = (img[0].clamp(0.0, 1.0).cpu().numpy() * 255.0).round().astype(np.uint8)
    resized = PILImage.fromarray(arr, mode="RGB").resize((width, height), PILImage.LANCZOS)
    out = torch.from_numpy(np.array(resized)).to(dtype=img.dtype) / 255.0
    return out.unsqueeze(0).to(img.device)


def _cover_fit(img, height, width, mode="bicubic"):
    # Scale img to cover a height x width cell, then center-crop the overflow.
    _, h, w, _ = img.shape
    scale = max(height / h, width / w)
    resized = _resize(img, max(1, round(h * scale)), max(1, round(w * scale)), mode)
    _, rh, rw, _ = resized.shape
    top = (rh - height) // 2
    left = (rw - width) // 2
    return resized[:, top:top + height, left:left + width, :]


def _match_channels(img, channels):
    c = img.shape[-1]
    if c == channels:
        return img
    return img[..., :channels] if c > channels else F.pad(img, (0, channels - c))


def _normalize_refs(raw, max_side, mode):
    """Flattens whatever arrives for reference_images (a native list of per-image tensors from
    Image List, or a single legacy stacked-batch tensor) into a flat list of [1,H,W,C] tensors,
    each keeping its native resolution (unless it exceeds max_side, in which case it's scaled
    down, never up, so one huge outlier can't blow up the grid/strip size)."""
    flat = []
    if raw is None:
        return flat
    for item in raw:
        if item is None:
            continue
        for i in range(item.shape[0]):
            img = item[i:i + 1]
            if max_side > 0:
                _, h, w, _ = img.shape
                longest = max(h, w)
                if longest > max_side:
                    scale = max_side / longest
                    img = _resize(img, max(1, round(h * scale)), max(1, round(w * scale)), mode)
            flat.append(img)
    return flat


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
                        "Which side of the main image the strip goes on. The strip's row-vs-column "
                        "layout is auto-picked from the main image's longest side; 'top'/'left' place "
                        "the strip before the main image along that axis, 'bottom'/'right' place it after. "
                        "Ignored if main_image is unconnected."
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

    def concat(self, reference_images, side, ref_scale, offset, fill, interpolation, max_ref_side,
               invert_mask, main_image=None):
        side = side[0]
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
        n = len(refs)
        channels = refs[0].shape[-1]
        device, dtype = refs[0].device, refs[0].dtype

        cols = max(1, math.ceil(math.sqrt(n)))
        rows = math.ceil(n / cols)
        # The largest reference sets the cell size, so smaller ones get upscaled up to
        # match instead of the smallest one capping every tile's resolution.
        cell_h = max(ref.shape[1] for ref in refs)
        cell_w = max(ref.shape[2] for ref in refs)

        if fill == "edge_average":
            fill_rgb = torch.cat([ref.reshape(-1, ref.shape[-1]) for ref in refs], dim=0).mean(dim=0)
        else:
            fill_rgb = torch.tensor(_FILL_PRESETS[fill], device=device, dtype=dtype)
            if channels != 3:
                fill_rgb = fill_rgb.mean().expand(channels)

        canvas_h, canvas_w = rows * cell_h, cols * cell_w
        canvas = fill_rgb.view(1, 1, 1, channels).expand(1, canvas_h, canvas_w, channels).clone()
        mask = torch.zeros((1, canvas_h, canvas_w), device=device, dtype=dtype)

        for i, ref in enumerate(refs):
            r, c = divmod(i, cols)
            tile = _cover_fit(_match_channels(ref, channels), cell_h, cell_w, interpolation)
            y, x = r * cell_h, c * cell_w
            canvas[:, y:y + cell_h, x:x + cell_w, :] = tile
            mask[:, y:y + cell_h, x:x + cell_w] = 1.0

        if invert_mask:
            mask = 1.0 - mask

        return (canvas, mask)


NODE_CLASS_MAPPINGS = {
    "MoonPack_ReferenceConcat": ReferenceConcat,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MoonPack_ReferenceConcat": "Reference Concat",
}
