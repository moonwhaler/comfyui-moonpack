import pytest

import _regional_lora_ops as ops


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


# --- attention ownership ----------------------------------------------------

def test_measured_layers_middle_third():
    assert ops.measured_layers(42) == [14, 16, 18, 20, 22, 24, 26]
    assert ops.measured_layers(2) == [0]


def _ownership_fixture():
    # 1 x 6 strip: box A covers cells 0-3, box B covers 2-5 (overlap 2-3); no spill.
    geo = {0: [1, 1, 1, 1, 0, 0], 1: [0, 0, 1, 1, 1, 1]}
    reach = {0: [1, 1, 1, 1, 0, 0], 1: [0, 0, 1, 1, 1, 1]}
    return geo, reach


def test_ownership_overlap_follows_attention():
    geo, reach = _ownership_fixture()
    # A's caption is attended in cells 0-2, B's in 3-5
    scores = {0: [1, 1, 1, 0.1, 0, 0], 1: [0, 0, 0.1, 1, 1, 1]}
    owned, bg = ops.ownership_masks(geo, reach, scores, 1, 6)
    assert owned[0][0] == 1 and owned[1][5] == 1          # exclusive zones stay geometric
    assert owned[0][2] > owned[1][2] and owned[1][3] > owned[0][3]
    for i in range(6):
        assert owned[0][i] + owned[1][i] + bg[i] == __import__("pytest").approx(1.0)


def test_ownership_back_box_wins_overlap_when_attended():
    geo, reach = _ownership_fixture()
    scores = {0: [1, 1, 0, 0, 0, 0], 1: [0, 0, 1, 1, 1, 1]}  # B (the back box) owns the overlap
    owned, _ = ops.ownership_masks(geo, reach, scores, 1, 6)
    assert owned[1][2] > 0.5 and owned[1][3] > 0.5 and owned[0][3] == 0


def test_ownership_ring_needs_score():
    geo = {0: [0, 1, 1, 0, 0, 0]}
    reach = {0: [1, 1, 1, 1, 1, 0]}
    owned, _ = ops.ownership_masks(geo, reach, {0: [0.9, 1, 1, 0.2, 0, 0]}, 1, 6)
    assert owned[0][0] > 0 and owned[0][5] == 0           # spill only where the subject is attended
    assert owned[0][4] < 0.5


def test_ownership_without_measurement_is_empty_contest():
    geo, reach = _ownership_fixture()
    owned, bg = ops.ownership_masks(geo, reach, {0: [0] * 6, 1: [0] * 6}, 1, 6)
    assert owned[0][0] == 1 and owned[0][2] < 0.5 and owned[1][3] < 0.5  # only the soft edge reaches in
