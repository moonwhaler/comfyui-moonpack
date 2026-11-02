/**
 * Parity checks for web/lib/moss_layout_math.js against the Python mask math.
 *
 *   node tests/js/moss_layout_math.mjs
 *
 * fixtures_moss_masks.json is generated from _regional_lora_ops.py / _moss_layout_ops.py,
 * so the editor's mask overlay and captions match what the node computes.
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  applyExtras, layoutMasks, presetSize, sidecar, stripTriggers, withTriggers,
} from "../../web/lib/moss_layout_math.js";

const here = dirname(fileURLToPath(import.meta.url));
const fx = JSON.parse(readFileSync(join(here, "fixtures_moss_masks.json"), "utf8"));
let failed = 0;
function check(label, cond) {
  console.log((cond ? "PASS " : "FAIL ") + label);
  if (!cond) failed++;
}
const close = (a, b) => a.length === b.length && a.every((v, i) => Math.abs(v - b[i]) < 1e-9);

for (const c of fx.cases) {
  const got = layoutMasks(fx.layout, c.gh, c.gw, c.feather, c.skirt);
  const tag = `${c.gh}x${c.gw} f=${c.feather} s=${c.skirt}`;
  check(`${tag}: same LoRA boxes`, got.boxes.map((b) => b.index).join() === c.boxes.map((b) => b.index).join());
  check(`${tag}: masks match Python`, got.boxes.every((b, k) => close(b.mask, c.boxes[k].mask)));
  check(`${tag}: background matches Python`, close(got.background, c.background));
}

const t = fx.trigger;
check("triggers match Python", withTriggers(t.desc, t.loras) === t.expected);
check("strip triggers", stripTriggers(t.expected, t.loras) === "woman");

const boxes = [{ x: 0, y: 0, w: 1, h: 1, desc: "woman", name: "Anna", loras: [{ on: true, lora: "a", text: "anna_v1" }] }];
const side = sidecar(boxes, [{ lora: "s", target: "outside" }]);
const back = applyExtras([{ x: 0, y: 0, w: 1, h: 1, desc: "woman, anna_v1" }], side.boxes);
check("sidecar round trip", back[0].name === "Anna" && back[0].desc === "woman" && back[0].loras[0].lora === "a");

const [w, h] = presetSize(16, 9, 1.0);
check(`preset 16:9 1MP = ${w}x${h}`, w % 16 === 0 && h % 16 === 0 && Math.abs(w / h - 16 / 9) < 0.03);
check("preset 1:1 1MP = 1024", presetSize(1, 1, 1.0).join() === "1024,1024");

console.log(failed ? `${failed} FAILED` : "all passed");
process.exit(failed ? 1 : 0);
