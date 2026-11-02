"""Pure logic for the MOSS Regional LoRA node: tags, box addressing, token masks.

Deliberately free of torch and comfy so it can be unit tested on its own. The
node module (`moss_regional_lora_node.py`) turns the plain-list masks built
here into tensors once per latent size.

Conventions
-----------
* Boxes come from core *Create Bounding Boxes* ``elements``:
  ``{"type", "bbox": [ymin, xmin, ymax, xmax] on a 0-1000 grid, "desc", ...}``.
* A box is addressed by the first ``@id`` in its description, or by its
  1-based index as shown in the bounding box preview.
* Targets: an int box index (0-based internally), ``GLOBAL`` (whole image,
  like a normal LoRA) or ``BACKGROUND`` (outside every LoRA box).
"""

import difflib
import re

GLOBAL = "*"
BACKGROUND = "background"
RESERVED_TARGETS = (GLOBAL, BACKGROUND)

# <lora:name>, <lora:name:0.8>, <lora:name:0.8:outside>
_TAG_RE = re.compile(r"<lora:([^:<>]+?)(?::([^:<>]*))?(?::([^:<>]*))?>", re.IGNORECASE)
# '@anna' at the start or after whitespace (so e-mail-like text is left alone)
_ID_RE = re.compile(r"(?<!\S)@([A-Za-z0-9_][A-Za-z0-9_\-]*)")
_SPACES_RE = re.compile(r"[ \t]{2,}")


