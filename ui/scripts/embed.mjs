/**
 * Reads dist/index.html and writes it as CHAT_HTML into
 * ../src/a2akit/_chat_ui.py so the debug UI is bundled
 * into the Python package with zero runtime dependencies.
 *
 * Usage: npm run build && npm run embed
 */
import { readFileSync, writeFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const distHtml = readFileSync(resolve(__dirname, "../dist/index.html"), "utf-8");

// Escape backslashes and triple-quotes for Python string embedding
const escaped = distHtml.replace(/\\/g, "\\\\").replace(/"""/g, '""\\"');

const py = `\
"""Debug UI for a2akit agents — Chat + Task Dashboard."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

CHAT_HTML = """\\
${escaped}
"""


def mount_chat_ui(app: FastAPI) -> None:
    """Mount the debug chat UI at \`\`/chat\`\`."""
    from importlib.metadata import version

    try:
        pkg_version = version("a2akit")
    except Exception:  # noqa: BLE001
        pkg_version = "dev"

    html = CHAT_HTML.replace("{{VERSION}}", pkg_version)

    @app.get("/chat", response_class=HTMLResponse, include_in_schema=False)
    async def debug_chat() -> HTMLResponse:
        return HTMLResponse(html)
`;

const outPath = resolve(__dirname, "../../src/a2akit/_chat_ui.py");
writeFileSync(outPath, py, "utf-8");

const sizeKb = (Buffer.byteLength(distHtml) / 1024).toFixed(1);
console.log(`Embedded ${sizeKb} KB HTML into ${outPath}`);
