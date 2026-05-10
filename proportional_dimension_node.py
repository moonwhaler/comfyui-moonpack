import math

CATEGORY = "MoonPack/image"

_ROUNDERS = {"nearest": round, "floor": math.floor, "ceil": math.ceil}


class ProportionalDimension:
    DESCRIPTION = (
        "Resizes width/height proportionally so the chosen side hits target_size, "
        "snapping to a multiple via nearest/floor/ceil rounding."
    )
    SEARCH_ALIASES = ["resize", "aspect", "scale", "dimension"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "width": ("INT", {"default": 1440, "min": 1, "max": 16384,
                                  "tooltip": "Original width in pixels."}),
                "height": ("INT", {"default": 1024, "min": 1, "max": 16384,
                                   "tooltip": "Original height in pixels."}),
                "target_size": ("INT", {"default": 480, "min": 1, "max": 16384,
                                        "tooltip": "Desired size for the selected side."}),
                "target_side": (["shortest", "longest"], {
                    "default": "shortest",
                    "tooltip": "Which side target_size applies to. 'shortest' upscales the smaller side; 'longest' caps the larger side.",
                }),
                "divisible_by": ("INT", {"default": 1, "min": 1, "max": 1024,
                    "tooltip": "Snap output dimensions to a multiple of this value (1 = no snapping)."}),
                "rounding": (["nearest", "floor", "ceil"], {
                    "default": "nearest",
                    "tooltip": "How to snap to the divisor. 'floor' guarantees output ≤ ideal; 'ceil' guarantees ≥.",
                }),
            },
            "optional": {
                "from_image": ("IMAGE", {
                    "tooltip": "Optional: read width/height from an IMAGE tensor instead of the widgets.",
                }),
            },
        }

    RETURN_TYPES = ("INT", "INT", "INT", "INT", "FLOAT")
    RETURN_NAMES = ("width", "height", "shortest_side", "longest_side", "scale")
    FUNCTION = "calculate"
    CATEGORY = CATEGORY

    def calculate(self, width, height, target_size, target_side, divisible_by,
                  rounding="nearest", from_image=None):
        if from_image is not None:
            # IMAGE shape is [B, H, W, C].
            _, h, w, _ = from_image.shape
            width, height = int(w), int(h)

        aspect = width / height
        if target_side == "shortest":
            if width < height:
                new_w = float(target_size)
                new_h = new_w / aspect
            else:
                new_h = float(target_size)
                new_w = new_h * aspect
        else:  # longest
            if width > height:
                new_w = float(target_size)
                new_h = new_w / aspect
            else:
                new_h = float(target_size)
                new_w = new_h * aspect

        if divisible_by > 1:
            snap = _ROUNDERS[rounding]
            new_w = max(divisible_by, int(snap(new_w / divisible_by)) * divisible_by)
            new_h = max(divisible_by, int(snap(new_h / divisible_by)) * divisible_by)
        else:
            new_w = max(1, int(round(new_w)))
            new_h = max(1, int(round(new_h)))

        scale = ((new_w / width) + (new_h / height)) / 2.0
        return (new_w, new_h, min(new_w, new_h), max(new_w, new_h), float(scale))


class DimensionFromImage:
    DESCRIPTION = "Reads width, height, and batch size from an IMAGE tensor."
    SEARCH_ALIASES = ["dimensions", "size", "image info", "shape"]

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image": ("IMAGE", {"tooltip": "Image tensor (shape [B, H, W, C])."})}}

    RETURN_TYPES = ("INT", "INT", "INT")
    RETURN_NAMES = ("width", "height", "batch_size")
    FUNCTION = "get_dims"
    CATEGORY = CATEGORY

    def get_dims(self, image):
        b, h, w = image.shape[0], image.shape[1], image.shape[2]
        return (int(w), int(h), int(b))


class SmartResolution:
    DESCRIPTION = (
        "Picks a model-friendly resolution near a megapixel budget while preserving aspect ratio. "
        "Snaps to each preset's required divisor."
    )
    SEARCH_ALIASES = ["preset", "sdxl", "flux", "wan", "megapixel", "resolution"]

    # name → (target_pixels, divisor, min_dim, max_dim)
    PRESETS = {
        "SD 1.5 (0.26MP)":     (512 * 512,    8,   256, 1024),
        "SDXL (1.0MP)":         (1024 * 1024,  64,  512, 2048),
        "Flux (1.0MP)":         (1024 * 1024,  16,  512, 2048),
        "Flux (1.4MP)":         (1216 * 1216,  16,  512, 2048),
        "Wan 480p (832x480)":   (832 * 480,    16,  256, 1280),
        "Wan 720p (1280x720)":  (1280 * 720,   16,  256, 1920),
    }

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "width": ("INT", {"default": 1920, "min": 1, "max": 16384,
                                  "tooltip": "Source width (aspect ratio is preserved)."}),
                "height": ("INT", {"default": 1080, "min": 1, "max": 16384,
                                   "tooltip": "Source height."}),
                "preset": (list(cls.PRESETS.keys()), {"tooltip": "Target model preset."}),
                "rounding": (["nearest", "floor", "ceil"], {
                    "default": "nearest",
                    "tooltip": "How to snap to the preset's divisor.",
                }),
            },
        }

    RETURN_TYPES = ("INT", "INT", "FLOAT")
    RETURN_NAMES = ("width", "height", "scale")
    FUNCTION = "calc"
    CATEGORY = CATEGORY

    def calc(self, width, height, preset, rounding):
        target_pixels, divisor, min_dim, max_dim = self.PRESETS[preset]
        aspect = width / height
        ideal_w = math.sqrt(target_pixels * aspect)
        ideal_h = math.sqrt(target_pixels / aspect)
        snap = _ROUNDERS[rounding]
        new_w = max(min_dim, min(max_dim, int(snap(ideal_w / divisor)) * divisor))
        new_h = max(min_dim, min(max_dim, int(snap(ideal_h / divisor)) * divisor))
        scale = ((new_w / width) + (new_h / height)) / 2.0
        return (new_w, new_h, float(scale))


NODE_CLASS_MAPPINGS = {
    "MoonPack_ProportionalDimension": ProportionalDimension,
    "MoonPack_DimensionFromImage": DimensionFromImage,
    "MoonPack_SmartResolution": SmartResolution,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MoonPack_ProportionalDimension": "Proportional Dimension",
    "MoonPack_DimensionFromImage": "Dimension From Image",
    "MoonPack_SmartResolution": "Smart Resolution",
}