def _tidy(text: str) -> str:
    """Collapses the gaps a removed tag leaves behind, keeping line breaks."""
    lines = [_SPACES_RE.sub(" ", line).strip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def _parse_strength(raw, tag: str) -> float:
    if raw is None or raw.strip() == "":
        return 1.0
    try:
        return float(raw)
    except ValueError:
        raise ValueError(f"MOSS Regional LoRA: bad strength '{raw}' in tag {tag}") from None


def parse_tags(text):
    """Returns (text without lora tags, [(name, strength, flag-or-None)])."""
    if not isinstance(text, str):
        return "", []
    tags = []

    def collect(match):
        name = match.group(1).strip()
        strength = _parse_strength(match.group(2), match.group(0))
        flag = match.group(3)
        flag = flag.strip().lower() if flag and flag.strip() else None
        tags.append((name, strength, flag))
        return " "

    return _tidy(_TAG_RE.sub(collect, text)), tags


def parse_box_desc(desc):
    """Returns (clean description, box id or None, tags) for one box.

    The first '@id' names the box; every '@id' is stripped so none reaches the
    caption.
    """
    clean, tags = parse_tags(desc)
    ids = _ID_RE.findall(clean)
    clean = _tidy(_ID_RE.sub(" ", clean))
    return clean, (ids[0].lower() if ids else None), tags


def parse_elements(elements):
    """Parses every box description.

    Returns (cleaned elements, box ids, [(box index, name, strength)]).
    Elements are copied, never mutated: the upstream node's output is cached.
    """
    cleaned, ids, tags = [], [], []
    for index, element in enumerate(elements if isinstance(elements, list) else []):
        if not isinstance(element, dict):
            continue
        clean, box_id, box_tags = parse_box_desc(element.get("desc", ""))
        if box_id is not None and box_id in ids:
            raise ValueError(f"MOSS Regional LoRA: box id '@{box_id}' is used by more than one box.")
        if box_id in RESERVED_TARGETS:
            raise ValueError(f"MOSS Regional LoRA: '@{box_id}' is reserved, pick another box id.")
        for name, strength, flag in box_tags:
            if flag is not None:
                raise ValueError(
                    f"MOSS Regional LoRA: box {index + 1}: flag '{flag}' is only allowed in the scene prompt."
                )
            tags.append((len(cleaned), name, strength))
        copy = dict(element)
        copy["desc"] = clean
        cleaned.append(copy)
        ids.append(box_id)
    return cleaned, ids, tags


def parse_scene_prompt(prompt):
    """Returns (clean prompt, [(target, name, strength)]) for the scene prompt."""
    clean, tags = parse_tags(prompt)
    out = []
    for name, strength, flag in tags:
        if flag is None:
            out.append((GLOBAL, name, strength))
        elif flag in ("outside", BACKGROUND):
            out.append((BACKGROUND, name, strength))
        else:
            raise ValueError(
                f"MOSS Regional LoRA: unknown flag '{flag}' in scene tag for '{name}' (use 'outside')."
            )
    return clean, out


def resolve_box(ref, ids):
    """Maps a box reference onto a target: box index, GLOBAL or BACKGROUND."""
    text = str(ref).strip().lstrip("@").lower()
    if text in RESERVED_TARGETS or text in ("all", "global"):
        return BACKGROUND if text == BACKGROUND else GLOBAL
    if text in ids:
        return ids.index(text)
    if text.isdigit():
        number = int(text)
        if 1 <= number <= len(ids):
            return number - 1
    named = [f"@{i}" for i in ids if i]
    raise ValueError(
        f"MOSS Regional LoRA: unknown box '{ref}'. Valid: 1..{len(ids)}"
        + (", " + ", ".join(named) if named else "")
        + ", '*' (whole image), 'background' (outside the boxes)."
    )


def closest_names(name, available, n=3):
    lowered = {a.lower(): a for a in available}
    return [lowered[m] for m in difflib.get_close_matches(name.lower(), list(lowered), n=n, cutoff=0.3)]


def merge_specs(tag_specs, node_specs):
    """Merges tag and node assignments; the node input wins for the same target + file.

    Each spec is a dict with at least 'target' and 'lora' (resolved filename).
    """
    taken = {(s["target"], s["lora"]) for s in node_specs}
    merged = [s for s in tag_specs if (s["target"], s["lora"]) not in taken]
    return merged + list(node_specs)


# --- geometry ---------------------------------------------------------------

def box_rect_tokens(bbox, grid_h, grid_w, skirt=0.0):
    """Box on the token grid as (y0, x0, y1, x1) floats, grown by skirt.

    skirt is a fraction of the image's shorter side (in tokens).
    """
    ymin, xmin, ymax, xmax = (float(v) / 1000.0 for v in bbox)
    y0, y1 = sorted((ymin * grid_h, ymax * grid_h))
    x0, x1 = sorted((xmin * grid_w, xmax * grid_w))
    grow = max(0.0, float(skirt)) * min(grid_h, grid_w)
    return (max(0.0, y0 - grow), max(0.0, x0 - grow),
            min(float(grid_h), y1 + grow), min(float(grid_w), x1 + grow))


def _axis_profile(lo, hi, size, feather):
    """Per-token weight along one axis: ramp of width `feather` centred on each edge.

    Always at least one full-weight token (the one holding the centre), so a
    box smaller than a token still gets its LoRA.
    """
    profile = []
    for i in range(size):
        c = i + 0.5
        if feather > 0:
            v = min(c - lo, hi - c) / feather + 0.5
            v = 0.0 if v < 0 else (1.0 if v > 1 else v)
        else:
            v = 1.0 if lo <= c < hi else 0.0
        profile.append(v)
    if hi > lo and size > 0:
        centre = min(size - 1, max(0, int((lo + hi) / 2)))
        profile[centre] = 1.0
    return profile


def box_mask(bbox, grid_h, grid_w, feather=0.0, skirt=0.0):
    """Soft mask of one box as a flat row-major list of grid_h * grid_w floats.

    feather is a fraction of the box's shorter side, capped at 0.3.
    """
    y0, x0, y1, x1 = box_rect_tokens(bbox, grid_h, grid_w, skirt)
    width = max(0.0, min(float(feather), 0.3)) * min(y1 - y0, x1 - x0)
    ys = _axis_profile(y0, y1, grid_h, width)
    xs = _axis_profile(x0, x1, grid_w, width)
    return [a * b for a in ys for b in xs]


def compose_masks(masks):
    """Painter's order: later boxes sit on top of earlier ones.

    masks: list of flat masks in drawing order. Returns (owned masks, background)
    where each owned mask is M_r * prod_{s later}(1 - M_s) and background is
    prod_all(1 - M_s). Per token the owned masks plus background sum to 1.
    """
    if not masks:
        return [], None
    n = len(masks[0])
    remaining = [1.0] * n
    owned = [None] * len(masks)
    for r in range(len(masks) - 1, -1, -1):
        m = masks[r]
        owned[r] = [m[i] * remaining[i] for i in range(n)]
        remaining = [remaining[i] * (1.0 - m[i]) for i in range(n)]
    return owned, remaining


# --- module policy ----------------------------------------------------------

SEQ, IMAGE, TEXT, VEC = "seq", "image", "text", "vec"


def module_kind(path):
    """What part of the MOSS sequence a Linear sees, by its path in the diffusion model.

    seq   - transformer blocks: [image tokens | text tokens | in-sequence refs]
    image - only the image tokens (output head)
    text  - only text tokens (text embedder)
    vec   - cannot be masked: no token axis (timestep / modulation), or
            video_embedder, which also embeds same-sized reference images in
            separate calls that are indistinguishable from the image call
    """
    if path.startswith("layers."):
        return SEQ
    if path.startswith("final_linear_video"):
        return IMAGE
    if path.startswith("text_embedder."):
        return TEXT
    return VEC


def schedule_active(sigma, sigma_start, sigma_end):
    """True if the current sigma lies in (sigma_end, sigma_start]; None bounds are open."""
    if sigma_start is not None and sigma > sigma_start:
        return False
    if sigma_end is not None and sigma <= sigma_end:
        return False
    return True
