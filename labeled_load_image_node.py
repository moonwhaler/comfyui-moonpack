import numpy as np

try:
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover - PIL ships with ComfyUI
    Image = None
    ImageOps = None

try:
    from ._label_ops import apply_crop, compose_labeled_image
except ImportError:  # importable for tests without package context
    from _label_ops import apply_crop, compose_labeled_image

CATEGORY = "MoonPack/image"


class LabeledLoadImage:
    DESCRIPTION = (
        "Loads an image and bakes an editable caption bar into it (e.g. 'Front View', "
        "'Character A'), so a reference stays identifiable once it's combined into a "
        "bigger Reference Concat/Grid layout. The bar is added as extra space at the "
        "top or bottom - only the crop region (if set) affects the photo's extent, "
        "the label bar itself never crops or resizes it further. A bold arrow in "
        "the bar points back at the photo; text and arrow can each be turned off "
        "independently. An optional border (same color as the bar) frames the whole "
        "result. Use the node's Edit Crop button to select a region visually, and "
        "the Preview button for an instant, exact look at the result before queuing."
    )
    SEARCH_ALIASES = ["load image", "label", "caption", "annotate", "reference", "text overlay"]

    @classmethod
    def INPUT_TYPES(cls):
        import os

        import folder_paths

        input_dir = folder_paths.get_input_directory()
        files = [f for f in os.listdir(input_dir) if os.path.isfile(os.path.join(input_dir, f))]
        files = folder_paths.filter_files_content_types(files, ["image"])
        return {
            "required": {
                "image": (sorted(files), {"image_upload": True}),
                "text": ("STRING", {
                    "default": "", "multiline": False,
                    "tooltip": "Caption drawn in the label bar. Auto-shrinks to fit, then truncates with an ellipsis.",
                }),
                "text_position": (["top", "bottom"], {
                    "default": "top",
                    "tooltip": "Which edge of the image the label bar is added to.",
                }),
                "show_label": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Draw the caption text in the bar.",
                }),
                "show_arrow": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Draw a bold arrow in the bar, pointing back at the photo.",
                }),
                "background_color": ("STRING", {
                    "default": "#000000",
                    "tooltip": "Label bar fill color and border color, as a hex code.",
                }),
                "text_color": ("STRING", {
                    "default": "#ffffff",
                    "tooltip": "Caption text and arrow color, as a hex code.",
                }),
                "border_width": ("INT", {
                    "default": 0, "min": 0, "max": 512, "step": 1,
                    "tooltip": "Inset border thickness in pixels, drawn in background_color around the whole result. 0 = no border.",
                }),
                "crop_x": ("INT", {
                    "default": 0, "min": 0, "max": 999999, "step": 1,
                    "tooltip": "Left edge of the crop region, in source-image pixels. Use the Edit Crop button to set this visually.",
                }),
                "crop_y": ("INT", {
                    "default": 0, "min": 0, "max": 999999, "step": 1,
                    "tooltip": "Top edge of the crop region, in source-image pixels. Use the Edit Crop button to set this visually.",
                }),
                "crop_width": ("INT", {
                    "default": 0, "min": 0, "max": 999999, "step": 1,
                    "tooltip": "Crop region width in pixels. 0 = everything to the right of crop_x (no crop, if crop_x/crop_y/crop_height are also 0).",
                }),
                "crop_height": ("INT", {
                    "default": 0, "min": 0, "max": 999999, "step": 1,
                    "tooltip": "Crop region height in pixels. 0 = everything below crop_y (no crop, if crop_x/crop_y/crop_width are also 0).",
                }),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION = "load_image"
    CATEGORY = CATEGORY

    def load_image(self, image, text, text_position, show_label, show_arrow,
                    background_color, text_color, border_width,
                    crop_x, crop_y, crop_width, crop_height):
        import folder_paths

        image_path = folder_paths.get_annotated_filepath(image)
        img = Image.open(image_path)
        img = ImageOps.exif_transpose(img).convert("RGB")
        img = apply_crop(img, crop_x, crop_y, crop_width, crop_height)

        composed = compose_labeled_image(
            img, text, text_position, show_label, show_arrow,
            background_color, text_color, border_width,
        )

        arr = np.array(composed).astype(np.float32) / 255.0
        tensor = arr[None, ...]

        import torch
        return (torch.from_numpy(tensor),)


NODE_CLASS_MAPPINGS = {
    "MoonPack_LabeledLoadImage": LabeledLoadImage,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MoonPack_LabeledLoadImage": "Load Image (Labeled)",
}
