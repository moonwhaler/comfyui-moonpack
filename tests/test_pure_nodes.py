# --- ProportionalDimension --------------------------------------------------

def test_proportional_dimension_shortest():
    from proportional_dimension_node import ProportionalDimension
    n = ProportionalDimension()
    w, h, s, l, _ = n.calculate(1920, 1080, 512, "shortest", 1)
    assert h == 512
    assert 909 <= w <= 911
    assert s == h
    assert l == w


def test_proportional_dimension_longest():
    from proportional_dimension_node import ProportionalDimension
    n = ProportionalDimension()
    w, h, _, _, _ = n.calculate(1920, 1080, 1024, "longest", 1)
    assert w == 1024
    assert h == 576


def test_proportional_dimension_divisible_floor():
    from proportional_dimension_node import ProportionalDimension
    n = ProportionalDimension()
    w, h, *_ = n.calculate(1920, 1080, 512, "shortest", 64, "floor")
    assert w % 64 == 0
    assert h % 64 == 0
    # floor must not exceed ideal
    assert w <= round(512 * (1920 / 1080)) + 1
    assert h <= 512


def test_proportional_dimension_scale_output():
    from proportional_dimension_node import ProportionalDimension
    n = ProportionalDimension()
    *_, scale = n.calculate(1920, 1080, 1024, "longest", 1)
    assert 0.5 < scale < 0.6


# --- SmartResolution --------------------------------------------------------

def test_smart_resolution_sdxl_aspect_preserved():
    from proportional_dimension_node import SmartResolution
    n = SmartResolution()
    w, h, _ = n.calc(1920, 1080, "SDXL (1.0MP)", "nearest")
    assert w % 64 == 0 and h % 64 == 0
    assert abs(w * h - 1024 * 1024) / (1024 * 1024) < 0.15
    src_ratio = 1920 / 1080
    out_ratio = w / h
    assert abs(out_ratio - src_ratio) / src_ratio < 0.10


def test_smart_resolution_wan480():
    from proportional_dimension_node import SmartResolution
    n = SmartResolution()
    w, h, _ = n.calc(1920, 1080, "Wan 480p (832x480)", "nearest")
    assert w % 16 == 0 and h % 16 == 0


# --- SimpleStringReplace ----------------------------------------------------

def test_simple_string_replace_basic():
    from string_replace_nodes import SimpleStringReplace
    n = SimpleStringReplace()
    out, ignored = n.replace("hello world", "hello => hi\nworld => earth")
    assert out == "hi earth"
    assert ignored == ""


def test_simple_string_replace_reports_malformed():
    from string_replace_nodes import SimpleStringReplace
    n = SimpleStringReplace()
    out, ignored = n.replace("abc", "no arrow here\na => b")
    assert out == "bbc"
    assert "no arrow here" in ignored


def test_simple_string_replace_whole_word():
    from string_replace_nodes import SimpleStringReplace
    n = SimpleStringReplace()
    out, _ = n.replace("the theatre", "the => a", whole_word_match=True)
    assert out == "a theatre"


# --- RegexStringReplace -----------------------------------------------------

def test_regex_replace_count():
    from string_replace_nodes import RegexStringReplace
    n = RegexStringReplace()
    out, count = n.replace("aaa bbb ccc", r"\b\w+\b", "X")
    assert count == 3
    assert out == "X X X"


def test_regex_replace_test_mode_highlights():
    from string_replace_nodes import RegexStringReplace
    n = RegexStringReplace()
    out, count = n.replace("xx YY zz", r"YY", "ZZ", test_mode=True)
    assert ">>>YY<<<" in out
    assert count == 1


def test_regex_replace_dotall():
    from string_replace_nodes import RegexStringReplace
    n = RegexStringReplace()
    out, count = n.replace("a\nb", r"a.b", "X", dotall=True)
    assert count == 1
    assert out == "X"


def test_regex_replace_invalid_pattern_returns_error():
    from string_replace_nodes import RegexStringReplace
    n = RegexStringReplace()
    out, count = n.replace("foo", r"(unclosed", "x")
    assert "regex error" in out
    assert count == 0


# --- RegexExtract -----------------------------------------------------------

def test_regex_extract_first():
    from string_replace_nodes import RegexExtract
    n = RegexExtract()
    matches, count = n.extract("Item 42 Cost 99", r"\d+")
    assert matches == ["42"]
    assert count == 1


def test_regex_extract_all():
    from string_replace_nodes import RegexExtract
    n = RegexExtract()
    matches, count = n.extract("a1 b2 c3", r"\d+", all_matches=True)
    assert matches == ["1", "2", "3"]
    assert count == 3


