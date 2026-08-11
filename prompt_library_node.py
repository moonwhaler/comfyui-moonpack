class PromptLibrary:
    """A managed text box: pick a saved prompt from the dropdown, or add/delete one."""

    DESCRIPTION = (
        "A multiline text box that doubles as a prompt library. Pick a saved "
        "prompt from the dropdown to load it, edit it in place (auto-saved), or use "
        "the +/- buttons to add or remove entries. Entries are stored on the node "
        "itself, so they travel with the workflow file. The STRING output is "
        "always whatever is currently in the text box."
    )
    SEARCH_ALIASES = ["prompt", "library", "preset", "text", "multiline"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {
                    "default": "", "multiline": True,
                    "tooltip": "The prompt text. This is exactly what gets output.",
                }),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "get_text"
    CATEGORY = "MoonPack/string"

    def get_text(self, text=""):
        return (text,)


NODE_CLASS_MAPPINGS = {
    "MoonPack_PromptLibrary": PromptLibrary,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MoonPack_PromptLibrary": "Prompt Library",
}
