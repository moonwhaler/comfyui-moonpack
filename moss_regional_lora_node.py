"""Regional LoRA engine for MOSS-Image: LoRA deltas masked per image token by box.

Used by the MOSS Regional Layout node (`moss_regional_layout_node.py`).

Each targeted Linear gets a forward hook that adds ``mask * strength * h(x)``
(the LoRA bypass path) to the layer output, so outside its box a LoRA
contributes exactly zero. One model pass per step, any number of LoRAs.

Masks are built per diffusion-model call by a DIFFUSION_MODEL wrapper, which
knows the latent grid and the text length. Everything here imports torch and
comfy lazily so the pure logic (`_regional_lora_ops.py`) stays testable.

Why not ComfyUI's BypassInjectionManager: it keeps one adapter per module and
drops LoRA keys that address a slice of a fused weight (MOSS fused q/k/v), so
every attention delta would silently vanish on repacked checkpoints.
"""

import logging
import os

try:
    from . import _regional_lora_ops as ops
    from .moonlora_loader_node import resolve_lora_filename
except ImportError:  # importable for tests without package context
    import _regional_lora_ops as ops
    from moonlora_loader_node import resolve_lora_filename

log = logging.getLogger("MoonPack")

INJECTION_KEY = "moonpack_moss_regional_lora"
PATCH_SIZE = 16  # pixels per MOSS token edge (FLUX.2 latent, already patchified)

_lora_cache = {}  # path -> (mtime, state dict) of the last run's files, like core LoraLoader


def _resolve_lora(name, available):
    """Resolves a tag/helper LoRA name onto a file in the loras folder or raises."""
    found = resolve_lora_filename(name, available)
    if found is None and not os.path.splitext(name)[1]:
        found = resolve_lora_filename(name + ".safetensors", available)
    if found is None:
        stem = os.path.splitext(name.replace("\\", "/").rsplit("/", 1)[-1])[0].lower()
        for candidate in available:
            base = candidate.replace("\\", "/").rsplit("/", 1)[-1]
            if os.path.splitext(base)[0].lower() == stem:
                found = candidate
                break
    if found is None:
        close = ops.closest_names(name, available)
        hint = f" Closest: {', '.join(close)}." if close else ""
        raise ValueError(f"MOSS Regional LoRA: LoRA '{name}' not found in the loras folder.{hint}")
    return found


def _load_many(filenames):
    """Loads several files, keeping all of them in the cache during this run."""
    import comfy.utils
    import folder_paths

    out = {}
    for filename in filenames:
        path = folder_paths.get_full_path_or_raise("loras", filename)
        mtime = os.path.getmtime(path)
        cached = _lora_cache.get(path)
        if cached is None or cached[0] != mtime:
            cached = (mtime, comfy.utils.load_torch_file(path, safe_load=True))
        out[filename] = cached[1]
    _lora_cache.clear()
    for filename, sd in out.items():
        path = folder_paths.get_full_path_or_raise("loras", filename)
        _lora_cache[path] = (os.path.getmtime(path), sd)
    return out


def _split_key(key):
    """Weight key (str or (str, (dim, start, size))) -> (module path in the diffusion model, slice)."""
    offset = None
    if isinstance(key, tuple):
        key, offset = key[0], key[1]
    if not isinstance(key, str) or not key.startswith("diffusion_model.") or not key.endswith(".weight"):
        return None, None
    return key[len("diffusion_model."):-len(".weight")], offset


def _get_module(root, path):
    module = root
    for part in path.split("."):
        module = module[int(part)] if part.isdigit() else getattr(module, part)
    return module


class _Group:
    """One adapter on one module (optionally on a slice of its output), used by several entries."""

    __slots__ = ("adapter", "offset", "entries", "kind")

    def __init__(self, adapter, offset, kind):
        self.adapter = adapter
        self.offset = offset
        self.entries = []  # entry indices
        self.kind = kind


class _CallContext:
    __slots__ = ("grid", "text_len", "active", "device", "dtype", "cache", "cond_rows", "batch", "spans_valid")

    def __init__(self, grid, text_len, active, device, dtype, cond_rows=None, batch=1, spans_valid=False):
        self.grid = grid
        self.text_len = text_len
        self.active = active
        self.device = device
        self.dtype = dtype
        self.cache = {}
        self.cond_rows = cond_rows    # batch rows that are positive conditioning (None = unknown)
        self.batch = batch
        self.spans_valid = spans_valid  # the call's text is the tokenized layout prompt


