// --- minimal browser / LiteGraph stubs -------------------------------------
const listeners = [];
globalThis.document = {
  addEventListener: (t, f) => listeners.push([t, f]),
  getElementById: () => null,
  createElement: () => ({ style: {}, classList: { add() {}, remove() {} }, append() {},
                          appendChild() {}, addEventListener() {}, replaceChildren() {},
                          querySelectorAll: () => [] }),
  head: { appendChild() {} },
  body: { appendChild() {} },
};
globalThis.window = { innerWidth: 1920, innerHeight: 1080 };
globalThis.LiteGraph = {
  NODE_WIDGET_HEIGHT: 20,
  NODE_TEXT_SIZE: 14,
  WIDGET_TEXT_COLOR: "#ddd",
  WIDGET_BGCOLOR: "#222",
  WIDGET_OUTLINE_COLOR: "#666",
  ContextMenu: class { constructor(items, opts) { globalThis.__menu = { items, opts }; } },
};

// A recording 2d context good enough for measureText-driven layout code.
function fakeCtx() {
  return new Proxy({
    measureText: (s) => ({ width: String(s).length * 7 }),
    save() {}, restore() {}, beginPath() {}, moveTo() {}, lineTo() {},
    quadraticCurveTo() {}, closePath() {}, fill() {}, stroke() {}, arc() {},
    fillText() {}, globalAlpha: 1, fillStyle: "", strokeStyle: "", lineWidth: 1,
    lineCap: "", textAlign: "", textBaseline: "", font: "",
  }, { get: (t, k) => (k in t ? t[k] : () => {}), set: (t, k, v) => (t[k] = v, true) });
}

await import("./extensions/moonpack/moonlora_loader.js");
const ext = globalThis.__ext;

// --- fake ComfyUI node type ------------------------------------------------
function makeNodeType() {
  function NodeType() {}
  NodeType.prototype.addCustomWidget = function (w) { this.widgets.push(w); return w; };
  NodeType.prototype.setDirtyCanvas = function () {};
  NodeType.prototype.computeSize = function () {
    let h = 0;
    for (const w of this.widgets) h += (w.computeSize ? w.computeSize(this.size[0])[1] : 20) + 4;
    return [280, h + 10];
  };
  NodeType.prototype.configure = function (info) {
    if (info.size) this.size = [...info.size];
    const vals = info.widgets_values || [];
    for (let i = 0; i < vals.length; i++) if (this.widgets[i]) this.widgets[i].value = vals[i];
  };
  NodeType.prototype.serialize = function () {
    return { size: [...this.size],
             widgets_values: this.widgets.map(w => w.serializeValue ? w.serializeValue(this) : w.value) };
  };
  return NodeType;
}
function newNode(NodeType) {
  const n = new NodeType();
  n.size = [280, 100];
  n.pos = [0, 0];
  n.properties = {};
  // the native `separator` widget ComfyUI creates from INPUT_TYPES
  n.widgets = [{ name: "separator", type: "text", value: ". ", options: {} }];
  n.onNodeCreated();
  return n;
}
/** Mimics ComfyUI graphToPrompt widget serialisation. */
function toPromptInputs(node) {
  const inputs = {};
  for (const w of node.widgets) {
    if (w.options && w.options.serialize === false) continue;
    inputs[w.name] = w.serializeValue ? w.serializeValue(node) : w.value;
  }
  return inputs;
}
/** Runs a draw pass so hit-area bounds are populated. */
function layout(node) {
  const ctx = fakeCtx();
  let y = 0;
  for (const w of node.widgets) {
    const h = w.computeSize ? w.computeSize(node.size[0])[1] : 20;
    w.last_y = y;
    w.draw?.(ctx, node, node.size[0], y, h);
    y += h + 4;
  }
}

const NodeType = makeNodeType();
ext.beforeRegisterNodeDef(NodeType, { name: "MoonPack_MoonLoraLoader" });

