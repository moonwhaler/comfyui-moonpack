class DynamicLoraStack:
    @classmethod
    def INPUT_TYPES(s):
        # Define up to 64 optional LoRA inputs
        optional_inputs = {f"lora_{i}": ("LORA",) for i in range(1, 65)}
        return {
            "required": {},
            "optional": optional_inputs
        }

    RETURN_TYPES = ("LORA",)
    FUNCTION = "stack_loras"
    CATEGORY = "moonpack/lora"

    def stack_loras(self, **kwargs):
        loras = []
        # Sort kwargs by key to maintain the order of inputs
        for i in range(1, 65):
            lora_key = f"lora_{i}"
            if lora_key in kwargs and kwargs[lora_key] is not None:
                loras.append(kwargs[lora_key])

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
