import logging
import re

try:
    from .utils import FlexibleOptionalInputType
except ImportError:  # importable for tests without package context
    from utils import FlexibleOptionalInputType

log = logging.getLogger("MoonPack")


def _input_index(key: str) -> int:
    """Extracts the trailing integer from 'input_N'; returns -1 if unparseable."""
    try:
        return int(key.split("_")[-1])
    except (IndexError, ValueError):
        return -1


class DynamicStringConcat:
    """Auto-expanding string concatenator with optional template-based interpolation."""

    DESCRIPTION = (
        "Concatenates connected string inputs in slot order. If 'template' is non-empty, "
        "slots are interpolated into placeholders {1}, {2}, … instead of joined."
    )
    SEARCH_ALIASES = ["join", "concat", "merge", "string", "template"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "separator": ("STRING", {
                    "default": " ", "multiline": False,
                    "tooltip": "Separator placed between joined strings (ignored when 'template' is non-empty).",
                }),
                "ignore_empty": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Skip inputs that are empty after stripping (join mode only).",
                }),
                "strip_whitespace": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Strip leading/trailing whitespace from each input before joining.",
                }),
                "prefix": ("STRING", {
                    "default": "", "multiline": False,
                    "tooltip": "Prepended to the final result.",
                }),
                "suffix": ("STRING", {
                    "default": "", "multiline": False,
                    "tooltip": "Appended to the final result.",
                }),
                "template": ("STRING", {
                    "default": "", "multiline": True,
                    "placeholder": "Optional. Use {1}, {2}, … for slot N. e.g. '{1}, in the style of {2}'",
                    "tooltip": "If non-empty, slots are interpolated into {N} placeholders instead of joined.",
                }),
            },
            "optional": FlexibleOptionalInputType("STRING"),
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "concatenate"
    CATEGORY = "MoonPack/string"
    OUTPUT_NODE = False

    def concatenate(self, separator=" ", ignore_empty=True, strip_whitespace=True,
                    prefix="", suffix="", template="", **kwargs):
        slots = {}
        for key, value in kwargs.items():
            if not key.startswith("input_"):
                continue
            idx = _input_index(key)
            if idx < 0 or value is None:
                continue
            if isinstance(value, (list, tuple)):
                value = value[0] if len(value) > 0 else ""
            s = str(value)
            if strip_whitespace:
                s = s.strip()
            slots[idx] = s

        if template.strip():
            def _resolve(match):
                return slots.get(int(match.group(1)), "")
            body = re.sub(r"\{(\d+)\}", _resolve, template)
        else:
            ordered = [slots[k] for k in sorted(slots.keys())]
            if ignore_empty:
                ordered = [s for s in ordered if s]
            body = separator.join(ordered)

        result = f"{prefix}{body}{suffix}"
        log.debug("DynamicStringConcat: %d slots → %d chars", len(slots), len(result))
        return (result,)


NODE_CLASS_MAPPINGS = {
    "MoonPack_DynamicStringConcat": DynamicStringConcat,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MoonPack_DynamicStringConcat": "Dynamic String Concat",
}
