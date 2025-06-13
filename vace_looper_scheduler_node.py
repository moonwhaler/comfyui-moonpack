class VACELooperFrameScheduler:
    """
    A ComfyUI node to calculate total frames and generate a schedule string
    for VACE Looper, based on overlapping frames and in-between frames.
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
                    "max": 10000, # Arbitrary high limit
                    "step": 1,
                    "display": "number"
                }),
                "in_between_frames": ("INT", {
                    "default": 51,
                    "min": 0,
                    "max": 10000, # Arbitrary high limit
                    "step": 1,
                    "display": "number"
                }),
            }
        }

    RETURN_TYPES = ("INT", "STRING", "INT", "INT")
    RETURN_NAMES = ("total_frames", "schedule_string", "overlap_frames", "in_between_frames")
    FUNCTION = "calculate_schedule"
    CATEGORY = "VACELooper"

    def calculate_schedule(self, overlapping_frames, in_between_frames):
        total_frames = (2 * overlapping_frames) + in_between_frames
        
        # Schedule string:
        # 0:(1.0) - Start of prefix overlap (video)
        # overlapping_frames:(0.0) - Start of in-between frames (blank)
        # overlapping_frames + in_between_frames:(1.0) - Start of postfix overlap (video)
        # The trailing comma is often expected by parsers like Fizz's BatchValueSchedule.
        schedule_string = f"0:(1.0),{overlapping_frames}:(0.0),{overlapping_frames + in_between_frames}:(1.0),"

        overlap_frames_out = overlapping_frames
        in_between_frames_out = in_between_frames
        
        return (total_frames, schedule_string, overlap_frames_out, in_between_frames_out)

# A dictionary that ComfyUI uses to know what nodes are available.
# This has to be called NODE_CLASS_MAPPINGS
NODE_CLASS_MAPPINGS = {
    "VACELooperFrameScheduler": VACELooperFrameScheduler
}

# A dictionary that ComfyUI uses to know what nodes are available.
# This has to be called NODE_DISPLAY_NAME_MAPPINGS
NODE_DISPLAY_NAME_MAPPINGS = {
    "VACELooperFrameScheduler": "VACE Looper Frame Scheduler"
}

if __name__ == "__main__":
    # Example Usage (for testing outside ComfyUI)
    scheduler = VACELooperFrameScheduler()
    
    # Test case 1: Default values
    overlap_1 = 15
    in_between_1 = 51
    total1, schedule1, ov_out1, ib_out1 = scheduler.calculate_schedule(overlap_1, in_between_1)
    print(f"Test Case 1 (Overlap: {overlap_1}, In-between: {in_between_1}):")
    print(f"  Total Frames: {total1}")
    print(f"  Schedule String: \"{schedule1}\"")
    print(f"  Overlap Out: {ov_out1}")
    print(f"  In-between Out: {ib_out1}")
    # Expected: Total Frames: 81, Schedule String: "0:(1.0),15:(0.0),66:(1.0),"

    # Test case 2: Different values
    overlap_2 = 10
    in_between_2 = 30
    total2, schedule2, ov_out2, ib_out2 = scheduler.calculate_schedule(overlap_2, in_between_2)
    print(f"\nTest Case 2 (Overlap: {overlap_2}, In-between: {in_between_2}):")
    print(f"  Total Frames: {total2}")
    print(f"  Schedule String: \"{schedule2}\"")
    print(f"  Overlap Out: {ov_out2}")
    print(f"  In-between Out: {ib_out2}")
    # Expected: Total Frames: 50, Schedule String: "0:(1.0),10:(0.0),40:(1.0),"

    # Test case 3: Zero in-between frames
    overlap_3 = 5
    in_between_3 = 0
    total3, schedule3, ov_out3, ib_out3 = scheduler.calculate_schedule(overlap_3, in_between_3)
    print(f"\nTest Case 3 (Overlap: {overlap_3}, In-between: {in_between_3}):")
    print(f"  Total Frames: {total3}")
    print(f"  Schedule String: \"{schedule3}\"")
    print(f"  Overlap Out: {ov_out3}")
    print(f"  In-between Out: {ib_out3}")
    # Expected: Total Frames: 10, Schedule String: "0:(1.0),5:(0.0),5:(1.0),"
