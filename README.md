# ComfyUI MoonPack

A focused collection of utility nodes for ComfyUI. Strings, dimensions, dynamic
inputs, fast bypassers, and a couple of video helpers.

## Installation

### Via ComfyUI Manager
Search for **MoonPack** and install.

### Manual
```bash
cd ComfyUI/custom_nodes
git clone https://github.com/moonwhaler/comfyui-moonpack.git
```
Then restart ComfyUI.

## Compatibility

**v0.2 renamed all node registry keys to use a `MoonPack_` prefix.** Workflows
saved with v0.1 still load — legacy keys are kept as aliases (marked
"(legacy)" in the menu) for one release cycle. Save your workflow once after
loading and it will automatically migrate to the new keys.

---

## Nodes

All nodes are under the **MoonPack/** category in the Add Node menu.

### MoonPack/image

| Node | Purpose |
|---|---|
| **Proportional Dimension** | Resize W/H to a target side while preserving aspect; snap to a divisor with nearest/floor/ceil rounding; optional `from_image` input. Outputs `width, height, shortest_side, longest_side, scale`. |
| **Dimension From Image** | Reads `width, height, batch_size` from an `IMAGE` tensor. |
| **Smart Resolution** | Picks a model-friendly resolution near a megapixel budget while preserving aspect ratio. Presets for SD 1.5, SDXL, Flux (1.0/1.4 MP), and Wan 480p/720p. |
| **Reference Concat** | Concatenates reference images into a strip against a main image (e.g. identity refs for a video first frame). Strip goes on the main image's longest side, capped to that side's length (never stretched beyond it), main image never shrunk. `offset` slides the strip into the main image (overlap) or away from it (filled gap). If `main_image` is left unconnected, outputs an auto-sized contact-sheet grid of just the reference images instead, sized to the *largest* reference (smaller ones are upscaled to match, not the other way around) — for full control over that grid layout, use **Reference Grid** instead. `interpolation` picks the resampling filter (nearest/bilinear/bicubic/lanczos). `max_ref_side` caps each reference's longest side (downscale only) before any sizing math, so one oversized reference can't blow up the output. Accepts a MoonPack Image List (each reference keeps its native resolution) or a plain stacked `IMAGE` batch. Outputs a `MASK` marking the reference area. |
| **Reference Grid** | Arranges reference images into a contact-sheet grid with full layout control: `columns` (0 = auto square-ish), `fit_mode` (cover/contain/stretch per cell), `cell_size_source` (largest/smallest/average, with optional fixed `cell_width`/`cell_height` overrides), `fill_direction` (row-major/column-major), and `last_row_align` (left/center/right) for an incomplete trailing row or column. Same `interpolation`, `max_ref_side`, and Image List support as Reference Concat. Outputs a `MASK` marking the actual reference pixels (excludes empty cells and any `contain` padding). |
| **Image List** | Collects images from auto-expanding slots (➕-style, like Dynamic LoRA Stack) into a native ComfyUI list instead of a stacked batch tensor, so mixed-resolution images keep their own resolution instead of all being resized to match. Feed to Reference Concat, Reference Grid, or any other list-aware node. |
| **Load Image (Labeled)** | Loads an image, optionally crops it to a `crop_x`/`crop_y`/`crop_width`/`crop_height` region (0 width/height = no crop on that axis), then bakes an editable caption bar (e.g. "Front View") onto the (possibly cropped) result as extra top/bottom space — the label bar itself never crops or resizes further. A bold arrow in the bar points back at the photo; text and arrow toggle independently. Background/text colors are color-swatch widgets; an optional inset `border_width` frames the whole result in the background color. The node's **Edit Crop** button opens a maximized popup to drag out the crop region visually on the original image; the **Preview** button renders the exact composited (cropped + labeled) result before queuing. |

### MoonPack/string

| Node | Purpose |
|---|---|
| **Simple String Replace** | Sequential `find => replace` pairs (one per line). Optional whole-word match. Reports malformed lines via `ignored_lines` instead of silently dropping them. |
| **Regex String Replace** | Full Python regex with case-insensitive / multiline / dotall flags and a non-destructive `test_mode` that highlights matches with `>>>…<<<`. Returns `match_count`. |
| **Regex Extract** | Returns the first or all regex matches. If the pattern has a capture group, returns the group; otherwise the whole match. `all_matches=True` emits each match as a separate `OUTPUT_IS_LIST` item. |
| **Dynamic String Concat** | Auto-expanding string concatenator. Has `template` mode (`{1}, {2}` placeholders), `prefix`/`suffix`, optional whitespace stripping, and an `ignore_empty` toggle. |
| **String Switch** | Routes one of up to 8 string inputs based on a 1-based selector. **Lazy:** only the chosen branch's upstream nodes are evaluated. |
| **Text Builder** | Joins any number of multiline text blocks typed on the node. Blocks are added, toggled, reordered (`▲`/`▼`) and removed on the node. A connected `text` input is always the first part. |

### MoonPack/lora

| Node | Purpose |
|---|---|
| **MoonLoRA Loader** | Applies any number of LoRAs to `MODEL`/`CLIP` and concatenates the trigger text of the enabled ones into a single `STRING`. |
| **Dynamic LoRA Stack** | Auto-expanding `WANVIDLORA` stacker (designed for kijai's WanVideoWrapper). Flattens nested lists; an empty stack returns `[]`, not `None`. |
| **MOSS Regional LoRA** | MOSS-Image only. Applies LoRAs per *Create Bounding Boxes* box: each LoRA's delta is masked per image token, so outside its box it contributes nothing. One model pass per step. |
| **MOSS Box LoRA** | Chainable LoRA → box assignment (`@id`, box number, `*` or `background`) with strength and start/end percent, for MOSS Regional LoRA. |

### MoonPack/utils

| Node | Purpose |
|---|---|
| **Fast Node Bypasser** | Adds a toggle widget per controlled node. Connect nodes to control them, **or** set the `matchTitle` regex property to auto-match by title. Sort by position / alphanumeric / custom alphabet. Toggle restrictions: `default` / `max one` / `always one`. Right-click for `Bypass All / Enable All / Toggle All / Refresh`. |
| **Conditional Bypasser** | Server-side gate: passes input through when enabled. When disabled, `disabled_behavior` picks `block` (returns `ExecutionBlocker`, downstream nodes don't run — default) or `pass_none` (downstream nodes run but receive `None`). Accepts any data type. |

### MoonPack/video

| Node | Purpose |
|---|---|
| **VACE Looper Frame Mask** | Calculates total frames and a kjnodes 'Create Fade Mask Advanced' schedule. Optional `images` input clamps overlap to half the source length and reports it via `was_clamped`. |
| **Frame Mask Generator** | General-purpose schedule generator. Modes: `linear_loop`, `ping_pong`, `ease_in_out`, `fade_in`, `fade_out`, `custom`. |

---

## Notable Details

### Fast Node Bypasser — pattern matching
Set the `matchTitle` property to a regex (e.g. `^KSampler`, `(upscale|downscale)`)
and the bypasser auto-discovers matching nodes. Use the **Refresh** menu item to
re-scan after renaming nodes or changing patterns.

`customSortAlphabet` accepts either single chars (`zyxw…`) or comma-delimited
prefixes (`sdxl,sd,n,p`). Nodes whose titles start with the earliest entry come
first; ties break alphanumerically.

### String Switch — lazy evaluation
`MoonPack_StringSwitch` declares each input as `lazy: True` and implements
`check_lazy_status`, so only the upstream graph for the **selected** branch is
evaluated. Use this for prompt A/B tests where each branch may chain expensive
generation.

### Dynamic String Concat — template mode
If the `template` widget is non-empty, `{1}, {2}, …` placeholders are
interpolated from input slots and `separator` is ignored:

```
template:  "{1}, in the style of {2}"
input_1:   "a cat"
input_2:   "Studio Ghibli"
result:    "a cat, in the style of Studio Ghibli"
```

Missing slots resolve to an empty string.

### MoonLoRA Loader — LoRAs and their trigger words in one node

Each row on the node carries a LoRA *and* the text that belongs with it, so the
two can never drift apart. Toggling a row off removes both the LoRA and its
trigger words from the output.

```
  ⊙ Toggle All                        Strength

 ╭──────────────────────────────────────────────╮
 │ ⬤  style/pixel_v3.safetensors   ◀1.00▶    ✕ │
 │     pixel art, 8bit                          │
 ╰──────────────────────────────────────────────╯

              ➕ Add LoRA
```

- **➕ Add LoRA** opens a filterable list of your local LoRA files.
- Click the filename to swap it, the strength to type a value, or drag the
  strength sideways to scrub it.
- Click the second line to edit that LoRA's trigger text.
- **✕** removes the row; right-click a row to toggle, reorder or edit it.
- Row order is the order the LoRAs are applied *and* the order their texts are
  concatenated.
- The `separator` widget is inserted verbatim between texts (default `". "`).
  Empty texts and disabled rows contribute nothing.
- Node property **Show Strengths** switches every row between one strength and
  separate model/clip strengths.
- `CLIP` is optional — leave it unconnected for a model-only patch.
- A LoRA whose file has gone missing is skipped with a warning, and its trigger
  text is dropped with it.

Everything is local. There is no Civitai lookup and no trigger-word scraping;
the text is whatever you type, stored in the workflow.

### MOSS Regional LoRA — LoRAs per bounding box

Regular LoRAs bleed into the whole MOSS-Image picture. This node adds each
LoRA in bypass mode (`W·x + m · s · ΔW·x`) and multiplies its delta by the
box's token mask `m`, so a character LoRA only acts inside its box. The base
weights stay untouched, which also works with int8/fp8 checkpoints.

```
Create Bounding Boxes.elements ─┐
Load Diffusion Model.MODEL ─────┴─► MOSS Regional LoRA ─┬─ elements, prompt ─► MOSS-Image Layout Prompt ─► Text Encoder
                                                         └─ MODEL ─► KSampler
```

Always feed the node's **cleaned** `elements` and `prompt` into
*MOSS-Image Layout Prompt*, otherwise the tag text ends up in the caption.

**Tags in a box description**

```
@anna woman in a red coat <lora:anna_moss:0.9> <lora:film_grain:0.4>
```

- `@anna` names the box (optional; boxes are also addressed by the number shown
  in the bounding box preview, starting at 1). Ids and tags are stripped.
- `<lora:name>` / `<lora:name:weight>`: the name may omit `.safetensors` and the
  subfolder. Several LoRAs in one box add up.
- Keep trigger words outside the tag, so they reach the caption.

**Tags in the scene prompt:** `<lora:style:0.5>` applies to the whole image like
a normal LoRA; `<lora:location:0.8:outside>` only acts outside the LoRA boxes.

**MOSS Box LoRA** nodes do the same with a LoRA dropdown and a
`start_percent`/`end_percent` schedule. Chain them into `regions`. For the same
box and file, the node wins over a tag.

**Masks**

- `feather` softens box edges (fraction of the box's shorter side, max 0.3);
  `skirt` grows every LoRA box by a fraction of the image's shorter side. A
  tiny box always keeps at least one full-strength token.
- Overlaps follow drawing order: a later box sits on top of an earlier one, so
  draw the background first and the foreground last, as the layout docs advise.
  Only boxes that carry a LoRA take part.
- `text_tokens = masked` (default) keeps box LoRAs off the text tokens, which
  gives the least bleed. Set it to `global` if a LoRA needs its trigger words to
  be processed by its own weights.
- `mask_preview` shows one mask per LoRA box, then the background mask if one is
  used, at `preview_width` × `preview_height`.

**Limits**

- Only additive adapters (LoRA, LoHa, LoKr) can be masked. Bias/diff patches and
  OFT in a regional assignment are skipped with a warning; global assignments
  apply them as normal weight patches. DoRA magnitude is ignored.
- The embedder and the modulation layers have no per-token place to mask, so box
  LoRAs skip them. A `*` LoRA applies there too.
- Attention still mixes tokens, so a little style can seep into neighbouring
  regions. Layout prompts are experimental in MOSS: a subject drawn outside its
  box loses its LoRA. Keep boxes generous, or use `skirt`.
- On int8/fp8 checkpoints, layers carrying a LoRA leave the fused quantized
  kernel path, so sampling gets slower.
- Use one MOSS Regional LoRA node per model. Feed extra LoRAs through
  MOSS Box LoRA nodes, not a second regional node.

### Text Builder — prompt fragments as a stack

`Dynamic String Concat` joins strings arriving over links. **Text Builder** owns
its text instead: press **➕ Add Text** for a block, and each block is a real
multiline textarea with its own control strip.

- **Toggle** — a disabled block keeps its text but contributes nothing, so
  prompt fragments can be A/B'd without deleting them. `Toggle All` flips every
  block at once.
- **Name a block** — click its `#1` caption (or pick Rename from the block's
  right-click menu) to label it, e.g. `#2  lighting`. Names are cosmetic; they
  never reach the output.
- **Reorder** — `▲` / `▼` on the strip, or Move Up / Move Down in the block's
  right-click menu. Output order is the order the blocks appear in, not the
  order they were created.
- **Right-click a block** — Toggle, Move Up, Move Down and Remove, the same
  actions as the strip's own buttons.
- **`text` input** — optional. When connected it is always the first part and
  cannot be reordered.
- **Joining** — parts are joined with `separator` verbatim (default `,`, so
  `a,b`; use `, ` for a space). `strip_whitespace` trims each part and
  `skip_empty` drops the ones that end up empty, including the link input, so
  no stray separators appear.

### Conditional Bypasser
Routes any value through when `enabled` is true. When false, `disabled_behavior`
controls what happens: `block` (default) returns an `ExecutionBlocker`,
preventing downstream nodes from executing entirely; `pass_none` lets
downstream nodes run normally but receive `None` instead of the value. Useful
for graph-driven branching that depends on upstream conditions.

---

## Development

```bash
# Python nodes
pytest tests/

# Frontend widgets (MoonLoRA Loader) — needs Node, no dependencies
# Text Builder's frontend has no headless checks; verify it in ComfyUI.
node tests/js/run.mjs
```

## License

MIT — see `LICENSE`.