def test_regex_extract_capture_group():
    from string_replace_nodes import RegexExtract
    n = RegexExtract()
    matches, count = n.extract("name=alice age=30", r"name=(\w+)")
    assert matches == ["alice"]
    assert count == 1


def test_regex_extract_no_match_default():
    from string_replace_nodes import RegexExtract
    n = RegexExtract()
    matches, count = n.extract("hello", r"\d+", default="<none>")
    assert matches == ["<none>"]
    assert count == 0


# --- VACE / FrameMaskGenerator ----------------------------------------------

def test_vace_looper_no_images():
    from vace_looper_fade_mask_node import VACELooperFrameMaskCreator
    n = VACELooperFrameMaskCreator()
    total, sched, ov, btw, src, clamped = n.calculate_schedule(15, 51)
    assert total == 81
    assert ov == 15
    assert btw == 51
    assert src == 0
    assert clamped is False
    assert sched == "0:(1.0),15:(0.0),66:(1.0),"


def test_vace_looper_clamps_to_source_length():
    from vace_looper_fade_mask_node import VACELooperFrameMaskCreator

    class FakeImg:
        shape = (10, 64, 64, 3)

    n = VACELooperFrameMaskCreator()
    total, sched, ov, btw, src, clamped = n.calculate_schedule(20, 30, FakeImg())
    assert ov == 5
    assert src == 10
    assert clamped is True
    assert total == 2 * 5 + 30


def test_frame_mask_fade_in():
    from vace_looper_fade_mask_node import FrameMaskGenerator
    n = FrameMaskGenerator()
    sched, total = n.generate("fade_in", 60, 10)
    assert total == 60
    assert sched.startswith("0:(0.0),10:(1.0)")


def test_frame_mask_ping_pong():
    from vace_looper_fade_mask_node import FrameMaskGenerator
    n = FrameMaskGenerator()
    sched, total = n.generate("ping_pong", 80, 10)
    assert total == 80
    assert "40:(0.0)" in sched
    assert sched.endswith("80:(1.0),")


def test_frame_mask_custom_appends_trailing_comma():
    from vace_looper_fade_mask_node import FrameMaskGenerator
    n = FrameMaskGenerator()
    sched, _ = n.generate("custom", 50, 10, "0:(1.0),25:(0.0)")
    assert sched.endswith(",")


# --- DynamicStringConcat ----------------------------------------------------

def test_dynamic_concat_join_basic():
    from dynamic_string_concat_node import DynamicStringConcat
    n = DynamicStringConcat()
    (out,) = n.concatenate(separator=", ", input_1="a", input_2="b", input_3="c")
    assert out == "a, b, c"


def test_dynamic_concat_skips_empty():
    from dynamic_string_concat_node import DynamicStringConcat
    n = DynamicStringConcat()
    (out,) = n.concatenate(
        separator=" ", ignore_empty=True,
        input_1="a", input_2="", input_3="c",
    )
    assert out == "a c"


def test_dynamic_concat_template():
    from dynamic_string_concat_node import DynamicStringConcat
    n = DynamicStringConcat()
    (out,) = n.concatenate(
        template="{2}-{1}",
        input_1="a", input_2="b",
    )
    assert out == "b-a"


def test_dynamic_concat_template_missing_slot_blank():
    from dynamic_string_concat_node import DynamicStringConcat
    n = DynamicStringConcat()
    (out,) = n.concatenate(template="x={5}", input_1="a")
    assert out == "x="


def test_dynamic_concat_prefix_suffix():
    from dynamic_string_concat_node import DynamicStringConcat
    n = DynamicStringConcat()
    (out,) = n.concatenate(separator=",", prefix="[", suffix="]", input_1="a", input_2="b")
    assert out == "[a,b]"


def test_dynamic_concat_handles_bad_keys():
    from dynamic_string_concat_node import DynamicStringConcat
    n = DynamicStringConcat()
    # input_x has a non-numeric suffix; should be ignored, not raise.
    (out,) = n.concatenate(separator=" ", input_1="a", input_x="ignored", input_2="b")
    assert out == "a b"


# --- DynamicLoraStack -------------------------------------------------------

def test_dynamic_lora_stack_empty_returns_empty_list():
    from dynamic_lora_stack_node import DynamicLoraStack
    n = DynamicLoraStack()
    (stack,) = n.stack_loras()
    assert stack == []


def test_dynamic_lora_stack_flattens_nested():
    from dynamic_lora_stack_node import DynamicLoraStack
    n = DynamicLoraStack()
    (stack,) = n.stack_loras(lora_1={"a": 1}, lora_2=[{"b": 2}, {"c": 3}])
    assert stack == [{"a": 1}, {"b": 2}, {"c": 3}]


