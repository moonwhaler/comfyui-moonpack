# ComfyUI MoonPack

A collection of utility nodes for ComfyUI that enhance workflow efficiency and flexibility.

## Installation

1. Clone this repository into your ComfyUI `custom_nodes` directory:
```bash
cd ComfyUI/custom_nodes
git clone https://github.com/yourusername/comfyui-moonpack.git
```

2. Restart ComfyUI

## Nodes

### Fast Node Bypasser

**Category:** `moonpack/utils`

A virtual node that allows quick bypassing of multiple nodes without manually toggling each one.

**Features:**
- **Connection-based mode:** Connect any nodes to this bypasser, and it will create toggle controls for each connected node
- **Pattern matching mode:** Use the `matchTitle` property to automatically match nodes by their title using regex patterns
- **Sorting options:** Sort controlled nodes by position, alphanumeric order, or custom alphabet
- **Toggle restrictions:** Optionally limit the number of nodes that can be enabled simultaneously
- Context menu actions: "Bypass All", "Enable All", "Toggle All"

**Usage:**

*Method 1: Connection-based (Manual)*
1. Add a "Fast Node Bypasser" node to your workflow
2. Connect output from any node you want to control to the bypasser's inputs
3. The bypasser will automatically create toggle widgets for each connected node
4. Use the toggles to enable/bypass individual nodes, or right-click for batch operations

*Method 2: Pattern matching (Automatic)*
1. Add a "Fast Node Bypasser" node to your workflow
2. Right-click the node → Properties (or Properties Panel)
3. Set the `matchTitle` property to a regex pattern (e.g., `sampler`, `ksampler`, `^SDXL.*`)
4. The node will automatically find and add toggles for all nodes matching the pattern
5. Pattern matching is case-insensitive

**Properties:**
- `matchTitle` (string): Regex pattern to match node titles. Leave empty to use connection-based mode.
- `sort` (combo): Sort order for toggles
  - `position` *(default)*: Sort by node position in the graph (top-to-bottom, left-to-right)
  - `alphanumeric`: Sort alphabetically by node title
  - `custom alphabet`: Sort using custom alphabet defined in `customSortAlphabet`
- `customSortAlphabet` (string): Custom alphabet for sorting (only used when sort is "custom alphabet")
  - Can be single characters (e.g., `zyxw...`) or comma-delimited strings (e.g., `sdxl,pro,sd,n,p`)
  - Nodes starting with earlier entries appear first
  - Nodes not matching any entry are placed last, sorted alphanumerically
  - When two nodes match the same entry, normal alphanumeric order breaks the tie
- `toggleRestriction` (combo): Limit the number of enabled nodes
  - `default` *(default)*: No restrictions, any number of nodes can be enabled
  - `max one`: At most one node can be enabled at a time
  - `always one`: Exactly one node must be enabled at all times

**Example patterns:**
- `sampler` - Matches any node with "sampler" in the title
- `^KSampler` - Matches nodes starting with "KSampler"
- `Load.*Model` - Matches nodes like "Load Checkpoint", "Load LoRA Model", etc.
- `(upscale|downscale)` - Matches nodes containing either "upscale" or "downscale"

**Example custom alphabet:**
- `sdxl,sd,n,p` - Nodes starting with "sdxl" first, then "sd", then "n", then "p"
- `a,b,c` - Sort by first letter: a's first, b's second, c's third

**Toggle Restriction Behavior:**
- When set to "max one" or "always one", enabling a node automatically disables all others
- When set to "always one", you cannot disable the last enabled node
- Restrictions apply to both individual toggle clicks and context menu actions
- Note: Restrictions are only enforced when using the bypasser's toggles; manual node changes outside the bypasser may result in multiple enabled nodes

---

### Dynamic LoRA Stack

**Category:** `moonpack/lora`

Dynamically stacks LoRA inputs with automatic input expansion.

**Features:**
- Automatically adds new input slots as you connect LoRAs
- Maintains proper order of LoRA stack
- Handles nested LoRA stacks (flattens them automatically)
- Always keeps one empty input available

**Inputs:**
- Dynamic `lora_1`, `lora_2`, etc. (WANVIDLORA type)

**Outputs:**
- `WANVIDLORA` - The combined LoRA stack

**Usage:**
1. Add the "Dynamic LoRA Stack" node
2. Connect LoRA outputs to the available inputs
3. New inputs automatically appear as you connect LoRAs
4. The node outputs a single combined stack in the order of connection

---

### Dynamic String Concat

**Category:** `utils`

Dynamically concatenates multiple string inputs with automatic input expansion.

**Features:**
- Automatically adds new input slots as you connect strings
- Customizable separator between strings
- Option to ignore empty strings
- Maintains input order

**Inputs:**
- `separator` (STRING): Character(s) to place between concatenated strings (default: space)
- `ignore_empty` (BOOLEAN): Skip empty strings in concatenation (default: true)
- Dynamic `input_1`, `input_2`, etc. (STRING type)

**Outputs:**
- `concatenated_string` (STRING): The combined result

**Usage:**
1. Add the "Dynamic String Concat" node
2. Set your desired separator (e.g., ", ", " | ", "\n")
3. Connect string outputs to the available inputs
4. New inputs automatically appear as needed
5. Toggle `ignore_empty` to control whether empty strings are included

**Example:**
- Inputs: "Hello", "", "World"
- Separator: " "
- ignore_empty: true
- Output: "Hello World"

---

### Proportional Dimension

**Category:** `dimensions`

Calculates new dimensions while maintaining the original aspect ratio.

**Features:**
- Maintains aspect ratio during resizing
- Choose target dimension (shortest or longest side)
- Useful for consistent image sizing in workflows

