import logging

try:
    from .utils import FlexibleOptionalInputType
except ImportError:  # importable for tests without package context
    from utils import FlexibleOptionalInputType

log = logging.getLogger("MoonPack")


def _input_index(key: str) -> int:
    try:
        return int(key.split("_")[-1])
    except (IndexError, ValueError):
        return -1


class DynamicLoraStack:
    DESCRIPTION = (
        "Stacks WANVIDLORA inputs with auto-expanding slots. "
        "Flattens nested lists; an empty stack returns [] (not None)."
    )
    SEARCH_ALIASES = ["lora", "stack", "wan", "wanvideo"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": FlexibleOptionalInputType("WANVIDLORA"),
        }

    RETURN_TYPES = ("WANVIDLORA",)
    RETURN_NAMES = ("lora_stack",)
    FUNCTION = "stack_loras"
    CATEGORY = "MoonPack/lora"

    def stack_loras(self, **kwargs):
        items = []
        for key, value in kwargs.items():
            if not key.startswith("lora_") or value is None:
                continue
            if _input_index(key) < 0:
                continue
            items.append((key, value))
        items.sort(key=lambda kv: _input_index(kv[0]))

        stacked = []
        for _, value in items:
            if isinstance(value, list):
                stacked.extend(value)
            else:
                stacked.append(value)

        log.debug("DynamicLoraStack: %d slots → stack of %d", len(items), len(stacked))
        return (stacked,)


NODE_CLASS_MAPPINGS = {
    "MoonPack_DynamicLoraStack": DynamicLoraStack,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MoonPack_DynamicLoraStack": "Dynamic LoRA Stack",
}
