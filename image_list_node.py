try:
    from .utils import FlexibleOptionalInputType
except ImportError:  # importable for tests without package context
    from utils import FlexibleOptionalInputType

CATEGORY = "MoonPack/image"


def _input_index(key: str) -> int:
    try:
        return int(key.split("_")[-1])
    except (IndexError, ValueError):
        return -1


class ImageList:
    DESCRIPTION = (
        "Collects images from auto-expanding slots into a native ComfyUI list, without "
        "stacking them into one batch tensor. Each image keeps its own native resolution, "
        "so mixed-resolution references stay full quality until a downstream node (e.g. "
        "Reference Concat) resizes them itself."
    )
    SEARCH_ALIASES = ["batch", "list", "images", "collect", "combine", "reference"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": FlexibleOptionalInputType("IMAGE"),
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("images",)
    OUTPUT_IS_LIST = (True,)
    FUNCTION = "collect"
    CATEGORY = CATEGORY

    def collect(self, **kwargs):
        items = []
        for key, value in kwargs.items():
            if not key.startswith("image_") or value is None:
                continue
            idx = _input_index(key)
            if idx < 0:
                continue
            items.append((idx, value))
        items.sort(key=lambda kv: kv[0])
        return ([value for _, value in items],)


NODE_CLASS_MAPPINGS = {
    "MoonPack_ImageList": ImageList,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MoonPack_ImageList": "Image List",
}
