class VACELooperFrameMaskCreator:
    """
    A ComfyUI node to calculate total frames and generate a frame mask string
    for VACE (Create Fade Mask Advanced, kjnodes), based on overlapping frames and in-between frames.
    """
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "overlapping_frames": ("INT", {
                    "default": 15,
                    "min": 0,
                    "max": 10000,
                    "step": 1,
                    "display": "number"
                }),
                "in_between_frames": ("INT", {
                    "default": 51,
                    "min": 0,
                    "max": 10000,
                    "step": 1,
                    "display": "number"
                }),
            },
            "optional": {
                "images": ("IMAGE",),
            }
        }

    RETURN_TYPES = ("INT", "STRING", "INT", "INT", "INT")
    RETURN_NAMES = ("total_frames", "fade_mask", "overlap_frames", "in_between_frames", "source_frames")
    FUNCTION = "calculate_schedule"
    CATEGORY = "VACELooper"

    def calculate_schedule(self, overlapping_frames, in_between_frames, images=None):
        source_frame_count = 0
        actual_overlapping_frames = overlapping_frames

        if images is not None:
            source_frame_count = images.shape[0]
            if source_frame_count > 0:
                max_overlap = source_frame_count // 2
                actual_overlapping_frames = min(overlapping_frames, max_overlap)

        total_frames = (2 * actual_overlapping_frames) + in_between_frames
        
        schedule_string = f"0:(1.0),{actual_overlapping_frames}:(0.0),{actual_overlapping_frames + in_between_frames}:(1.0),"

        return (total_frames, schedule_string, actual_overlapping_frames, in_between_frames, source_frame_count)

NODE_CLASS_MAPPINGS = {
    "VACELooperFrameMaskCreator": VACELooperFrameMaskCreator
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "VACELooperFrameMaskCreator": "VACE Looper Frame Mask Creator"
}

if __name__ == "__main__":
    # Mock torch and numpy for testing outside of ComfyUI
    import numpy as np
    class MockTensor:
        def __init__(self, shape):
            self.shape = shape
        def __repr__(self):
            return f"MockTensor(shape={self.shape})"

    # Example Usage (for testing outside ComfyUI)
    scheduler = VACELooperFrameMaskCreator()
