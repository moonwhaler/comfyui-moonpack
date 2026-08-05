import logging

try:
    from .utils import FlexibleOptionalInputType, any_type
except ImportError:  # importable for tests without package context
    from utils import FlexibleOptionalInputType, any_type

log = logging.getLogger("MoonPack")

LORA_PREFIX = "lora_"
NONE_SENTINEL = "None"


def _norm(path: str) -> str:
    """Normalises a lora path for comparison (workflows saved on Windows use '\\')."""
    return path.replace("\\", "/")


def _as_float(value, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def iter_lora_rows(kwargs: dict) -> list:
    """Returns [(key, row)] for every lora row widget, in display order.

    Order is the kwargs insertion order, never the numeric suffix: the frontend
    serialises widgets top to bottom, so a row moved up or down keeps its
    original 'lora_N' name but changes position. Sorting by suffix would
    silently ignore reordering.
    """
    rows = []
    for key, value in kwargs.items():
        if not key.startswith(LORA_PREFIX) or not isinstance(value, dict):
            continue
        rows.append((key, value))
    return rows


def join_trigger_texts(rows, separator: str) -> str:
    """Joins the trigger texts of enabled rows with the separator, verbatim.

    Each text is stripped; empty texts and disabled rows contribute nothing.
    """
    texts = []
    for row in rows:
        if not row.get("on"):
            continue
        text = row.get("text")
        if not isinstance(text, str):
            continue
        text = text.strip()
        if text:
            texts.append(text)
    return str(separator if separator is not None else "").join(texts)


def resolve_lora_filename(name, available):
    """Maps a stored lora name onto an actual file, or None if it is gone.

    Falls back from exact match to case-insensitive, then to a basename match
    so a lora moved between subfolders still resolves.
    """
    if not isinstance(name, str) or not name or name == NONE_SENTINEL:
        return None

    wanted = _norm(name)
    for candidate in available:
        if _norm(candidate) == wanted:
            return candidate

    lowered = wanted.lower()
    for candidate in available:
        if _norm(candidate).lower() == lowered:
            return candidate

    base = lowered.rsplit("/", 1)[-1]
    for candidate in available:
        if _norm(candidate).lower().rsplit("/", 1)[-1] == base:
            return candidate

    return None


class MoonLoraLoader:
    """Applies any number of LoRAs and emits the trigger words of the enabled ones."""

    DESCRIPTION = (
        "Applies a list of LoRAs to MODEL/CLIP and concatenates the trigger text of "
        "every enabled row into a single string. Rows are added, toggled, reordered "
        "and removed directly on the node. Fully local — no Civitai lookup."
    )
    SEARCH_ALIASES = ["lora", "power", "trigger", "prompt", "stack", "moonlora"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "separator": ("STRING", {
                    "default": ". ", "multiline": False,
                    "tooltip": "Inserted verbatim between the trigger texts of enabled LoRAs.",
                }),
            },
            # Rows arrive as undeclared 'lora_N' inputs from the frontend widgets.
            "optional": FlexibleOptionalInputType(any_type, data={
                "clip": ("CLIP",),
                "trigger_text": ("STRING", {"forceInput": True}),
            }),
        }

    RETURN_TYPES = ("MODEL", "CLIP", "STRING")
    RETURN_NAMES = ("MODEL", "CLIP", "trigger_text")
    FUNCTION = "load_loras"
    CATEGORY = "MoonPack/lora"

    def load_loras(self, model, separator=". ", clip=None, trigger_text=None, **kwargs):
        rows = iter_lora_rows(kwargs)
        applied = []
        if isinstance(trigger_text, str):
            applied.append({"on": True, "text": trigger_text})
        if not rows:
            return (model, clip, join_trigger_texts(applied, separator))

        # Imported here so the module stays importable outside ComfyUI.
        import folder_paths
        from nodes import LoraLoader

        available = folder_paths.get_filename_list("loras")
        loader = LoraLoader()
        warned_missing_clip = False

        for key, row in rows:
            if not row.get("on"):
                continue

            resolved = resolve_lora_filename(row.get("lora"), available)
            if resolved is None:
                # Its trigger text is dropped too: emitting trigger words for a
                # lora that was never applied would be misleading.
                log.warning(
                    "MoonLoRA Loader: %s -> '%s' not found in the loras folder; row skipped.",
                    key, row.get("lora"),
                )
                continue

            strength_model = _as_float(row.get("strength"), 1.0)
            strength_two = row.get("strengthTwo")
            if clip is None:
                if strength_two is not None and _as_float(strength_two, 0.0) != 0.0 \
                        and not warned_missing_clip:
                    log.warning(
                        "MoonLoRA Loader: clip strengths are set but no CLIP is connected; "
                        "applying model strengths only."
                    )
                    warned_missing_clip = True
                strength_clip = 0
            elif strength_two is None:
                strength_clip = strength_model
            else:
                strength_clip = _as_float(strength_two, strength_model)

            # Collected before the zero-strength check: a zero-strength row is a
            # no-op for the model, but the user still asked for its trigger words.
            applied.append(row)

            if strength_model == 0 and strength_clip == 0:
                continue

            model, clip = loader.load_lora(
                model, clip, resolved, strength_model, strength_clip
            )

        return (model, clip, join_trigger_texts(applied, separator))


NODE_CLASS_MAPPINGS = {
    "MoonPack_MoonLoraLoader": MoonLoraLoader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MoonPack_MoonLoraLoader": "MoonLoRA Loader",
}
