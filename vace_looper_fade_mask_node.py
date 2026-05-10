CATEGORY = "MoonPack/video"


class VACELooperFrameMaskCreator:
    DESCRIPTION = (
        "Calculates total frames and a kjnodes 'Create Fade Mask Advanced' schedule "
        "for VACE looping. Optionally clamps overlap to source-image length."
    )
    SEARCH_ALIASES = ["vace", "loop", "fade", "schedule", "mask", "kjnodes"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "overlapping_frames": ("INT", {
                    "default": 15, "min": 1, "max": 10000, "step": 1,
                    "tooltip": "Frames at start and end with weight 1.0 (source-driven).",
                }),
                "in_between_frames": ("INT", {
                    "default": 51, "min": 0, "max": 10000, "step": 1,
                    "tooltip": "Frames in the middle with weight 0.0 (fully generated).",
                }),
            },
            "optional": {
                "images": ("IMAGE", {
                    "tooltip": "Optional source images. If provided, overlap is clamped to half their count.",
                }),
            },
        }

    RETURN_TYPES = ("INT", "STRING", "INT", "INT", "INT", "BOOLEAN")
    RETURN_NAMES = ("total_frames", "fade_mask", "overlap_frames", "between_frames",
                    "source_frames", "was_clamped")
    FUNCTION = "calculate_schedule"
    CATEGORY = CATEGORY

    def calculate_schedule(self, overlapping_frames, in_between_frames, images=None):
        source_frame_count = 0
        actual_overlap = overlapping_frames
        was_clamped = False

        if images is not None:
            source_frame_count = int(images.shape[0])
            if source_frame_count > 0:
                max_overlap = source_frame_count // 2
                if overlapping_frames > max_overlap:
                    actual_overlap = max_overlap
                    was_clamped = True

        total_frames = (2 * actual_overlap) + in_between_frames
        # kjnodes 'Create Fade Mask Advanced' format. The trailing comma is part of its parser contract.
        schedule = (
            f"0:(1.0),{actual_overlap}:(0.0),"
            f"{actual_overlap + in_between_frames}:(1.0),"
        )
        return (total_frames, schedule, actual_overlap, in_between_frames,
                source_frame_count, was_clamped)


class FrameMaskGenerator:
    DESCRIPTION = (
        "Generates kjnodes-style fade mask schedules for several common patterns: "
        "linear loop, ping-pong, ease-in-out, fade-in, fade-out, or pass-through custom keyframes."
    )
    SEARCH_ALIASES = ["fade", "mask", "schedule", "keyframe", "loop", "ping pong"]

    MODES = ["linear_loop", "ping_pong", "ease_in_out", "fade_in", "fade_out", "custom"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (cls.MODES, {
                    "default": "linear_loop",
                    "tooltip": (
                        "linear_loop: 1→0 then 0→1 with held middle. "
                        "ping_pong: 1→0→1. ease_in_out: 0→1→0 with mid-fade stops. "
                        "fade_in: 0→1 then hold. fade_out: hold then 1→0. "
                        "custom: pass custom_keyframes through."
                    ),
                }),
                "total_frames": ("INT", {
                    "default": 81, "min": 1, "max": 100000, "step": 1,
                    "tooltip": "Total length in frames.",
                }),
                "fade_frames": ("INT", {
                    "default": 15, "min": 0, "max": 10000, "step": 1,
                    "tooltip": "Length of each fade ramp (auto-clamped to total_frames/2).",
                }),
            },
            "optional": {
                "custom_keyframes": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "0:(1.0),15:(0.0),...",
                    "tooltip": "Used only when mode='custom'. A trailing comma is added if missing.",
                }),
            },
        }

    RETURN_TYPES = ("STRING", "INT")
    RETURN_NAMES = ("schedule", "total_frames")
    FUNCTION = "generate"
    CATEGORY = CATEGORY

    def generate(self, mode, total_frames, fade_frames, custom_keyframes=""):
        f = max(0, min(fade_frames, total_frames // 2))
        if mode == "custom":
            sched = custom_keyframes.strip()
            if sched and not sched.endswith(","):
                sched += ","
            return (sched, total_frames)
        if mode == "linear_loop":
            sched = f"0:(1.0),{f}:(0.0),{total_frames - f}:(0.0),{total_frames}:(1.0),"
        elif mode == "ping_pong":
            mid = total_frames // 2
            sched = f"0:(1.0),{mid}:(0.0),{total_frames}:(1.0),"
        elif mode == "ease_in_out":
            mid = total_frames // 2
            sched = f"0:(0.0),{f}:(0.5),{mid}:(1.0),{total_frames - f}:(0.5),{total_frames}:(0.0),"
        elif mode == "fade_in":
            sched = f"0:(0.0),{f}:(1.0),{total_frames}:(1.0),"
        elif mode == "fade_out":
            sched = f"0:(1.0),{total_frames - f}:(1.0),{total_frames}:(0.0),"
        else:
            sched = "0:(1.0),"
        return (sched, total_frames)


NODE_CLASS_MAPPINGS = {
    "MoonPack_VACELooperFrameMaskCreator": VACELooperFrameMaskCreator,
    "MoonPack_FrameMaskGenerator": FrameMaskGenerator,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MoonPack_VACELooperFrameMaskCreator": "VACE Looper Frame Mask",
    "MoonPack_FrameMaskGenerator": "Frame Mask Generator",
}
