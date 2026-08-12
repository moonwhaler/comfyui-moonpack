import math

import torch

from ._image_ops import FILL_PRESETS as _FILL_PRESETS
from ._image_ops import contain_fit as _contain_fit
from ._image_ops import cover_fit as _cover_fit
from ._image_ops import match_channels as _match_channels
from ._image_ops import normalize_refs as _normalize_refs
from ._image_ops import resize as _resize

CATEGORY = "MoonPack/image"


class ReferenceGrid:
    DESCRIPTION = (
        "Arranges a batch of reference images into a contact-sheet grid, with full "
        "control over column count, per-cell fit mode, cell sizing, fill order and "
        "alignment of an incomplete last row/column. Accepts either a MoonPack Image "
        "List (keeps each reference's native resolution) or a plain stacked IMAGE batch."
    )
    SEARCH_ALIASES = ["grid", "contact sheet", "reference", "mosaic", "tile"]
    INPUT_IS_LIST = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "reference_images": ("IMAGE", {
                    "tooltip": (
                        "Reference images to arrange into a grid. Connect a MoonPack Image List "
                        "to keep each image's native resolution (recommended for mixed-resolution "
                        "references), or a plain stacked IMAGE batch."
                    ),
                }),
                "columns": ("INT", {
                    "default": 0, "min": 0, "max": 8192, "step": 1,
                    "tooltip": "Number of grid columns. 0 = auto (ceil(sqrt(n)), a roughly square grid).",
                }),
                "fit_mode": (["cover", "contain", "stretch"], {
                    "default": "cover",
                    "tooltip": (
                        "How each reference fills its cell. 'cover': scale to fill, center-crop "
                        "the overflow. 'contain': scale to fit inside, pad the leftover with fill "
                        "color. 'stretch': force an exact fit, distorting aspect ratio."
                    ),
                }),
                "cell_size_source": (["largest", "smallest", "average"], {
                    "default": "largest",
                    "tooltip": (
                        "Which references set the cell size (per axis, independently): the "
                        "largest reference (upscales smaller ones), the smallest (downscales "
                        "larger ones), or the average dimensions."
                    ),
                }),
                "cell_width": ("INT", {
                    "default": 0, "min": 0, "max": 8192, "step": 1,
                    "tooltip": "Fixed cell width override. 0 = use cell_size_source.",
                }),
                "cell_height": ("INT", {
                    "default": 0, "min": 0, "max": 8192, "step": 1,
                    "tooltip": "Fixed cell height override. 0 = use cell_size_source.",
                }),
                "fill_direction": (["row_major", "column_major"], {
                    "default": "row_major",
                    "tooltip": (
                        "Order references fill the grid. 'row_major': left to right, then top to "
                        "bottom. 'column_major': top to bottom, then left to right."
                    ),
                }),
                "last_row_align": (["left", "center", "right"], {
                    "default": "left",
                    "tooltip": (
                        "Alignment of the incomplete trailing row (row_major) or column "
                        "(column_major, where left/right act as top/bottom) when the reference "
                        "count doesn't evenly divide the grid."
                    ),
                }),
                "fill": (["black", "white", "gray", "edge_average"], {
                    "default": "black",
                    "tooltip": (
                        "Background color for empty cells and any 'contain' padding. "
                        "'edge_average' uses the mean color of all references."
                    ),
                }),
                "interpolation": (["nearest", "bilinear", "bicubic", "lanczos"], {
                    "default": "bicubic",
                    "tooltip": "Resampling filter used whenever a reference image is resized.",
                }),
                "max_ref_side": ("INT", {
                    "default": 0, "min": 0, "max": 8192, "step": 1,
                    "tooltip": (
                        "Caps each reference's longest side to this many pixels before any other "
                        "processing (downscale only, never upscales). Keeps one oversized "
                        "reference from blowing up the grid size. 0 = no cap."
                    ),
                }),
                "invert_mask": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "Flip the output mask (empty/padding area becomes 1.0 instead of the reference area).",
                }),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("image", "mask")
    FUNCTION = "build"
    CATEGORY = CATEGORY

    def build(self, reference_images, columns, fit_mode, cell_size_source, cell_width, cell_height,
              fill_direction, last_row_align, fill, interpolation, max_ref_side, invert_mask):
        columns = columns[0]
        fit_mode = fit_mode[0]
        cell_size_source = cell_size_source[0]
        cell_width = cell_width[0]
        cell_height = cell_height[0]
        fill_direction = fill_direction[0]
        last_row_align = last_row_align[0]
        fill = fill[0]
        interpolation = interpolation[0]
        max_ref_side = max_ref_side[0]
        invert_mask = invert_mask[0]

        refs = _normalize_refs(reference_images, max_ref_side, interpolation)
        if not refs:
            raise ValueError("ReferenceGrid: connect at least one reference image.")

        n = len(refs)
        channels = refs[0].shape[-1]
        device, dtype = refs[0].device, refs[0].dtype

        cols = columns if columns > 0 else max(1, math.ceil(math.sqrt(n)))
        rows = math.ceil(n / cols)

        heights = [ref.shape[1] for ref in refs]
        widths = [ref.shape[2] for ref in refs]
        if cell_size_source == "smallest":
            src_h, src_w = min(heights), min(widths)
        elif cell_size_source == "average":
            src_h = round(sum(heights) / n)
            src_w = round(sum(widths) / n)
        else:
            src_h, src_w = max(heights), max(widths)
        cell_h = cell_height if cell_height > 0 else src_h
        cell_w = cell_width if cell_width > 0 else src_w

        if fill == "edge_average":
            fill_rgb = torch.cat([ref.reshape(-1, ref.shape[-1]) for ref in refs], dim=0).mean(dim=0)
        else:
            fill_rgb = torch.tensor(_FILL_PRESETS[fill], device=device, dtype=dtype)
            if channels != 3:
                fill_rgb = fill_rgb.mean().expand(channels)

        canvas_h, canvas_w = rows * cell_h, cols * cell_w
        canvas = fill_rgb.view(1, 1, 1, channels).expand(1, canvas_h, canvas_w, channels).clone()
        mask = torch.zeros((1, canvas_h, canvas_w), device=device, dtype=dtype)

        positions = self._positions(n, cols, rows, fill_direction, last_row_align)

        for ref, (r, c) in zip(refs, positions):
            tile_ref = _match_channels(ref, channels)
            y, x = r * cell_h, c * cell_w
            if fit_mode == "cover":
                tile = _cover_fit(tile_ref, cell_h, cell_w, interpolation)
                canvas[:, y:y + cell_h, x:x + cell_w, :] = tile
                mask[:, y:y + cell_h, x:x + cell_w] = 1.0
            elif fit_mode == "contain":
                tile, top, left, ch, cw = _contain_fit(tile_ref, cell_h, cell_w, interpolation, fill_rgb)
                canvas[:, y:y + cell_h, x:x + cell_w, :] = tile
                mask[:, y + top:y + top + ch, x + left:x + left + cw] = 1.0
            else:
                tile = _resize(tile_ref, cell_h, cell_w, interpolation)
                canvas[:, y:y + cell_h, x:x + cell_w, :] = tile
                mask[:, y:y + cell_h, x:x + cell_w] = 1.0

        if invert_mask:
            mask = 1.0 - mask

        return (canvas, mask)

    @staticmethod
    def _positions(n, cols, rows, fill_direction, align):
        """Maps flat index i (0..n-1) to (row, col), honoring fill_direction and applying
        last_row_align to whichever trailing group (last row, or last column for
        column_major) is incomplete."""
        if fill_direction == "row_major":
            full_rows = n // cols
            remainder = n - full_rows * cols
            offset = 0
            if remainder and align != "left":
                gap = cols - remainder
                offset = gap // 2 if align == "center" else gap
            positions = []
            for i in range(n):
                r, c = divmod(i, cols)
                if r == full_rows and remainder:
                    c += offset
                positions.append((r, c))
            return positions
        else:
            full_cols = n // rows
            remainder = n - full_cols * rows
            offset = 0
            if remainder and align != "left":
                gap = rows - remainder
                offset = gap // 2 if align == "center" else gap
            positions = []
            for i in range(n):
                c, r = divmod(i, rows)
                if c == full_cols and remainder:
                    r += offset
                positions.append((r, c))
            return positions


NODE_CLASS_MAPPINGS = {
    "MoonPack_ReferenceGrid": ReferenceGrid,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MoonPack_ReferenceGrid": "Reference Grid",
}