let failures = 0;
function check(label, cond, extra) {
  if (cond) { console.log("  ok  " + label); }
  else { failures++; console.log("  FAIL " + label, extra !== undefined ? JSON.stringify(extra) : ""); }
}

console.log("\n[1] node creation");
const n = newNode(NodeType);
check("separator widget survives", n.widgets[0].name === "separator");
check("property defaults to single strength", n.properties["Show Strengths"] === "Single Strength");
check("no rows yet", n.moonRows().length === 0);

console.log("\n[2] adding rows keeps them above the button");
const r1 = n.moonAddRow("style/a.safetensors");
const r2 = n.moonAddRow("b.safetensors");
const r3 = n.moonAddRow("c.safetensors");
check("row names increment", n.moonRows().map(r => r.name).join(",") === "lora_1,lora_2,lora_3",
      n.moonRows().map(r => r.name));
check("button is last", n.widgets[n.widgets.length - 1] === n._moonButton);
check("rows sit before the bottom divider",
      n.widgets.map(w => w.name).join(",") ===
      "separator,moonDividerTop,moonHeader,lora_1,lora_2,lora_3,moonDividerBottom,moonAddButton",
      n.widgets.map(w => w.name));

console.log("\n[3] prompt serialisation");
r1.value.text = "  alpha  ";
r2.value.on = false;
r2.value.strength = 0.5;
let inputs = toPromptInputs(n);
check("chrome widgets excluded", !("moonHeader" in inputs) && !("moonAddButton" in inputs),
      Object.keys(inputs));
check("separator included", inputs.separator === ". ");
check("row order matches display", Object.keys(inputs).join(",") === "separator,lora_1,lora_2,lora_3",
      Object.keys(inputs));
check("single mode omits strengthTwo", !("strengthTwo" in inputs.lora_1), inputs.lora_1);
check("row payload shape", inputs.lora_1.on === true && inputs.lora_1.lora === "style/a.safetensors"
      && inputs.lora_1.strength === 1 && inputs.lora_1.text === "  alpha  ", inputs.lora_1);
check("disabled row still serialises", inputs.lora_2.on === false && inputs.lora_2.strength === 0.5);

console.log("\n[4] move down reorders the prompt");
layout(n);
const slot = n.getSlotInPosition(0, r1.last_y + 5);
check("row claimed by getSlotInPosition", slot?.widget === r1);
n.getSlotMenuOptions(slot);
const menu = globalThis.__menu.items.filter(Boolean);
menu.find(m => m.content.includes("Move Down")).callback();
check("lora_1 moved after lora_2",
      Object.keys(toPromptInputs(n)).join(",") === "separator,lora_2,lora_1,lora_3",
      Object.keys(toPromptInputs(n)));
check("move up disabled on the first row",
      (n.getSlotMenuOptions(n.getSlotInPosition(0, (layout(n), n.moonRows()[0].last_y + 5))),
       globalThis.__menu.items.filter(Boolean).find(m => m.content.includes("Move Up")).disabled) === true);

console.log("\n[5] dual strength mode");
n.properties["Show Strengths"] = "Separate Model & Clip";
n.onPropertyChanged("Show Strengths", "Separate Model & Clip");
inputs = toPromptInputs(n);
check("strengthTwo seeded from strength", inputs.lora_1.strengthTwo === inputs.lora_1.strength,
      inputs.lora_1);
n.properties["Show Strengths"] = "Single Strength";
n.onPropertyChanged("Show Strengths", "Single Strength");
check("strengthTwo dropped again", !("strengthTwo" in toPromptInputs(n).lora_1));

console.log("\n[6] toggle all");
check("mixed state reads null", n.moonAllRowsState() === null, n.moonAllRowsState());
n.moonToggleAllRows();
check("all on after first toggle", n.moonRows().every(r => r.value.on));
n.moonToggleAllRows();
check("all off after second toggle", n.moonRows().every(r => !r.value.on));

