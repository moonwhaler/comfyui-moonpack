class PromptLibrary:
    """A managed text box: save, update and recall named prompts from a shared library."""

    DESCRIPTION = (
        "A multiline text box that doubles as a searchable prompt library. Save the "
        "current text under a name (with an optional description/tags), reload any "
        "saved prompt from the dropdown, or update/delete it. The STRING output is "
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
            "optional": {
                # Set by the frontend when a library entry is loaded/saved, so
                # reopening the workflow shows which entry is active. Not read
                # by the backend: the output is always `text`, verbatim.
                "entry_name": ("STRING", {"default": "", "forceInput": False}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "get_text"
    CATEGORY = "MoonPack/string"

    def get_text(self, text="", entry_name=""):
        return (text,)


NODE_CLASS_MAPPINGS = {
    "MoonPack_PromptLibrary": PromptLibrary,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MoonPack_PromptLibrary": "Prompt Library",
}
