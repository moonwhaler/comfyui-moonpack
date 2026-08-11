import math

import torch
import torch.nn.functional as F

CATEGORY = "MoonPack/image"

_FILL_PRESETS = {
    "black": (0.0, 0.0, 0.0),
    "white": (1.0, 1.0, 1.0),
    "gray": (0.5, 0.5, 0.5),
}


def _resize(img, height, width):
    # img: [1, H, W, C] -> resize to [1, height, width, C]
    t = img.permute(0, 3, 1, 2)
    t = F.interpolate(t, size=(height, width), mode="bilinear", align_corners=False)
    return t.clamp(0.0, 1.0).permute(0, 2, 3, 1)


def _cover_fit(img, height, width):
    # Scale img to cover a height x width cell, then center-crop the overflow.
    _, h, w, _ = img.shape
    scale = max(height / h, width / w)
    resized = _resize(img, max(1, round(h * scale)), max(1, round(w * scale)))
    _, rh, rw, _ = resized.shape
    top = (rh - height) // 2
    left = (rw - width) // 2
    return resized[:, top:top + height, left:left + width, :]


def _median(values):
    s = sorted(values)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


class ReferenceConcat:
    DESCRIPTION = (
        "Concatenates a batch of reference images into a strip alongside a main image, "
        "for feeding identity references to video models without losing subject identity. "
        "The strip is placed on the main image's longest side, sized to exactly match that "
        "side's length (no resolution cap), and the main image is never shrunk. 'offset' "
        "slides the strip further into the main image (overlap) or further outside it (gap). "
        "If main_image is left unconnected, outputs a contact-sheet grid of just the "
        "reference images instead (side/ref_scale/offset are ignored in that mode)."
    )
    SEARCH_ALIASES = ["concat", "reference", "identity", "first frame", "kjnodes", "video", "contact sheet"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "reference_images": ("IMAGE", {
                    "tooltip": "Batch of reference images to concatenate as an identity strip.",
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

    def concat(self, reference_images, side, ref_scale, offset, fill, invert_mask, main_image=None):
        if main_image is None:
            if reference_images is None or reference_images.shape[0] == 0:
                raise ValueError("ReferenceConcat: connect main_image, reference_images, or both.")
            return self._build_sheet(reference_images, fill, invert_mask)

        main = main_image[:1]
        _, main_h, main_w, channels = main.shape
        device, dtype = main.device, main.dtype

        if reference_images is None or reference_images.shape[0] == 0:
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
        for i in range(reference_images.shape[0]):
            _, rh, rw, _ = reference_images[i:i + 1].shape
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
        for i in range(reference_images.shape[0]):
            ref = reference_images[i:i + 1]
            _, rh, rw, rc = ref.shape
            if rc != channels:
                ref = ref[..., :channels] if rc > channels else F.pad(ref, (0, channels - rc))
            length = lengths[i]
            if axis == "row":
                tiles.append(_resize(ref, final_thickness, length))
            else:
                tiles.append(_resize(ref, length, final_thickness))

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

    def _build_sheet(self, reference_images, fill, invert_mask):
        n, _, _, channels = reference_images.shape
        device, dtype = reference_images.device, reference_images.dtype

        cols = max(1, math.ceil(math.sqrt(n)))
        rows = math.ceil(n / cols)
        cell_h = max(1, round(_median([reference_images[i].shape[0] for i in range(n)])))
        cell_w = max(1, round(_median([reference_images[i].shape[1] for i in range(n)])))

        if fill == "edge_average":
            fill_rgb = reference_images.reshape(-1, channels).mean(dim=0)
        else:
            fill_rgb = torch.tensor(_FILL_PRESETS[fill], device=device, dtype=dtype)
            if channels != 3:
                fill_rgb = fill_rgb.mean().expand(channels)

        canvas_h, canvas_w = rows * cell_h, cols * cell_w
        canvas = fill_rgb.view(1, 1, 1, channels).expand(1, canvas_h, canvas_w, channels).clone()
        mask = torch.zeros((1, canvas_h, canvas_w), device=device, dtype=dtype)

        for i in range(n):
            r, c = divmod(i, cols)
            tile = _cover_fit(reference_images[i:i + 1], cell_h, cell_w)
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
