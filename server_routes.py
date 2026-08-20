"""Local HTTP routes used by MoonPack's frontend widgets.

Import-guarded: outside a running ComfyUI (tests, linting) this module is a
no-op instead of an ImportError.
"""

import io
import logging

from ._label_ops import apply_crop, compose_labeled_image

log = logging.getLogger("MoonPack")


def _register():
    from aiohttp import web
    from server import PromptServer

    routes = PromptServer.instance.routes

    @routes.get("/moonpack/loras")
    async def moonpack_list_loras(_request):
        """Returns every lora file ComfyUI knows about, as relative paths."""
        import folder_paths
        return web.json_response({"loras": list(folder_paths.get_filename_list("loras"))})

    @routes.post("/moonpack/label_preview")
    async def moonpack_label_preview(request):
        """Composites Load Image (Labeled)'s current widget values (crop
        included) onto its selected file, so the node's Preview button shows
        an exact, instant match for what execution will actually output."""
        import folder_paths
        from PIL import Image, ImageOps

        try:
            data = await request.json()
            image_path = folder_paths.get_annotated_filepath(str(data.get("image", "")))
            img = Image.open(image_path)
            img = ImageOps.exif_transpose(img).convert("RGB")
            img = apply_crop(
                img,
                int(data.get("crop_x", 0) or 0),
                int(data.get("crop_y", 0) or 0),
                int(data.get("crop_width", 0) or 0),
                int(data.get("crop_height", 0) or 0),
            )

            composed = compose_labeled_image(
                img,
                data.get("text", ""),
                data.get("text_position", "top"),
                bool(data.get("show_label", True)),
                bool(data.get("show_arrow", True)),
                data.get("background_color", "#000000"),
                data.get("text_color", "#ffffff"),
                int(data.get("border_width", 0) or 0),
            )

            buf = io.BytesIO()
            composed.save(buf, format="PNG")
            return web.Response(body=buf.getvalue(), content_type="image/png")
        except Exception as e:  # noqa: BLE001 - report to the widget instead of a 500
            log.warning("MoonPack: label preview failed", exc_info=True)
            return web.json_response({"error": str(e)}, status=400)

    @routes.post("/moonpack/crop_source")
    async def moonpack_crop_source(request):
        """Returns the selected file's raw, EXIF-corrected RGB pixels (no crop,
        no label bar) for the node's Edit Crop popup, so the region the user
        drags there lines up 1:1 with what apply_crop will actually cut."""
        import folder_paths
        from PIL import Image, ImageOps

        try:
            data = await request.json()
            image_path = folder_paths.get_annotated_filepath(str(data.get("image", "")))
            img = Image.open(image_path)
            img = ImageOps.exif_transpose(img).convert("RGB")

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return web.Response(body=buf.getvalue(), content_type="image/png")
        except Exception as e:  # noqa: BLE001 - report to the widget instead of a 500
            log.warning("MoonPack: crop source fetch failed", exc_info=True)
            return web.json_response({"error": str(e)}, status=400)

    return True


try:
    REGISTERED = _register()
except Exception:  # noqa: BLE001 - a broken route must not stop node loading
    REGISTERED = False
    log.warning("MoonPack: could not register HTTP routes; the MoonLoRA Loader "
                "picker will be empty.", exc_info=True)
