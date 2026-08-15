try:
    from .utils import any_type
except ImportError:  # importable for tests without package context
    from utils import any_type


class ConditionalBypasser:
    """Server-side gate: passes input through when enabled, blocks downstream execution otherwise."""

    DESCRIPTION = (
        "When 'enabled' is true, passes the input through unchanged. "
        "When false, either blocks downstream execution entirely (ExecutionBlocker) "
        "or passes None through, depending on 'disabled_behavior'. "
        "Accepts any data type."
    )
    SEARCH_ALIASES = ["bypass", "gate", "block", "switch", "mute", "if"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "value": (any_type, {"tooltip": "Any input. Type-checked dynamically."}),
                "enabled": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "If false, behavior is controlled by 'disabled_behavior'.",
                }),
                "disabled_behavior": (["block", "pass_none"], {
                    "default": "block",
                    "tooltip": (
                        "When disabled: 'block' stops downstream nodes from running "
                        "(ExecutionBlocker). 'pass_none' lets downstream nodes run but "
                        "receive None instead of the input value."
                    ),
                }),
            },
        }

    RETURN_TYPES = (any_type,)
    RETURN_NAMES = ("output",)
    FUNCTION = "gate"
    CATEGORY = "MoonPack/utils"

    def gate(self, value, enabled, disabled_behavior="block"):
        if enabled:
            return (value,)
        if disabled_behavior == "pass_none":
            return (None,)
        try:
            from comfy_execution.graph import ExecutionBlocker
            return (ExecutionBlocker(None),)
        except ImportError:
            # Older ComfyUI versions without ExecutionBlocker — fall back to None.
            return (None,)


NODE_CLASS_MAPPINGS = {
    "MoonPack_ConditionalBypasser": ConditionalBypasser,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MoonPack_ConditionalBypasser": "Conditional Bypasser",
}