**Inputs:**
- `width` (INT): Original width (default: 1440)
- `height` (INT): Original height (default: 1024)
- `target_size` (INT): Desired size for the selected dimension (default: 480)
- `target_side` (STRING): Which dimension to apply target_size to
  - `shortest`: Sets minimum resolution (scales up the smaller dimension)
  - `longest`: Sets maximum resolution (scales down the larger dimension)

**Outputs:**
- `width` (INT): Calculated new width
- `height` (INT): Calculated new height
- `shortest_side` (INT): The shorter dimension of the result
- `longest_side` (INT): The longer dimension of the result

**Usage:**

*Example 1: Minimum resolution*
- Input: 1920x1080, target_size: 512, target_side: "shortest"
- Output: 910x512 (shortest side is now 512)

*Example 2: Maximum resolution*
- Input: 1920x1080, target_size: 1024, target_side: "longest"
- Output: 1024x576 (longest side is now 1024)

---

### Simple String Replace

**Category:** `string`

Performs simple find-and-replace operations on strings.

**Features:**
- Multiple find/replace pairs (one per line)
- Optional whole-word matching
- Sequential replacement processing
- Empty replacement removes text

**Inputs:**
- `text` (STRING): Input text to process (must be connected)
- `find_replace_pairs` (STRING, multiline): Find/replace pairs in format `find => replace`
- `whole_word_match` (BOOLEAN): Only match complete words (default: false)

**Outputs:**
- `STRING`: Processed text

**Usage:**
```
hello => hi
world => earth
old => new
```

**Notes:**
- Replacements are applied sequentially
- If "A => B" and "B => C" are both defined, "A" becomes "C"
- Empty replacement (e.g., `text => `) removes the matched text
- Use `whole_word_match` to avoid partial matches (e.g., "the" won't match "there")

---

### Regex String Replace

**Category:** `string`

Advanced string replacement using regular expressions.

**Features:**
- Full regex pattern support
- Capture groups for complex replacements
- Test mode to preview matches
- Case-insensitive matching option
- Error handling with helpful messages

**Inputs:**
- `text` (STRING): Input text to process (must be connected)
- `pattern` (STRING, multiline): Regular expression pattern
- `replacement` (STRING, multiline): Replacement text (can use `\1`, `\2` for capture groups)
- `case_insensitive` (BOOLEAN): Ignore case when matching (default: false)
- `test_mode` (BOOLEAN): Highlight matches without replacing (default: false)

**Outputs:**
- `STRING`: Processed text (or error message if pattern is invalid)

**Common Patterns:**
- `.` = any character
- `.*` = any characters (greedy)
- `\d` = digit
- `\w` = word character (letter, digit, underscore)
- `[abc]` = matches a, b, or c
- `(text)` = capture group (can reference with `\1`, `\2`, etc.)

**Usage Examples:**

*Extract numbers:*
- Pattern: `[^\d]+`
- Replacement: ` `
- Input: "Item123Price456"
- Output: " 123 456"

*Swap words:*
- Pattern: `(\w+)\s+(\w+)`
- Replacement: `\2 \1`
- Input: "Hello World"
- Output: "World Hello"

*Test mode:*
- Enable `test_mode` to see matches wrapped in `>>>match<<<` without replacing

---

### VACE Looper Frame Mask Creator

**Category:** `VACELooper`

Calculates total frames and generates frame mask strings for VACE (Create Fade Mask Advanced, kjnodes) based on overlapping and in-between frames.

**Features:**
- Automatic frame calculation for video looping
- Generates fade mask schedule string for VACE
- Adjusts overlap based on source frame count
- Compatible with kjnodes' Create Fade Mask Advanced

**Inputs:**
- `overlapping_frames` (INT): Number of frames to overlap between loops (default: 15)
- `in_between_frames` (INT): Number of frames between overlaps (default: 51)
- `images` (IMAGE, optional): Source images to calculate maximum safe overlap

**Outputs:**
- `total_frames` (INT): Total number of frames needed
- `fade_mask` (STRING): Fade mask schedule string for VACE
- `overlap_frames` (INT): Actual overlap frames used (may be adjusted)
- `in_between_frames` (INT): In-between frames (passthrough)
- `source_frames` (INT): Number of source frames detected (0 if no images)

**Usage:**
1. Add "VACE Looper Frame Mask Creator" to your workflow
2. Set desired overlapping and in-between frame counts
3. Optionally connect source images for automatic overlap adjustment
4. Connect `total_frames` output to frame count inputs
5. Connect `fade_mask` output to VACE's "Create Fade Mask Advanced" node

**Calculation:**
- `total_frames = (2 × overlapping_frames) + in_between_frames`
- If source images are provided, overlap is limited to `source_frame_count ÷ 2`
- Fade mask format: `0:(1.0),{overlap}:(0.0),{overlap+between}:(1.0),`

---

## Tips

### Fast Node Bypasser Workflow
- Use multiple Fast Node Bypasser nodes with different `matchTitle` patterns to create organized control groups
- Combine connection-based and pattern-based bypassing in the same workflow for maximum flexibility
- Use pattern matching for consistent node naming conventions (e.g., all samplers named with "Sampler" suffix)

### Dynamic Nodes
- The Dynamic LoRA Stack and Dynamic String Concat nodes automatically manage inputs, keeping workflows clean
- You can chain multiple Dynamic nodes together

### String Processing
- Use Simple String Replace for straightforward text substitution
- Use Regex String Replace for pattern-based transformations
- Test regex patterns with `test_mode` enabled before applying replacements

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## License

MIT License.
