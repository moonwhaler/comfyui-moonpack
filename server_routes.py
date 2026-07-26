"""Local HTTP routes used by MoonPack's frontend widgets.

Import-guarded: outside a running ComfyUI (tests, linting) this module is a
no-op instead of an ImportError.
"""

import logging

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

    return True


try:
    REGISTERED = _register()
except Exception:  # noqa: BLE001 - a broken route must not stop node loading
    REGISTERED = False
    log.warning("MoonPack: could not register HTTP routes; the MoonLoRA Loader "
                "picker will be empty.", exc_info=True)
