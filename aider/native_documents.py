"""Turns files that are not plain text into text read_file can return: Jupyter notebooks, PDFs and binary files.
A notebook is rendered cell by cell with its text outputs; a PDF goes through poppler's pdftotext, so no Python
dependency is added; any other binary file is refused with a short reason instead of returning garbage.
Notebook rendering is pure; only the PDF step runs a command.
"""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from aider.native_toolcalling import NativeToolError

NOTEBOOK_SUFFIX = ".ipynb"
PDF_SUFFIX = ".pdf"
PDFTOTEXT = "pdftotext"
PDF_TIMEOUT_SECONDS = 60
SNIFF_BYTES = 8_192
NUL = b"\0"
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".heic"})
MAX_OUTPUT_CHARS = 2_000
NO_PDFTOTEXT = "Reading PDFs needs poppler's pdftotext; ask the user to install it with: brew install poppler"
IMAGE_FILE = "{path} is an image; the agent's model reads text only. Ask the user to describe it if it matters."
BINARY_FILE = "{path} is a binary file and cannot be read as text."


class DocumentError(NativeToolError):
    """Raised when a file cannot be turned into text."""


def cell_text(value: object) -> str:
    return "".join(value) if isinstance(value, list) else str(value or "")


def render_output(output: dict) -> str:
    if "text" in output:
        text = cell_text(output["text"])
    else:
        data = output.get("data") or {}
        text = cell_text(data.get("text/plain", "")) or cell_text(output.get("evalue", ""))
    return text[:MAX_OUTPUT_CHARS]


def render_notebook(raw: str) -> str:
    """Cells as '# [n] code' / '# [n] markdown' sections, code outputs after '# output'."""
    try:
        cells = json.loads(raw).get("cells", [])
    except (ValueError, AttributeError) as err:
        raise DocumentError(f"Not a valid notebook: {err}") from err
    parts = []
    for number, cell in enumerate(cells, start=1):
        kind = cell.get("cell_type", "code")
        parts.append(f"# [{number}] {kind}\n{cell_text(cell.get('source')).rstrip()}")
        outputs = [render_output(o) for o in cell.get("outputs", []) if isinstance(o, dict)]
        if any(o.strip() for o in outputs):
            parts.append("# output\n" + "\n".join(o.rstrip() for o in outputs if o.strip()))
    return "\n\n".join(parts) + "\n"


def pdf_text(path: Path) -> str:
    if shutil.which(PDFTOTEXT) is None:
        raise DocumentError(NO_PDFTOTEXT)
    done = subprocess.run([PDFTOTEXT, "-layout", str(path), "-"], capture_output=True, text=True,
                          errors="replace", timeout=PDF_TIMEOUT_SECONDS)
    if done.returncode != 0:
        raise DocumentError(f"pdftotext failed on {path.name}: {done.stderr.strip()}")
    return done.stdout


def document_text(path: Path, shown: str) -> Optional[str]:
    """Text for a notebook or PDF; None for other files, which raise only when they are binary."""
    suffix = path.suffix.lower()
    if suffix == NOTEBOOK_SUFFIX:
        return render_notebook(path.read_text(encoding="utf-8", errors="replace"))
    if suffix == PDF_SUFFIX:
        return pdf_text(path)
    with path.open("rb") as handle:
        head = handle.read(SNIFF_BYTES)
    if NUL in head:
        raise DocumentError((IMAGE_FILE if suffix in IMAGE_SUFFIXES else BINARY_FILE).format(path=shown))
    return None
