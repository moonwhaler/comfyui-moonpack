import json
import os

import _moss_layout_ops as lo
import _regional_lora_ops as ops

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures_kj_moss_layout.json")


def test_layout_matches_kijai_fixture():
    with open(FIXTURE) as f:
        fx = json.load(f)
    summ = lo.summary(*fx["summary_args"])
    out = lo.layout(summ, fx["boxes"], fx["width"], fx["height"])
    assert json.dumps(out) == json.dumps(fx["layout"])


def _box(**kw):
    return {**lo.blank_box(), "x": 0.0, "y": 0.0, "w": 0.5, "h": 0.5, **kw}


def test_triggers_appended_and_hidden_skipped():
    boxes = [
        _box(desc="woman", loras=[{"on": True, "lora": "anna.safetensors", "strength": 0.9, "text": "anna_v1"},
                                  {"on": False, "lora": "x.safetensors", "strength": 1, "text": "nope"}]),
        _box(desc="hidden", hidden=True),
    ]
    summ = lo.summary("park", [], "none", [], [{"on": True, "lora": "s.safetensors", "strength": 1, "text": "style_x"}])
    out = lo.layout(summ, boxes, 1024, 1024)
    assert out["summary"]["caption"] == "park, style_x"
    assert [i["caption"] for i in out["items"]] == ["woman, anna_v1"]


def test_layout_none_when_only_hidden():
    assert lo.layout(lo.summary("p", [], "none", []), [_box(hidden=True)], 512, 512) is None


def test_regional_assignments():
    boxes = [
        _box(x=0.5, w=0.5, loras=[{"on": True, "lora": "a", "strength": 0.8, "start": 0.2, "end": 0.1}]),
        _box(hidden=True, loras=[{"on": True, "lora": "b", "strength": 1}]),
        _box(loras=[{"on": True, "lora": "c", "strength": 0}, {"on": True, "lora": "None", "strength": 1}]),
        _box(x=0.2, w=-0.1, h=0.3, loras=[{"lora": "d", "strength": "1.5"}]),
    ]
    scene = [{"on": True, "lora": "s", "strength": 0.5, "target": "outside"},
             {"on": True, "lora": "g", "strength": 0.4}]
    bboxes, entries = lo.regional_assignments(boxes, scene)
    assert set(bboxes) == {0, 2, 3}  # hidden box 1 dropped, indices stay editor numbers
    assert bboxes[0] == [0.0, 500.0, 500.0, 1000.0]
    assert [round(v, 6) for v in bboxes[3]] == [0.0, 100.0, 300.0, 200.0]  # negative width normalized
    assert [(e["target"], e["lora"]) for e in entries] == [(0, "a"), (3, "d"), (ops.BACKGROUND, "s"), (ops.GLOBAL, "g")]
    assert entries[0]["start"] == 0.1 and entries[0]["end"] == 0.2
    assert entries[1]["strength"] == 1.5


def test_strip_triggers_and_extras_roundtrip():
    loras = [{"on": True, "lora": "a", "strength": 1, "text": "anna_v1"}]
    boxes = [_box(desc="woman", name="Anna", loras=loras), _box(desc="car")]
    lay = lo.layout(lo.summary("p", [], "none", []), boxes, 1024, 1024)
    lay[lo.SIDECAR_KEY] = lo.sidecar(boxes, [])
    back = lo.apply_extras(lo.layout_to_boxes(lay, 1024, 1024), lay[lo.SIDECAR_KEY]["boxes"])
    assert back[0]["desc"] == "woman" and back[0]["name"] == "Anna" and back[0]["loras"] == loras
    assert back[1]["desc"] == "car" and back[1]["loras"] == []
    assert lo.strip_triggers("anna_v1", loras) == ""
    assert lo.strip_triggers("woman, other", loras) == "woman, other"


def test_bbox_outputs_skip_hidden():
    out = lo.bbox_outputs([_box(), _box(hidden=True), _box(nobbox=True)], 100, 200)
    assert out == [[{"x": 0, "y": 0, "width": 50, "height": 100}]]


def test_seed_boxes_carry_lora_list():
    boxes = lo.seed_boxes([[{"x": 10, "y": 20, "width": 30, "height": 40}]], 100, 100)
    assert boxes[0]["loras"] == [] and boxes[0]["x"] == 0.1


def test_front_first_compose():
    # box 0 is front-most: composing back to front must give box 0 the overlap
    front = ops.box_mask([0, 0, 1000, 1000], 2, 2)
    back = ops.box_mask([0, 0, 1000, 1000], 2, 2)
    owned, _ = ops.compose_masks([back, front])  # back first, as the engine passes reversed order
    assert owned[1] == [1.0] * 4 and owned[0] == [0.0] * 4
