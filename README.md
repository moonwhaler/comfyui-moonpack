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

### MoonPack/string

| Node | Purpose |
|---|---|
| **Simple String Replace** | Sequential `find => replace` pairs (one per line). Optional whole-word match. Reports malformed lines via `ignored_lines` instead of silently dropping them. |
| **Regex String Replace** | Full Python regex with case-insensitive / multiline / dotall flags and a non-destructive `test_mode` that highlights matches with `>>>…<<<`. Returns `match_count`. |
| **Regex Extract** | Returns the first or all regex matches. If the pattern has a capture group, returns the group; otherwise the whole match. `all_matches=True` emits each match as a separate `OUTPUT_IS_LIST` item. |
| **Dynamic String Concat** | Auto-expanding string concatenator. Has `template` mode (`{1}, {2}` placeholders), `prefix`/`suffix`, optional whitespace stripping, and an `ignore_empty` toggle. |
| **String Switch** | Routes one of up to 8 string inputs based on a 1-based selector. **Lazy:** only the chosen branch's upstream nodes are evaluated. |

### MoonPack/lora

| Node | Purpose |
|---|---|
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

### Conditional Bypasser
Routes any value through when `enabled` is true; when false, returns an
`ExecutionBlocker`, preventing downstream nodes from executing entirely. Useful
for graph-driven branching that depends on upstream conditions.

---

## Development

```bash
# Run the test suite
pytest tests/
```

## License

MIT — see `LICENSE`.