TEXT_MASKED, TEXT_GLOBAL, TEXT_OWN = "masked", "global", "own caption"


def _cond_rows(transformer_options, batch):
    """Batch rows of positive conditioning, from cond_or_uncond (0 = cond)."""
    kinds = transformer_options.get("cond_or_uncond")
    if not kinds or batch % len(kinds):
        return None
    per = batch // len(kinds)
    return [c * per + j for c, k in enumerate(kinds) if k == 0 for j in range(per)]


class RegionalLoraManager:
    """Owns the hooks, the per-call mask context and the schedule of one node output."""

    def __init__(self, boxes, entries, feather, skirt, text_mode, ownership=None):
        self.boxes = boxes            # {box index: bbox} for boxes that carry a LoRA; index 0 = front-most
        self.entries = entries        # dicts: target, strength, start, end, lora
        self.feather = feather
        self.skirt = skirt
        self.text_mode = text_mode    # TEXT_MASKED | TEXT_GLOBAL | TEXT_OWN
        # attention ownership: {"spans": {box: (t0, t1)}, "n_tokens": int, "measure_until": f, "spill": f}
        self.ownership = ownership
        self.attention = bool(ownership and ownership.get("attention"))  # measure, then decide ownership
        self.spans = (ownership or {}).get("spans") or {}
        self.n_tokens = (ownership or {}).get("n_tokens")
        self.measure_sigma = None     # measure while sigma > this (set in on_pre_run)
        self.scores = None            # {box: (H*W,) float32 tensor} accumulated attention mass
        self.score_grid = None
        self.owned_ready = False
        self._warned = set()
        self.modules = {}             # module path -> [ _Group ]
        self.handles = []
        self.forced = {}              # module -> previous comfy_force_forward
        self.moved = []               # (adapter, original weights)
        self.ctx = None
        self.sigma_bounds = [(None, None)] * len(entries)
        self._mask_cache = {}         # (H, W, device, dtype) -> {target: flat image mask tensor}

    # --- building -------------------------------------------------------
    def add(self, path, offset, adapter, entry_index):
        groups = self.modules.setdefault(path, [])
        for g in groups:
            if g.adapter is adapter and g.offset == offset:
                g.entries.append(entry_index)
                return
        g = _Group(adapter, offset, ops.module_kind(path))
        g.entries.append(entry_index)
        groups.append(g)

    # --- schedule -------------------------------------------------------
    def on_pre_run(self, patcher):
        try:
            sampling = patcher.get_model_object("model_sampling")
        except Exception:
            sampling = None
        bounds = []
        for e in self.entries:
            if sampling is None or (e["start"] <= 0.0 and e["end"] >= 1.0):
                bounds.append((None, None))
                continue
            start = None if e["start"] <= 0.0 else float(sampling.percent_to_sigma(e["start"]))
            end = None if e["end"] >= 1.0 else float(sampling.percent_to_sigma(e["end"]))
            bounds.append((start, end))
        self.sigma_bounds = bounds
        # every sampling run measures afresh
        self.scores, self.score_grid, self.owned_ready = None, None, False
        self._mask_cache.clear()
        if self.attention and self.spans:
            until = float(self.ownership.get("measure_until", 0.3))
            self.measure_sigma = float(sampling.percent_to_sigma(until)) if sampling is not None else None

    def _warn_once(self, key, msg, *args):
        if key not in self._warned:
            self._warned.add(key)
            log.warning(msg, *args)

    # --- masks ----------------------------------------------------------
    def image_masks(self, grid_h, grid_w, device, dtype):
        """{target: (H*W,) tensor} for every regional target, cached per latent size."""
        import torch

        key = (grid_h, grid_w, str(device), dtype)
        cached = self._mask_cache.get(key)
        if cached is not None:
            return cached
        if self.owned_ready and self.score_grid == (grid_h, grid_w):
            owned_d, background = self._ownership_lists(grid_h, grid_w)
            masks = {i: torch.tensor(m, device=device, dtype=dtype) for i, m in owned_d.items()}
            masks[ops.BACKGROUND] = torch.tensor(background, device=device, dtype=dtype)
        else:
            order = sorted(self.boxes, reverse=True)  # box 0 is front-most: compose back to front
            raw = [ops.box_mask(self.boxes[i], grid_h, grid_w, self.feather, self.skirt) for i in order]
            owned, background = ops.compose_masks(raw)
            masks = {i: torch.tensor(m, device=device, dtype=dtype) for i, m in zip(order, owned)}
            masks[ops.BACKGROUND] = (torch.tensor(background, device=device, dtype=dtype) if background is not None
                                     else torch.ones(grid_h * grid_w, device=device, dtype=dtype))
        if len(self._mask_cache) > 4:
            self._mask_cache.clear()
        self._mask_cache[key] = masks
        return masks

    def _target_weight(self, target, kind, length):
        """Mask of one target for a module call: float or (1, length, 1) tensor."""
        if target == ops.GLOBAL:
            return 1.0
        ctx = self.ctx
        if ctx is None or kind == ops.VEC:
            return 0.0
        text_value = 1.0 if self.text_mode == TEXT_GLOBAL else 0.0
        if kind == ops.TEXT:
            return text_value
        grid_h, grid_w = ctx.grid
        hw = grid_h * grid_w
        if kind == ops.IMAGE:
            if length != hw:
                return 0.0
            return self.image_masks(grid_h, grid_w, ctx.device, ctx.dtype)[target].view(1, hw, 1)
        # SEQ: [image | text | in-sequence refs]
        if length < hw:  # a refs-only pass (preprocess_refs inside the call)
            return 0.0
        import torch

        image = self.image_masks(grid_h, grid_w, ctx.device, ctx.dtype)[target]
        text = min(ctx.text_len, length - hw)
        parts = [image]
        if text > 0:
            parts.append(torch.full((text,), text_value, device=ctx.device, dtype=ctx.dtype))
        if length - hw - text > 0:
            parts.append(torch.zeros(length - hw - text, device=ctx.device, dtype=ctx.dtype))
        mask = torch.cat(parts).view(1, length, 1)
        span = self.spans.get(target) if isinstance(target, int) else None
        if self.text_mode == TEXT_OWN and span is not None and ctx.spans_valid and ctx.cond_rows:
            # own caption: the box's caption tokens, in positive-conditioning rows only
            mask = mask.expand(ctx.batch, length, 1).clone()
            t0, t1 = span
            rows = torch.tensor(ctx.cond_rows, device=ctx.device)
            mask[rows, hw + t0:hw + min(t1, text)] = 1.0
        return mask

    def weight_for(self, group, length):
        """Sum of strength * mask over the group's active entries (float or tensor)."""
        ctx = self.ctx
        active = [i for i in group.entries if ctx is None or i in ctx.active]
        if not active:
            return 0.0
        cache_key = (tuple(active), group.kind, length)
        if ctx is not None and cache_key in ctx.cache:
            return ctx.cache[cache_key]
        total = 0.0
        for i in active:
            e = self.entries[i]
            w = self._target_weight(e["target"], group.kind, length)
            if isinstance(w, float):
                if w != 0.0:
                    total = total + e["strength"] * w
            else:
                total = total + e["strength"] * w
        if ctx is not None:
            ctx.cache[cache_key] = total
        return total

    # --- hooks ----------------------------------------------------------
    def _make_hook(self, groups):
        def hook(module, args, output):
            if not args:
                return output
            x = args[0]
            length = x.shape[1] if x.dim() == 3 else -1
            for g in groups:
                w = self.weight_for(g, length)
                if isinstance(w, float) and w == 0.0:
                    continue
                if g.offset is None:
                    base = output
                else:
                    dim, start, size = g.offset
                    base = output.narrow(-1, start, size)  # weight dim 0 == output features
                delta = g.adapter.h(x, base) * w
                base.add_(delta.to(base.dtype))
            return output
        return hook

    def inject(self, patcher):
        if self.handles:
            return  # already injected; never stack a second delta
        import torch
        import comfy.model_management

        root = patcher.model.diffusion_model
        device = comfy.model_management.get_torch_device()
        try:
            dtype = patcher.model.get_dtype_inference()
        except Exception:
            dtype = None
        if dtype not in (torch.float32, torch.float16, torch.bfloat16):
            dtype = None
        seen = set()
        for path, groups in self.modules.items():
            module = _get_module(root, path)
            for g in groups:
                if id(g.adapter) in seen:
                    continue
                seen.add(id(g.adapter))
                original = g.adapter.weights
                self.moved.append((g.adapter, original))
                g.adapter.weights = type(original)(
                    w.to(device=device, dtype=dtype) if isinstance(w, torch.Tensor) and dtype is not None
                    else (w.to(device=device) if isinstance(w, torch.Tensor) else w)
                    for w in original
                )
            self.forced[module] = getattr(module, "comfy_force_forward", False)
            module.comfy_force_forward = True  # fused/quantized fast paths skip the module call otherwise
            self.handles.append(module.register_forward_hook(self._make_hook(groups)))

    def eject(self, patcher):
        for handle in self.handles:
            handle.remove()
        self.handles = []
        for module, previous in self.forced.items():
            module.comfy_force_forward = previous
        self.forced = {}
        for adapter, original in self.moved:
            adapter.weights = original
        self.moved = []
        self._mask_cache.clear()

    # --- per-call context -----------------------------------------------
    def diffusion_wrapper(self, executor, x, timestep, context, transformer_options, **kwargs):
        sigmas = transformer_options.get("sigmas")
        sigma = float(sigmas.max()) if sigmas is not None else None
        active = set()
        for i, (start, end) in enumerate(self.sigma_bounds):
            if sigma is None or ops.schedule_active(sigma, start, end):
                active.add(i)
        text_len = context.shape[1] if context is not None and context.dim() >= 2 else 0
        cond_rows = _cond_rows(transformer_options, x.shape[0])
        spans_valid = bool(self.spans) and self.n_tokens == text_len
        if self.spans and cond_rows and not spans_valid:
            self._warn_once("len", "MOSS Regional Layout: the positive prompt has %d tokens, expected %d; "
                            "the prompt was changed after this node, so attention ownership and 'own caption' "
                            "fall back to the box masks.", text_len, self.n_tokens)
        grid = tuple(x.shape[-2:])
        measuring = (self.attention and spans_valid and bool(cond_rows) and sigma is not None
                     and self.measure_sigma is not None and sigma > self.measure_sigma)
        if (self.attention and not measuring and not self.owned_ready and self.scores is not None
                and sigma is not None and self.measure_sigma is not None and sigma <= self.measure_sigma):
            self._finish_measurement()
        self.ctx = _CallContext(grid, text_len, active, x.device, x.dtype, cond_rows, x.shape[0], spans_valid)
        try:
            if any(self.entries[i]["target"] != ops.GLOBAL for i in active):
                # built before the blocks run, outside the memory-compiler region
                self.image_masks(x.shape[-2], x.shape[-1], x.device, x.dtype)
            if measuring:
                transformer_options = {**transformer_options,
                                       "optimized_attention_override": self._make_override(
                                           transformer_options.get("optimized_attention_override"), grid, text_len, cond_rows)}
            return executor(x, timestep, context, transformer_options, **kwargs)
        finally:
            self.ctx = None

    # --- attention measurement ------------------------------------------
    def _make_override(self, previous, grid, text_len, cond_rows):
        """Attention override that records image->caption attention, then runs attention unchanged."""
        def override(func, *args, **kwargs):
            to = kwargs.get("transformer_options") or {}
            block = to.get("block_index")
            if block is not None and block in self._measure_blocks(to):
                try:
                    self._accumulate(args[0], args[1], args[3], grid, text_len, cond_rows)
                except Exception as e:  # measurement must never break sampling
                    self._warn_once("measure", "MOSS Regional Layout: attention measurement failed (%s); "
                                    "using the box masks.", e)
                    self.attention = False
            if previous is not None:
                return previous(func, *args, **kwargs)
            return func(*args, **kwargs)
        return override

    def _measure_blocks(self, to):
        n = to.get("total_blocks") or 42
        cached = getattr(self, "_blocks_cache", None)
        if cached is None or cached[0] != n:
            self._blocks_cache = (n, set(ops.measured_layers(n)))
        return self._blocks_cache[1]

    def _accumulate(self, q, k, heads, grid, text_len, cond_rows, chunk=1024):
        import torch

        hw = grid[0] * grid[1]
        rows = torch.tensor(cond_rows, device=q.device)
        dh = q.shape[-1] // heads
        qi = q.index_select(0, rows)[:, :hw].reshape(len(cond_rows), hw, heads, dh).transpose(1, 2)
        kt = k.index_select(0, rows)[:, hw:hw + text_len].reshape(len(cond_rows), text_len, heads, dh).transpose(1, 2)
        if self.scores is None or self.score_grid != grid:
            self.scores = {b: torch.zeros(hw, device=q.device, dtype=torch.float32) for b in self.spans}
            self.score_grid = grid
        scale = dh ** -0.5
        with torch.no_grad():
            for s0 in range(0, hw, chunk):
                logits = torch.matmul(qi[:, :, s0:s0 + chunk].float(), kt.float().transpose(-1, -2)) * scale
                probs = logits.softmax(-1)  # over the text tokens: which part of the prompt each image token reads
                for b, (t0, t1) in self.spans.items():
                    self.scores[b][s0:s0 + chunk] += probs[..., t0:t1].sum(-1).mean(dim=(0, 1))

    def _finish_measurement(self):
        self.owned_ready = True
        self._mask_cache.clear()
        gh, gw = self.score_grid
        owned, _ = self._ownership_lists(gh, gw)
        geo = {b: ops.box_mask(self.boxes[b], gh, gw, self.feather, self.skirt) for b in owned}
        parts = []
        for b in sorted(owned):
            moved = sum(1 for i in range(gh * gw) if owned[b][i] > 0.5 and geo[b][i] <= 0.5)
            lost = sum(1 for i in range(gh * gw) if owned[b][i] <= 0.5 and geo[b][i] > 0.5)
            parts.append(f"box {b + 1}: +{moved}/-{lost} tokens")
        log.info("MOSS Regional Layout: attention ownership vs. the drawn boxes: %s", ", ".join(parts))

    def _ownership_lists(self, gh, gw):
        cached = getattr(self, "_own_cache", None)
        if cached is not None and cached[0] == (gh, gw, id(self.scores)):
            return cached[1]
        spill = float(self.ownership.get("spill", 0.1)) if self.ownership else 0.1
        boxes = [b for b in self.boxes if b in self.scores]
        geo = {b: ops.box_mask(self.boxes[b], gh, gw, self.feather, self.skirt) for b in boxes}
        reach = {b: [1.0 if v > 0 else 0.0 for v in ops.box_mask(self.boxes[b], gh, gw, 0.0, self.skirt + spill)]
                 for b in boxes}
        scores = {b: self.scores[b].tolist() for b in boxes}
        owned, background = ops.ownership_masks(geo, reach, scores, gh, gw)
        # boxes with a LoRA but no caption span keep their geometric mask (painter's order below them)
        for b in self.boxes:
            if b not in owned:
                m = ops.box_mask(self.boxes[b], gh, gw, self.feather, self.skirt)
                owned[b] = [m[i] * background[i] for i in range(gh * gw)]
                background = [background[i] - owned[b][i] for i in range(gh * gw)]
        self._own_cache = ((gh, gw, id(self.scores)), (owned, background))
        return owned, background


