"""Pure JSON-backed CRUD for the Prompt Library node's saved entries.

Kept import-free of ComfyUI (except folder_paths, imported lazily inside
_library_path) so the CRUD logic is testable without a running server.
"""

import json
import logging
import os

log = logging.getLogger("MoonPack")

LIBRARY_FILENAME = "moonpack_prompt_library.json"


def _library_path() -> str:
    import folder_paths
    return os.path.join(folder_paths.get_user_directory(), LIBRARY_FILENAME)


def load_library() -> list:
    """Returns every saved entry, or [] if the file is missing or unreadable."""
    path = _library_path()
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        log.warning("MoonPack Prompt Library: could not read %s; treating as empty.", path)
        return []
    entries = data.get("entries") if isinstance(data, dict) else None
    return entries if isinstance(entries, list) else []


def save_library(entries: list) -> None:
    path = _library_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"entries": entries}, handle, indent=2, ensure_ascii=False)


def find_entry(entries: list, name: str):
    for entry in entries:
        if entry.get("name") == name:
            return entry
    return None


def add_entry(name: str, text: str) -> list:
    """Appends a new entry. Raises ValueError if the name is already taken."""
    entries = load_library()
    if find_entry(entries, name) is not None:
        raise ValueError(f"An entry named '{name}' already exists.")
    entries.append({"name": name, "text": text})
    save_library(entries)
    return entries


def update_entry(name: str, text: str) -> list:
    """Updates an existing entry's text. Raises KeyError if the name doesn't exist."""
    entries = load_library()
    entry = find_entry(entries, name)
    if entry is None:
        raise KeyError(f"No entry named '{name}' exists.")
    entry["text"] = text
    save_library(entries)
    return entries


def delete_entry(name: str) -> list:
    """Removes an entry by name. Raises KeyError if no entry with that name exists."""
    entries = load_library()
    if find_entry(entries, name) is None:
        raise KeyError(f"No entry named '{name}' exists.")
    entries = [entry for entry in entries if entry.get("name") != name]
    save_library(entries)
    return entries
