"""Pure logic for regional LoRAs on MOSS-Image: token masks and module policy.

Deliberately free of torch and comfy so it can be unit tested on its own. The
node module (`moss_regional_lora_node.py`) turns the plain-list masks built
here into tensors once per latent size.

Boxes are [ymin, xmin, ymax, xmax] on a 0-1000 grid. Targets: an int box index,
``GLOBAL`` (whole image, like a normal LoRA) or ``BACKGROUND`` (outside every
LoRA box).
"""

import difflib

GLOBAL = "*"
BACKGROUND = "background"


def closest_names(name, available, n=3):
    lowered = {a.lower(): a for a in available}
    return [lowered[m] for m in difflib.get_close_matches(name.lower(), list(lowered), n=n, cutoff=0.3)]


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


# --- attention ownership ----------------------------------------------------

def measured_layers(n_blocks):
    """Blocks whose attention is measured: the middle third, every second block."""
    lo, hi = n_blocks // 3, (2 * n_blocks) // 3
    return list(range(lo, hi, 2)) or list(range(n_blocks))


def _median(values):
    vals = sorted(values)
    if not vals:
        return 0.0
    mid = len(vals) // 2
    return vals[mid] if len(vals) % 2 else 0.5 * (vals[mid - 1] + vals[mid])


def ownership_masks(geo, reach, scores, grid_h, grid_w, ring_min=0.5):
    """Exclusive LoRA masks where the model, not the drawing, decides contested tokens.

    geo:    {box: flat geometric mask (feather/skirt applied)}
    reach:  {box: flat 0/1 mask of the box grown by `spill`} (contains the box)
    scores: {box: flat attention mass of the image tokens to the box's caption}

    A token inside exactly one reach region, and inside that box, keeps the
    geometric value. Every other token in some reach region is contested: the
    box whose caption it attends to most (relative to that box's own median
    inside the box) takes it, weighted by clamp(score, 0, 1). In the ring
    outside its box a LoRA needs a score >= ring_min. Contested values are
    softened with a 3x3 mean. Returns ({box: mask}, background).
    """
    n = grid_h * grid_w
    boxes = list(geo)
    norm = {}
    for r in boxes:
        inside = [scores[r][i] for i in range(n) if geo[r][i] > 0.5]
        med = _median(inside)
        norm[r] = [v / med for v in scores[r]] if med > 0 else [0.0] * n
    owned = {r: [0.0] * n for r in boxes}
    contested = [False] * n
    for i in range(n):
        cands = [r for r in boxes if reach[r][i] > 0]
        if not cands:
            continue
        if len(cands) == 1 and geo[cands[0]][i] > 0:
            owned[cands[0]][i] = geo[cands[0]][i]
            continue
        contested[i] = True
        best = max(cands, key=lambda r: norm[r][i])
        s = norm[best][i]
        if geo[best][i] <= 0 and s < ring_min:
            continue
        owned[best][i] = max(0.0, min(1.0, s))
    smoothed = {r: list(m) for r, m in owned.items()}
    for i in range(n):
        if not contested[i]:
            continue
        y, x = divmod(i, grid_w)
        cells = [(yy * grid_w + xx) for yy in range(max(0, y - 1), min(grid_h, y + 2))
                 for xx in range(max(0, x - 1), min(grid_w, x + 2))]
        for r in boxes:
            smoothed[r][i] = sum(owned[r][c] for c in cells) / len(cells)
    background = [max(0.0, 1.0 - sum(smoothed[r][i] for r in boxes)) for i in range(n)]
    return smoothed, background
