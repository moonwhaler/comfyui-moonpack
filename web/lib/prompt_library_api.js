/**
 * Fetch/cache and CRUD calls for the Prompt Library node, backed by
 * MoonPack's /moonpack/prompt_library routes.
 */

import { api } from "../../../scripts/api.js";

let cache = null;
let inflight = null;

/** Returns every saved entry ({name, text}), cached for the session. */
export function fetchPromptEntries(force = false) {
    if (force) {
        cache = null;
        inflight = null;
    }
    if (cache) return Promise.resolve(cache);
    if (!inflight) {
        inflight = api
            .fetchApi("/moonpack/prompt_library")
            .then((response) => response.json())
            .then((data) => {
                cache = Array.isArray(data?.entries) ? data.entries : [];
                return cache;
            })
            .catch((error) => {
                console.error("[MoonPack] could not load the prompt library:", error);
                inflight = null;
                return [];
            });
    }
    return inflight;
}

export function clearPromptCache() {
    cache = null;
    inflight = null;
}

async function request(method, path, body) {
    const response = await api.fetchApi(path, {
        method,
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(data?.error || `Request failed (${response.status}).`);
    }
    clearPromptCache();
    return data.entries;
}

export const createPromptEntry = (entry) => request("POST", "/moonpack/prompt_library", entry);
export const updatePromptEntry = (name, entry) =>
    request("PUT", `/moonpack/prompt_library/${encodeURIComponent(name)}`, entry);
export const deletePromptEntry = (name) =>
    request("DELETE", `/moonpack/prompt_library/${encodeURIComponent(name)}`);
