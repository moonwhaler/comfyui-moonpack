import logging

try:
    from .utils import FlexibleOptionalInputType
except ImportError:  # importable for tests without package context
    from utils import FlexibleOptionalInputType

log = logging.getLogger("MoonPack")

CTL_PREFIX = "ctl_"
ENTRY_PREFIX = "entry_"


def _suffix(key: str) -> str:
    """'ctl_3' -> '3'. The suffix pairs a control strip with its text widget."""
    return key.split("_", 1)[1] if "_" in key else ""


def _as_text(value) -> str:
    """Coerces a widget or link value to a string, unwrapping batched lists."""
    if isinstance(value, (list, tuple)):
        value = value[0] if len(value) > 0 else ""
    return "" if value is None else str(value)


def iter_entries(kwargs: dict) -> list:
    """Returns [(suffix, on, text)] for every text block, in display order.

    Order is the kwargs insertion order, never the numeric suffix: the frontend
    serialises widgets top to bottom, so a block moved up or down keeps its
    original 'ctl_N' name but changes position. Sorting by suffix would
    silently ignore reordering.
    """
    texts = {}
    for key, value in kwargs.items():
        if key.startswith(ENTRY_PREFIX):
            texts[_suffix(key)] = _as_text(value)

    entries = []
    for key, value in kwargs.items():
        if not key.startswith(CTL_PREFIX) or not isinstance(value, dict):
            continue
        suffix = _suffix(key)
        if suffix not in texts:
            log.debug("Text Builder: %s has no matching %s%s; skipped",
                      key, ENTRY_PREFIX, suffix)
            continue
        entries.append((suffix, bool(value.get("on")), texts[suffix]))
    return entries


def join_parts(parts, separator, skip_empty=True, strip_whitespace=True,
                newline_between_inputs=False, newline_wrapped_separator="") -> str:
    """Joins parts with the separator verbatim, after optional strip/skip."""
    sep = "" if separator is None else str(separator)
    if newline_wrapped_separator:
        sep = f"\n{newline_wrapped_separator}\n"
    elif newline_between_inputs:
        sep = "\n"
    kept = []
    for part in parts:
        if strip_whitespace:
            part = part.strip()
        if skip_empty and not part:
            continue
        kept.append(part)
    return sep.join(kept)


class TextBuilder:
    """Joins any number of on-node text blocks, and an optional input, into one string."""

    DESCRIPTION = (
        "Joins any number of multiline text blocks typed on the node with a separator. "
        "Blocks are added, toggled, reordered and removed directly on the node. "
        "A connected 'text' input is always the first part and cannot be reordered."
    )
    SEARCH_ALIASES = ["text", "concat", "join", "prompt", "builder", "stack"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "separator": ("STRING", {
                    "default": ",", "multiline": False,
                    "tooltip": "Inserted verbatim between the parts. ',' gives 'a,b'; use ', ' for a space.",
                }),
                "skip_empty": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Drop parts that are empty after stripping, so no stray separators appear.",
                }),
                "strip_whitespace": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Strip leading/trailing whitespace from each part before joining.",
                }),
                "newline_between_inputs": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "Join parts with a linefeed (\\n) instead of 'separator'.",
                }),
                "newline_wrapped_separator": ("STRING", {
                    "default": "", "multiline": False,
                    "tooltip": "Advanced. If non-empty, joins parts as LF + this text + LF, e.g. "
                                "'(part) LF (text) LF (part)'. Takes precedence over "
                                "'newline_between_inputs' and 'separator'.",
                }),
            },
            # Blocks arrive as undeclared 'ctl_N'/'entry_N' inputs from the frontend widgets.
            "optional": FlexibleOptionalInputType(
                "STRING", data={"text": ("STRING", {"forceInput": True})},
            ),
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "build"
    CATEGORY = "MoonPack/string"

    def build(self, separator=",", skip_empty=True, strip_whitespace=True,
              newline_between_inputs=False, newline_wrapped_separator="",
              text=None, **kwargs):
        parts = []
        if text is not None:
            parts.append(_as_text(text))
        for _suffix_key, on, block in iter_entries(kwargs):
            if on:
                parts.append(block)

        result = join_parts(parts, separator, skip_empty, strip_whitespace,
                             newline_between_inputs, newline_wrapped_separator)
        log.debug("Text Builder: %d parts -> %d chars", len(parts), len(result))
        return (result,)


NODE_CLASS_MAPPINGS = {
    "MoonPack_TextBuilder": TextBuilder,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MoonPack_TextBuilder": "Text Builder",
}
