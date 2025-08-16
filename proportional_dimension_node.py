# --- ProportionalDimension Node ---
class ProportionalDimension:
    """
    Calculates new width and height dimensions while maintaining the original aspect ratio.
    You can choose whether the 'target_size' applies to the shortest or longest side.

    Inputs:
        width (INT): The original width of the image/area.
        height (INT): The original height of the image/area.
        target_size (INT): The desired size for the selected dimension (shortest or longest).
        target_side (STRING): Whether to apply target_size to "shortest" or "longest" side.
                              - "shortest": Sets minimum resolution (default)
                              - "longest": Sets maximum resolution

    Outputs:
        width (INT): The new calculated width.
        height (INT): The new calculated height.
    """
    def __init__(self):
        pass
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "width": ("INT", {"default": 1440, "min": 1, "max": 10000}),
                "height": ("INT", {"default": 1024, "min": 1, "max": 10000}),
                "target_size": ("INT", {"default": 480, "min": 1, "max": 10000}),
                "target_side": (["shortest", "longest"], {"default": "shortest"}),
            }
        }

    RETURN_TYPES = ("INT", "INT", "INT", "INT",)
    RETURN_NAMES = ("width", "height", "shortest_side", "longest_side",)
    FUNCTION = "calculate"
    CATEGORY = "dimensions"

    def calculate(self, width, height, target_size, target_side):
        aspect_ratio = width / height
        
        if target_side == "shortest":
            # Apply target_size to the shorter dimension (minimum resolution)
            if width < height:
                new_width = target_size
                new_height = int(new_width / aspect_ratio)
            else:
                new_height = target_size
                new_width = int(new_height * aspect_ratio)
        else:  # target_side == "longest"
            # Apply target_size to the longer dimension (maximum resolution)
            if width > height:
                new_width = target_size
                new_height = int(new_width / aspect_ratio)
            else:
                new_height = target_size
                new_width = int(new_height * aspect_ratio)

        shortest_side = min(new_width, new_height)
        longest_side = max(new_width, new_height)
            
        return (new_width, new_height, shortest_side, longest_side,)

NODE_CLASS_MAPPINGS = {
    "ProportionalDimension": ProportionalDimension
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ProportionalDimension": "Proportional Dimension"
}