def test_dynamic_lora_stack_handles_bad_keys():
    from dynamic_lora_stack_node import DynamicLoraStack
    n = DynamicLoraStack()
    (stack,) = n.stack_loras(lora_1={"a": 1}, lora_main_x={"bad": True}, lora_2={"b": 2})
    assert stack == [{"a": 1}, {"b": 2}]


# --- StringSwitch -----------------------------------------------------------

def test_string_switch_pick():
    from string_switch_node import StringSwitch
    n = StringSwitch()
    (out,) = n.pick(2, input_1="a", input_2="b", input_3="c")
    assert out == "b"


def test_string_switch_lazy_check():
    from string_switch_node import StringSwitch
    n = StringSwitch()
    needed = n.check_lazy_status(3, input_3=None, input_1="a")
    assert needed == ["input_3"]


def test_string_switch_lazy_check_satisfied():
    from string_switch_node import StringSwitch
    n = StringSwitch()
    needed = n.check_lazy_status(1, input_1="ready")
    assert needed == []


def test_string_switch_missing_input_returns_empty():
    from string_switch_node import StringSwitch
    n = StringSwitch()
    (out,) = n.pick(5)
    assert out == ""


# --- ConditionalBypasser ----------------------------------------------------

def test_conditional_bypasser_passes_when_enabled():
    from conditional_bypasser_node import ConditionalBypasser
    n = ConditionalBypasser()
    (out,) = n.gate("payload", True)
    assert out == "payload"


def test_conditional_bypasser_blocks_when_disabled():
    from conditional_bypasser_node import ConditionalBypasser
    n = ConditionalBypasser()
    (out,) = n.gate("payload", False)
    # Either ExecutionBlocker (real ComfyUI) or None (fallback) — both indicate "no pass-through".
    assert out is None or type(out).__name__ == "ExecutionBlocker"


# --- Module-level smoke tests -----------------------------------------------

def test_all_modules_export_mappings():
    """Every node module declares NODE_CLASS_MAPPINGS and NODE_DISPLAY_NAME_MAPPINGS."""
    modules = [
        "proportional_dimension_node",
        "string_replace_nodes",
        "vace_looper_fade_mask_node",
        "dynamic_string_concat_node",
        "dynamic_lora_stack_node",
        "fast_node_bypasser",
        "string_switch_node",
        "conditional_bypasser_node",
    ]
    for name in modules:
        m = __import__(name)
        assert hasattr(m, "NODE_CLASS_MAPPINGS"), f"{name} missing NODE_CLASS_MAPPINGS"
        assert hasattr(m, "NODE_DISPLAY_NAME_MAPPINGS"), f"{name} missing NODE_DISPLAY_NAME_MAPPINGS"
        for key in m.NODE_CLASS_MAPPINGS:
            assert key.startswith("MoonPack_"), f"{name}: key '{key}' missing MoonPack_ prefix"
            assert key in m.NODE_DISPLAY_NAME_MAPPINGS, f"{name}: '{key}' missing display name"


def test_all_node_classes_have_required_attributes():
    """Each node class declares the four ComfyUI essentials."""
    modules = [
        "proportional_dimension_node",
        "string_replace_nodes",
        "vace_looper_fade_mask_node",
        "dynamic_string_concat_node",
        "dynamic_lora_stack_node",
        "fast_node_bypasser",
        "string_switch_node",
        "conditional_bypasser_node",
    ]
    for name in modules:
        m = __import__(name)
        for key, cls in m.NODE_CLASS_MAPPINGS.items():
            assert hasattr(cls, "INPUT_TYPES"), f"{key} missing INPUT_TYPES"
            assert hasattr(cls, "RETURN_TYPES"), f"{key} missing RETURN_TYPES"
            assert hasattr(cls, "FUNCTION"), f"{key} missing FUNCTION"
            assert hasattr(cls, "CATEGORY"), f"{key} missing CATEGORY"
            assert cls.CATEGORY.startswith("MoonPack/"), \
                f"{key} CATEGORY '{cls.CATEGORY}' must be MoonPack/<group>"
            # INPUT_TYPES must be callable and return a dict with 'required'.
            it = cls.INPUT_TYPES()
            assert isinstance(it, dict)
            assert "required" in it
            # FUNCTION must name an actual method.
            assert callable(getattr(cls, cls.FUNCTION, None)), \
                f"{key} FUNCTION='{cls.FUNCTION}' is not callable on the class"
