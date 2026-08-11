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
| **Reference Concat** | Concatenates reference images into a strip against a main image (e.g. identity refs for a video first frame). Strip goes on the main image's longest side, capped to that side's length (never stretched beyond it), main image never shrunk. `offset` slides the strip into the main image (overlap) or away from it (filled gap). If `main_image` is left unconnected, outputs an auto-sized contact-sheet grid of just the reference images instead, sized to the *largest* reference (smaller ones are upscaled to match, not the other way around). `interpolation` picks the resampling filter (nearest/bilinear/bicubic/lanczos). `max_ref_side` caps each reference's longest side (downscale only) before any sizing math, so one oversized reference can't blow up the output. Accepts a MoonPack Image List (each reference keeps its native resolution) or a plain stacked `IMAGE` batch. Outputs a `MASK` marking the reference area. |
| **Image List** | Collects images from auto-expanding slots (➕-style, like Dynamic LoRA Stack) into a native ComfyUI list instead of a stacked batch tensor, so mixed-resolution images keep their own resolution instead of all being resized to match. Feed to Reference Concat or any other list-aware node. |

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

### MoonPack/utils

| Node | Purpose |
|---|---|
| **Fast Node Bypasser** | Adds a toggle widget per controlled node. Connect nodes to control them, **or** set the `matchTitle` regex property to auto-match by title. Sort by position / alphanumeric / custom alphabet. Toggle restrictions: `default` / `max one` / `always one`. Right-click for `Bypass All / Enable All / Toggle All / Refresh`. |
| **Conditional Bypasser** | Server-side gate: passes input through when enabled, returns `ExecutionBlocker` so downstream nodes don't run when disabled. Accepts any data type. |

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
Routes any value through when `enabled` is true; when false, returns an
`ExecutionBlocker`, preventing downstream nodes from executing entirely. Useful
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
