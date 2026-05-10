class StringSwitch:
    """Routes one of N string inputs to the output via lazy evaluation."""

    DESCRIPTION = (
        "Routes one of up to 8 string inputs to the output based on 'selected'. "
        "Uses lazy evaluation: only the chosen branch's upstream graph is evaluated."
    )
    SEARCH_ALIASES = ["switch", "select", "route", "choose", "branch", "if"]

    SLOT_COUNT = 8

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "selected": ("INT", {
                    "default": 1, "min": 1, "max": cls.SLOT_COUNT, "step": 1,
                    "tooltip": "1-based index of the input to pass through.",
                }),
            },
            "optional": {
                f"input_{i}": ("STRING", {
                    "forceInput": True, "lazy": True,
                    "tooltip": f"String input #{i}",
                })
                for i in range(1, cls.SLOT_COUNT + 1)
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "pick"
    CATEGORY = "MoonPack/string"

    def check_lazy_status(self, selected, **kwargs):
        key = f"input_{int(selected)}"
        if kwargs.get(key) is None:
            return [key]
        return []

    def pick(self, selected, **kwargs):
        key = f"input_{int(selected)}"
        v = kwargs.get(key)
        if v is None:
            return ("",)
        if isinstance(v, (list, tuple)):
            v = v[0] if v else ""
        return (str(v),)


NODE_CLASS_MAPPINGS = {
    "MoonPack_StringSwitch": StringSwitch,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MoonPack_StringSwitch": "String Switch",
}
