"""HTTP routes backing the Prompt Library node's dropdown and save/update/delete buttons.

Import-guarded: outside a running ComfyUI (tests, linting) this module is a
no-op instead of an ImportError.
"""

import logging

from . import prompt_library_store as store

log = logging.getLogger("MoonPack")


def _register():
    from aiohttp import web
    from server import PromptServer

    routes = PromptServer.instance.routes

    @routes.get("/moonpack/prompt_library")
    async def moonpack_list_prompts(_request):
        return web.json_response({"entries": store.load_library()})

    @routes.post("/moonpack/prompt_library")
    async def moonpack_add_prompt(request):
        body = await request.json()
        name = str(body.get("name", "")).strip()
        if not name:
            return web.json_response({"error": "Name is required."}, status=400)
        try:
            entries = store.add_entry(
                name, str(body.get("description", "")), str(body.get("tags", "")),
                str(body.get("text", "")),
            )
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response({"entries": entries})

    @routes.put("/moonpack/prompt_library/{name}")
    async def moonpack_update_prompt(request):
        body = await request.json()
        try:
            entries = store.update_entry(
                request.match_info["name"], str(body.get("description", "")),
                str(body.get("tags", "")), str(body.get("text", "")),
            )
        except KeyError as exc:
            return web.json_response({"error": str(exc)}, status=404)
        return web.json_response({"entries": entries})

    @routes.delete("/moonpack/prompt_library/{name}")
    async def moonpack_delete_prompt(request):
        try:
            entries = store.delete_entry(request.match_info["name"])
        except KeyError as exc:
            return web.json_response({"error": str(exc)}, status=404)
        return web.json_response({"entries": entries})

    return True


try:
    REGISTERED = _register()
except Exception:  # noqa: BLE001 - a broken route must not stop node loading
    REGISTERED = False
    log.warning("MoonPack: could not register HTTP routes; the Prompt Library "
                "node's dropdown/save buttons will not work.", exc_info=True)
