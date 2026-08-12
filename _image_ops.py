import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image as PILImage

FILL_PRESETS = {
    "black": (0.0, 0.0, 0.0),
    "white": (1.0, 1.0, 1.0),
    "gray": (0.5, 0.5, 0.5),
}

TORCH_MODES = ("nearest", "bilinear", "bicubic")


def resize(img, height, width, mode="bicubic"):
    # img: [1, H, W, C] -> resize to [1, height, width, C]
    _, h, w, c = img.shape
    if h == height and w == width:
        return img.clamp(0.0, 1.0)
    if mode == "lanczos" and c == 3:
        return resize_lanczos(img, height, width)
    torch_mode = mode if mode in TORCH_MODES else "bicubic"
    t = img.permute(0, 3, 1, 2)
    kwargs = {} if torch_mode == "nearest" else {"align_corners": False}
    t = F.interpolate(t, size=(height, width), mode=torch_mode, **kwargs)
    return t.clamp(0.0, 1.0).permute(0, 2, 3, 1)


def resize_lanczos(img, height, width):
    arr = (img[0].clamp(0.0, 1.0).cpu().numpy() * 255.0).round().astype(np.uint8)
    resized = PILImage.fromarray(arr, mode="RGB").resize((width, height), PILImage.LANCZOS)
    out = torch.from_numpy(np.array(resized)).to(dtype=img.dtype) / 255.0
    return out.unsqueeze(0).to(img.device)


def cover_fit(img, height, width, mode="bicubic"):
    # Scale img to cover a height x width cell, then center-crop the overflow.
    _, h, w, _ = img.shape
    scale = max(height / h, width / w)
    resized = resize(img, max(1, round(h * scale)), max(1, round(w * scale)), mode)
    _, rh, rw, _ = resized.shape
    top = (rh - height) // 2
    left = (rw - width) // 2
    return resized[:, top:top + height, left:left + width, :]


def contain_fit(img, height, width, mode, fill_rgb):
    """Scales img to fit inside a height x width cell without cropping, pads the
    leftover with fill_rgb. Returns (tile, top, left, content_h, content_w) so the
    caller can mark only the real image pixels (not the padding) in a mask."""
    _, h, w, c = img.shape
    scale = min(height / h, width / w)
    content_h = max(1, min(height, round(h * scale)))
    content_w = max(1, min(width, round(w * scale)))
    content = resize(img, content_h, content_w, mode)
    top = (height - content_h) // 2
    left = (width - content_w) // 2
    tile = fill_rgb.view(1, 1, 1, c).expand(1, height, width, c).clone()
    tile[:, top:top + content_h, left:left + content_w, :] = content
    return tile, top, left, content_h, content_w


def match_channels(img, channels):
    c = img.shape[-1]
    if c == channels:
        return img
    return img[..., :channels] if c > channels else F.pad(img, (0, channels - c))


def normalize_refs(raw, max_side, mode):
    """Flattens whatever arrives for reference_images (a native list of per-image tensors from
    Image List, or a single legacy stacked-batch tensor) into a flat list of [1,H,W,C] tensors,
    each keeping its native resolution (unless it exceeds max_side, in which case it's scaled
    down, never up, so one huge outlier can't blow up the grid/strip size)."""
    flat = []
    if raw is None:
        return flat
    for item in raw:
        if item is None:
            continue
        for i in range(item.shape[0]):
            img = item[i:i + 1]
            if max_side > 0:
                _, h, w, _ = img.shape
                longest = max(h, w)
                if longest > max_side:
                    scale = max_side / longest
                    img = resize(img, max(1, round(h * scale)), max(1, round(w * scale)), mode)
            flat.append(img)
    return flat
