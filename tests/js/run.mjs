/**
 * Headless checks for the MoonLoRA Loader frontend widgets.
 *
 *   node tests/js/run.mjs
 *
 * The widget code imports ComfyUI's `scripts/app.js` and `scripts/api.js` by
 * relative path, so this mirrors web/ into a temp directory laid out the way
 * ComfyUI serves it, drops stub modules where those imports land, and runs
 * _checks.mjs there against fake LiteGraph/DOM globals.
 */

import { cpSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repo = join(here, "..", "..");

const root = mkdtempSync(join(tmpdir(), "moonpack-js-"));
try {
    mkdirSync(join(root, "scripts"), { recursive: true });
    mkdirSync(join(root, "extensions"), { recursive: true });

    writeFileSync(join(root, "package.json"), '{"type":"module"}\n');
    writeFileSync(
        join(root, "scripts", "app.js"),
        `export const app = {
  canvas: { ds: { scale: 1 }, editor_alpha: 1, prompt: () => {} },
  registerExtension: (ext) => { globalThis.__ext = ext; },
};
`,
    );
    writeFileSync(
        join(root, "scripts", "api.js"),
        `export const api = { fetchApi: async () => ({ json: async () => ({ loras: [] }) }) };
`,
    );

    cpSync(join(repo, "web"), join(root, "extensions", "moonpack"), { recursive: true });
    cpSync(join(here, "_checks.mjs"), join(root, "_checks.mjs"));

    await import(pathToFileURL(join(root, "_checks.mjs")).href);
    process.exitCode = globalThis.__failures ? 1 : 0;
} finally {
    rmSync(root, { recursive: true, force: true });
}
