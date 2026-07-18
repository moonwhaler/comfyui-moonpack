import os

import numpy as np
from PIL import Image

try:
    import folder_paths  # ComfyUI runtime; absent under bare pytest.
except ImportError:  # pragma: no cover
    folder_paths = None

CATEGORY = "MoonPack/image"

_EXT = {"png": "png", "jpeg": "jpg", "webp": "webp"}


def _encode(img, fp, fmt, quality, lossless):
    """Write img to fp in fmt with NO metadata (no pnginfo/exif/xmp)."""
    if fmt == "png":
        img.save(fp, "PNG", pnginfo=None, compress_level=4)
    elif fmt == "jpeg":
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.save(fp, "JPEG", quality=int(quality))
    elif fmt == "webp":
        img.save(fp, "WEBP", quality=int(quality), lossless=bool(lossless))
    else:
        raise ValueError(f"unknown format: {fmt}")


class CleanSaveImage:
    DESCRIPTION = (
        "Saves images to disk with ZERO metadata: no EXIF, no PNG tEXt/iTXt/zTXt "
        "chunks, no embedded workflow/prompt/AI-generation comments. Drop-in "
        "replacement for SaveImage for privacy-safe output. PNG/JPEG/WEBP."
    )
    SEARCH_ALIASES = ["metadata", "exif", "strip", "clean", "save", "privacy", "scrub"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE", {"tooltip": "Image batch to save (shape [B, H, W, C])."}),
                "filename_prefix": ("STRING", {
                    "default": "ComfyUI",
                    "tooltip": "Prefix for saved files; saved under the ComfyUI output folder.",
                }),
                "format": (["png", "jpeg", "webp"], {
                    "default": "png",
                    "tooltip": "Output file format.",
                }),
                "quality": ("INT", {
                    "default": 90, "min": 1, "max": 100,
                    "tooltip": "JPEG/WEBP quality. Ignored for PNG.",
                }),
                "lossless_webp": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "WEBP only: lossless encoding.",
                }),
            },
            "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"},
        }

    RETURN_TYPES = ()
    FUNCTION = "save"
    OUTPUT_NODE = True
    CATEGORY = CATEGORY

    def save(self, images, filename_prefix, format, quality, lossless_webp,
             prompt=None, extra_pnginfo=None):
        # prompt / extra_pnginfo intentionally discarded — that is the point.
        ext = _EXT[format]
        full_output_folder, filename, counter, subfolder, _ = \
            folder_paths.get_save_image_path(
                filename_prefix, folder_paths.get_output_directory())
        results = []
        for i in range(images.shape[0]):
            arr = (images[i].cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
            img = Image.fromarray(arr)
            file = f"{filename}_{counter:05}_.{ext}"
            _encode(img, os.path.join(full_output_folder, file),
                    format, quality, lossless_webp)
            results.append({"filename": file, "subfolder": subfolder, "type": "output"})
            counter += 1
        return {"ui": {"images": results}}


NODE_CLASS_MAPPINGS = {"MoonPack_CleanSaveImage": CleanSaveImage}
NODE_DISPLAY_NAME_MAPPINGS = {"MoonPack_CleanSaveImage": "Clean Save Image"}
