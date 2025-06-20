from .utils import FlexibleOptionalInputType


class DynamicLoraStack:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {},
            "optional": FlexibleOptionalInputType("WANVIDLORA")
        }

    RETURN_TYPES = ("WANVIDLORA",)
    FUNCTION = "stack_loras"
    CATEGORY = "moonpack/lora"

    def stack_loras(self, **kwargs):
        loras = []
        # Sort kwargs by key to maintain the order of inputs
        for key, value in sorted(kwargs.items()):
            if key.startswith("lora_") and value is not None:
                loras.append(value)

        if not loras:
            return (None,)

        # Flatten the list of loras, as some inputs might be stacks themselves
        stacked_loras = []
        for lora in loras:
            if isinstance(lora, list):
                stacked_loras.extend(lora)
            else:
                stacked_loras.append(lora)

        return (stacked_loras,)

NODE_CLASS_MAPPINGS = {
    "DynamicLoraStack": DynamicLoraStack
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "DynamicLoraStack": "Dynamic LoRA Stack"
}
