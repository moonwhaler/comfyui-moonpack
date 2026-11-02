import pytest

import _regional_lora_ops as ops


# --- tags -------------------------------------------------------------------

def test_parse_tags_multiple_decimals_and_missing_weight():
    clean, tags = ops.parse_tags("woman <lora:anna_moss:0.9> in red <lora:film_grain> coat <lora:x:-.5>")
    assert clean == "woman in red coat"
    assert tags == [("anna_moss", 0.9, None), ("film_grain", 1.0, None), ("x", -0.5, None)]


def test_parse_tags_subfolder_and_flag():
    _, tags = ops.parse_tags("<lora:chars/anna.safetensors:0.7:outside>")
    assert tags == [("chars/anna.safetensors", 0.7, "outside")]


def test_parse_tags_bad_strength():
    with pytest.raises(ValueError, match="bad strength"):
        ops.parse_tags("<lora:a:strong>")


def test_parse_box_desc_strips_ids_keeps_newlines():
    clean, box_id, tags = ops.parse_box_desc("@Anna woman <lora:a:1>\nmail me@example.com @extra")
    assert box_id == "anna"
    assert clean == "woman\nmail me@example.com"
    assert tags == [("a", 1.0, None)]


def test_parse_elements_copies_and_indexes():
    elements = [
        {"type": "obj", "bbox": [0, 0, 1000, 1000], "desc": "forest"},
        {"type": "obj", "bbox": [100, 100, 900, 500], "desc": "@anna woman <lora:anna:0.9> <lora:grain:0.4>"},
    ]
    cleaned, ids, tags = ops.parse_elements(elements)
    assert elements[1]["desc"].startswith("@anna")  # input untouched
    assert cleaned[1]["desc"] == "woman"
    assert cleaned[1]["bbox"] == [100, 100, 900, 500]
    assert ids == [None, "anna"]
    assert tags == [(1, "anna", 0.9), (1, "grain", 0.4)]


def test_parse_elements_duplicate_and_reserved_ids():
    with pytest.raises(ValueError, match="more than one"):
        ops.parse_elements([{"bbox": [0, 0, 1, 1], "desc": "@a"}, {"bbox": [0, 0, 1, 1], "desc": "@a"}])
    with pytest.raises(ValueError, match="reserved"):
        ops.parse_elements([{"bbox": [0, 0, 1, 1], "desc": "@background"}])


def test_parse_elements_rejects_flag_in_box():
    with pytest.raises(ValueError, match="scene prompt"):
        ops.parse_elements([{"bbox": [0, 0, 1, 1], "desc": "<lora:a:1:outside>"}])


def test_parse_scene_prompt_targets():
    clean, tags = ops.parse_scene_prompt("a park <lora:style:0.5> <lora:loc:0.8:outside>")
    assert clean == "a park"
    assert tags == [(ops.GLOBAL, "style", 0.5), (ops.BACKGROUND, "loc", 0.8)]
    with pytest.raises(ValueError, match="unknown flag"):
        ops.parse_scene_prompt("<lora:a:1:inside>")


# --- addressing / merge -----------------------------------------------------

def test_resolve_box():
    ids = [None, "anna", "car"]
    assert ops.resolve_box("anna", ids) == 1
    assert ops.resolve_box("@CAR", ids) == 2
    assert ops.resolve_box("1", ids) == 0
    assert ops.resolve_box("*", ids) == ops.GLOBAL
    assert ops.resolve_box("background", ids) == ops.BACKGROUND
    with pytest.raises(ValueError, match="@anna"):
        ops.resolve_box("bob", ids)
    with pytest.raises(ValueError):
        ops.resolve_box("4", ids)


def test_merge_specs_node_wins():
    tags = [{"target": 1, "lora": "a.safetensors", "strength": 0.9},
            {"target": 1, "lora": "b.safetensors", "strength": 0.4}]
    nodes = [{"target": 1, "lora": "a.safetensors", "strength": 0.2}]
    merged = ops.merge_specs(tags, nodes)
    assert {(s["lora"], s["strength"]) for s in merged} == {("b.safetensors", 0.4), ("a.safetensors", 0.2)}


def test_closest_names():
    assert ops.closest_names("anna_mos", ["anna_moss.safetensors", "car.safetensors"])[0] == "anna_moss.safetensors"


# --- geometry ---------------------------------------------------------------

def _grid(mask, w):
    return [mask[i:i + w] for i in range(0, len(mask), w)]


def test_box_mask_hard():
    # left half of an 4x4 grid
    m = _grid(ops.box_mask([0, 0, 1000, 500], 4, 4), 4)
    assert m == [[1.0, 1.0, 0.0, 0.0]] * 4


def test_box_mask_aspect_and_order():
    # rows are y: top quarter of a 4 (h) x 8 (w) grid
    m = _grid(ops.box_mask([0, 0, 250, 1000], 4, 8), 8)
    assert m[0] == [1.0] * 8
    assert all(v == 0.0 for row in m[1:] for v in row)


def test_box_mask_tiny_box_keeps_one_token():
    m = ops.box_mask([510, 510, 520, 520], 8, 8)
    assert sum(m) == 1.0
    assert m[4 * 8 + 4] == 1.0


def test_box_mask_feather_is_soft_and_capped():
    m = ops.box_mask([0, 0, 1000, 1000], 20, 20, feather=1.0)  # capped to 0.3
    row = m[10 * 20:11 * 20]
    assert row[10] == 1.0
    assert 0.0 < row[0] < 1.0
    assert row == row[::-1]


def test_box_mask_skirt_grows():
    hard = sum(ops.box_mask([400, 400, 600, 600], 10, 10))
    grown = sum(ops.box_mask([400, 400, 600, 600], 10, 10, skirt=0.1))
    assert hard == 4.0 and grown == 16.0


def test_compose_masks_painter_order():
    back = [1.0, 1.0, 1.0, 0.0]
    front = [0.0, 1.0, 0.5, 0.0]
    owned, background = ops.compose_masks([back, front])
    assert owned[1] == front
    assert owned[0] == [1.0, 0.0, 0.5, 0.0]
    assert background == [0.0, 0.0, 0.0, 1.0]
    for i in range(4):
        assert owned[0][i] + owned[1][i] + background[i] == pytest.approx(1.0)


def test_module_kind():
    assert ops.module_kind("layers.3.proj.qkv") == ops.SEQ
    assert ops.module_kind("video_embedder") == ops.VEC
    assert ops.module_kind("final_linear_video") == ops.IMAGE
    assert ops.module_kind("text_embedder.blocks.0.qkv") == ops.TEXT
    assert ops.module_kind("shared_block_modulation") == ops.VEC


def test_schedule_active():
    assert ops.schedule_active(5.0, None, None)
    assert ops.schedule_active(5.0, 10.0, 1.0)
    assert not ops.schedule_active(11.0, 10.0, 1.0)
    assert not ops.schedule_active(1.0, 10.0, 1.0)
