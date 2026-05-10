class FastNodeBypasser:
    """Virtual control node — all toggle/bypass behavior lives in web/moonpack.js."""

    DESCRIPTION = (
        "Adds toggle widgets to bypass connected nodes (or nodes whose title matches a regex). "
        "Right-click for 'Bypass All / Enable All / Toggle All / Refresh'. "
        "Sort order and toggle restrictions configurable via node properties."
    )
    SEARCH_ALIASES = ["bypass", "mute", "toggle", "disable", "enable", "fast groups"]

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}, "optional": {}}

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        return True

    RETURN_TYPES = ()
    FUNCTION = "noop"
    CATEGORY = "MoonPack/utils"
    OUTPUT_NODE = False

    def noop(self, **kwargs):
        # Pure client-side node; no server-side execution required.
        return ()


NODE_CLASS_MAPPINGS = {
    "MoonPack_FastNodeBypasser": FastNodeBypasser,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MoonPack_FastNodeBypasser": "Fast Node Bypasser",
}
