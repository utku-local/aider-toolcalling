"""Keeps long tool output whole: the full text goes to a file in the project and the model gets a preview and path.
The file lives in .aider-agent/outputs/, which carries its own .gitignore so none of it is committed; the model
can read any part of it with read_file and a line range.
The preview keeps the start and the end, because errors and summaries usually sit at the end of command output.
"""

from pathlib import Path

OUTPUT_DIR = Path(".aider-agent") / "outputs"
IGNORE_ALL = "*\n"
ENCODING = "utf-8"
HEAD_CHARS = 4_000
TAIL_CHARS = 16_000
SPILL_NOTE = (
    "\n[... output too long: {total} characters, {lines} lines. The full text is in {path}; read parts of it with "
    "read_file and start_line/end_line ...]\n"
)


def preview(text: str, rel_path: str, head: int = HEAD_CHARS, tail: int = TAIL_CHARS) -> str:
    """The start and end of `text` around a note naming the file that holds all of it."""
    note = SPILL_NOTE.format(total=len(text), lines=len(text.splitlines()), path=rel_path)
    return text[:head] + note + text[-tail:]


class OutputSpill:
    """Writes long outputs under `root`/.aider-agent/outputs and returns their paths relative to `root`."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.count = 0

    def save(self, text: str, label: str) -> str:
        folder = self.root / OUTPUT_DIR
        folder.mkdir(parents=True, exist_ok=True)
        ignore = folder / ".gitignore"
        if not ignore.exists():
            ignore.write_text(IGNORE_ALL, encoding=ENCODING)
        self.count += 1
        rel = OUTPUT_DIR / f"{label}-{self.count}.txt"
        (self.root / rel).write_text(text, encoding=ENCODING)
        return str(rel)

    def shorten(self, text: str, label: str) -> str:
        """`text` replaced by its preview, with the full text saved to a file."""
        return preview(text, self.save(text, label))