console.log("\n[7] save / reload round-trip");
n.moonToggleAllRows();
n.moonRows()[1].value.text = "beta";
n.moonRows()[1].value.strength = 0.42;
const saved = n.serialize();
const reloaded = new NodeType();
reloaded.size = [280, 100];
reloaded.pos = [0, 0];
reloaded.properties = {};
reloaded.widgets = [{ name: "separator", type: "text", value: "", options: {} }];
reloaded.onNodeCreated();
reloaded.configure(saved);
check("separator restored", reloaded.widgets[0].value === ". ", reloaded.widgets[0].value);
check("row count restored", reloaded.moonRows().length === 3, reloaded.moonRows().length);
check("row order restored",
      reloaded.moonRows().map(r => r.value.lora).join(",") ===
      n.moonRows().map(r => r.value.lora).join(","),
      reloaded.moonRows().map(r => r.value.lora));
check("text restored", reloaded.moonRows()[1].value.text === "beta");
check("strength restored", reloaded.moonRows()[1].value.strength === 0.42);
check("names renumbered from 1",
      reloaded.moonRows().map(r => r.name).join(",") === "lora_1,lora_2,lora_3");
check("chrome not duplicated",
      reloaded.widgets.filter(w => w.name === "moonHeader").length === 1,
      reloaded.widgets.map(w => w.name));

console.log("\n[8] hit areas after a draw pass");
layout(reloaded);
const row = reloaded.moonRows()[0];
const areas = Object.entries(row.hitAreas).filter(([, a]) => a.bounds[2] > 0);
check("toggle, lora, text, strength and remove all hit-testable",
      ["toggle", "lora", "text", "remove", "strengthDec", "strengthVal", "strengthInc"]
        .every(k => row.hitAreas[k].bounds[2] > 0),
      areas.map(([k]) => k));
check("dual-only areas inert in single mode",
      row.hitAreas.strengthTwoVal.bounds[2] === 0);
const before = row.value.on;
row.mouse({ type: "pointerdown" }, [row.hitAreas.toggle.bounds[0] + 2, row.last_y + 6], reloaded);
check("clicking the toggle flips the row", row.value.on === !before);
const base = row.value.strength;
const stepX = row.hitAreas.strengthInc.bounds[0] + 2;
row.mouse({ type: "pointerdown" }, [stepX, row.last_y + 6], reloaded);
row.mouse({ type: "pointerup" }, [stepX, row.last_y + 6], reloaded);
check("increment arrow steps by 0.05", row.value.strength === Math.round((base + 0.05) * 100) / 100,
      [base, row.value.strength]);
const valX = row.hitAreas.strengthVal.bounds[0] + 2;
const afterStep = row.value.strength;
row.mouse({ type: "pointerdown" }, [valX, row.last_y + 6], reloaded);
row.mouse({ type: "pointermove" }, [valX + 10, row.last_y + 6], reloaded);
row.mouse({ type: "pointerup" }, [valX + 10, row.last_y + 6], reloaded);
check("dragging scrubs and suppresses the click",
      row.value.strength === Math.round((base + 0.05 + 0.1) * 100) / 100, [base, row.value.strength]);
check("clicking empty space is ignored",
      row.mouse({ type: "pointerdown" }, [-50, row.last_y + 6], reloaded) === false);

console.log("\n[9] remove");
const removed = reloaded.moonRows()[1];
reloaded.moonRemoveRow(removed);
check("row gone", reloaded.moonRows().length === 2);
check("remaining names intact",
      reloaded.moonRows().map(r => r.name).join(",") === "lora_1,lora_3",
      reloaded.moonRows().map(r => r.name));

console.log("\n[10] low quality zoom");
const appMod = await import("./scripts/app.js");
appMod.app.canvas.ds.scale = 0.3;
let threw = null;
try { layout(reloaded); } catch (e) { threw = e; }
check("draws without throwing when zoomed out", threw === null, threw?.message);
appMod.app.canvas.ds.scale = 1;

console.log(failures ? `\n${failures} FAILURE(S)` : "\nALL JS CHECKS PASS");
// run.mjs sets the exit code once it has cleaned up the temp mirror.
globalThis.__failures = failures;