ADDITIVE_ADAPTERS = ("LoRAAdapter", "LoHaAdapter", "LoKrAdapter")


def _set_adapter_shape(adapter, module, offset):
    """What BypassForwardHook sets, with the slice width for fused q/k/v."""
    adapter.multiplier = 1.0
    adapter.is_conv = False
    adapter.conv_dim = 0
    adapter.kernel_size = (1,)
    adapter.kw_dict = {}
    adapter.in_channels = getattr(module, "in_features", None)
    adapter.out_channels = offset[2] if offset is not None else getattr(module, "out_features", None)


def apply_regional_loras(model, boxes, entries, feather, skirt, text_mode, ownership=None):
    """Returns a patched clone of `model`. entries: dicts with target/lora/strength/start/end."""
    import comfy.lora
    import comfy.lora_convert
    import comfy.model_base
    import comfy.patcher_extension
    import comfy.weight_adapter

    if not isinstance(model.model, comfy.model_base.MOSSImage):
        raise ValueError(
            f"MOSS Regional Layout only works with MOSS-Image models, got {type(model.model).__name__}."
        )
    if model.get_injections(INJECTION_KEY) is not None:
        raise ValueError(
            "MOSS Regional LoRA: this model already went through a MOSS Regional Layout node. "
            "Put all regional LoRAs into one node."
        )

    clone = model.clone()
    entries = [e for e in entries if e["strength"] != 0.0]
    if not entries:
        return clone

    used_boxes = {e["target"] for e in entries if isinstance(e["target"], int)}
    if isinstance(text_mode, bool):  # older callers
        text_mode = TEXT_GLOBAL if text_mode else TEXT_MASKED
    if ownership is not None:
        ownership = {**ownership, "spans": {b: s for b, s in (ownership.get("spans") or {}).items() if b in used_boxes}}
    manager = RegionalLoraManager({i: boxes[i] for i in sorted(used_boxes)}, entries, feather, skirt, text_mode, ownership)

    key_map = comfy.lora.model_lora_keys_unet(model.model, {})
    root = model.model.diffusion_model
    files = _load_many(sorted({e["lora"] for e in entries}))
    loaded_per_file = {
        name: comfy.lora.load_lora(comfy.lora_convert.convert_lora(sd), key_map) for name, sd in files.items()
    }

    hooked = 0
    for index, e in enumerate(entries):
        loaded = loaded_per_file[e["lora"]]
        regional = e["target"] != ops.GLOBAL
        skipped, missing, dora = 0, 0, False
        global_patches = {}
        for key, patch in loaded.items():
            is_adapter = isinstance(patch, comfy.weight_adapter.WeightAdapterBase)
            if not is_adapter or type(patch).__name__ not in ADDITIVE_ADAPTERS:
                # diff/bias/set patches and OFT-like adapters cannot be masked per token
                if regional:
                    skipped += 1
                else:
                    global_patches[key] = patch
                continue
            path, offset = _split_key(key)
            try:
                module = _get_module(root, path) if path else None
            except (AttributeError, IndexError, KeyError, TypeError):
                module = None
            if module is None or not hasattr(module, "weight"):
                missing += 1
                continue
            if offset is not None and offset[0] != 0:
                missing += 1
                continue
            if type(patch).__name__ == "LoRAAdapter" and patch.weights[4] is not None:
                dora = True
            _set_adapter_shape(patch, module, offset)
            manager.add(path, offset, patch, index)
            hooked += 1
        if global_patches:
            if e["start"] > 0.0 or e["end"] < 1.0:
                log.warning("MOSS Regional LoRA: %s: %d weight patches are applied unscheduled.",
                            e["lora"], len(global_patches))
            clone.add_patches(global_patches, e["strength"])
        if skipped:
            log.warning("MOSS Regional LoRA: %s: %d non-LoRA patches (bias/diff/OFT) cannot be masked "
                        "and are skipped for box %s.", e["lora"], skipped, e["target"])
        if missing:
            log.warning("MOSS Regional LoRA: %s: %d adapters target modules the model does not have.",
                        e["lora"], missing)
        if dora:
            log.warning("MOSS Regional LoRA: %s is a DoRA; the magnitude part is ignored in bypass mode.",
                        e["lora"])

    if hooked == 0:
        log.warning("MOSS Regional LoRA: no LoRA layer matched the model; output is unchanged.")
        return clone

    clone.set_injections(INJECTION_KEY, [comfy.patcher_extension.PatcherInjection(
        inject=manager.inject, eject=manager.eject)])
    clone.add_wrapper_with_key(comfy.patcher_extension.WrappersMP.DIFFUSION_MODEL, INJECTION_KEY,
                               manager.diffusion_wrapper)
    clone.add_callback_with_key(comfy.patcher_extension.CallbacksMP.ON_PRE_RUN, INJECTION_KEY,
                                manager.on_pre_run)
    log.info("MOSS Regional LoRA: %d LoRA assignments over %d layers.", len(entries), len(manager.modules))
    return clone


def preview_masks(boxes, entries, feather, skirt, width, height):
    """MASK batch: one per LoRA box (box-number order), then the background if used."""
    import torch

    grid_h, grid_w = max(1, round(height / PATCH_SIZE)), max(1, round(width / PATCH_SIZE))
    used = sorted({e["target"] for e in entries if isinstance(e["target"], int)}, reverse=True)
    raw = [ops.box_mask(boxes[i], grid_h, grid_w, feather, skirt) for i in used]
    owned, background = ops.compose_masks(raw)  # back to front: box 0 is front-most
    masks = list(reversed(owned))  # output in box-number order
    if any(e["target"] == ops.BACKGROUND for e in entries):
        masks.append(background if background is not None else [1.0] * (grid_h * grid_w))
    if not masks:
        return torch.zeros((1, height, width))
    t = torch.tensor(masks, dtype=torch.float32).view(-1, 1, grid_h, grid_w)
    t = torch.nn.functional.interpolate(t, size=(height, width), mode="nearest")
    return t[:, 0]
