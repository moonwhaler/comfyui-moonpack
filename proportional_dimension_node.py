# --- ProportionalDimension Node ---
class ProportionalDimension:
    """
    Calculates new width and height dimensions while maintaining the original aspect ratio.
    The smaller of the original width or height will be scaled to the 'target_size',
    and the other dimension will be adjusted proportionally.

    Inputs:
        width (INT): The original width of the image/area.
        height (INT): The original height of the image/area.
        target_size (INT): The desired size for the smaller dimension of the output.

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
            }
        }

    RETURN_TYPES = ("INT", "INT",)
    RETURN_NAMES = ("width", "height",)
    FUNCTION = "calculate"
    CATEGORY = "dimensions"

    def calculate(self, width, height, target_size):
        aspect_ratio = width / height
        
        if width < height:
            new_width = target_size
            new_height = int(new_width / aspect_ratio)
        else:
            new_height = target_size
            new_width = int(new_height * aspect_ratio)
            
        return (new_width, new_height,)

NODE_CLASS_MAPPINGS = {
    "ProportionalDimension": ProportionalDimension
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ProportionalDimension": "Proportional Dimension"
}
