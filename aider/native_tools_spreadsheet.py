"""The read_spreadsheet tool: reads .xlsx/.xlsm workbooks with the standard library and returns sheets as text.
An .xlsx file is a zip of XML parts; the workbook lists the sheets, sharedStrings holds the text cells, and each
sheet part holds rows of cells, so zipfile and ElementTree are enough and no dependency is added.
Formulas show the value Excel last saved; rows come back in pages so large sheets do not flood the prompt.
"""

import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import PurePosixPath
from typing import Optional

from aider.native_tool_context import ToolContext
from aider.native_toolcalling import NativeToolError, NativeToolRegistry
from aider.native_tools_builtin import resolve_in_root

MAIN_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
WORKBOOK_PART = "xl/workbook.xml"
WORKBOOK_RELS_PART = "xl/_rels/workbook.xml.rels"
SHARED_STRINGS_PART = "xl/sharedStrings.xml"
STYLES_PART = "xl/styles.xml"
# Built-in number formats 14-22 and 45-47 are dates or times; serials count days from 1899-12-30.
BUILTIN_DATE_FORMATS = frozenset({14, 15, 16, 17, 18, 19, 20, 21, 22, 45, 46, 47})
DATE_TOKENS = frozenset("dy")
EXCEL_EPOCH = datetime(1899, 12, 30)
NUMBER = re.compile(r"-?\d+(\.\d+)?")
XL_DIR = "xl"
SUPPORTED_SUFFIXES = frozenset({".xlsx", ".xlsm"})
DEFAULT_MAX_ROWS = 50
MAX_ROWS_LIMIT = 500
CELL_REF = re.compile(r"([A-Z]+)(\d+)")
CELL_SEPARATOR = " | "
ALPHABET_SIZE = 26
FIRST_COLUMN = "A"
MORE_ROWS_NOTE = "[{shown} of {total} rows shown; ask with start_row to read more]"

SPREADSHEET_PARAMETERS = {
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        "sheet": {"type": "string", "description": "Defaults to the first sheet."},
        "start_row": {"type": "integer", "description": "1-based."},
        "max_rows": {"type": "integer", "description": f"Rows to return (default {DEFAULT_MAX_ROWS}, "
                                                       f"max {MAX_ROWS_LIMIT})."},
    },
    "required": ["path"],
}


class SpreadsheetError(NativeToolError):
    """Raised for unsupported or unreadable workbooks."""


def column_index(letters: str) -> int:
    index = 0
    for letter in letters:
        index = index * ALPHABET_SIZE + (ord(letter) - ord(FIRST_COLUMN) + 1)
    return index - 1


def sheet_parts(book: zipfile.ZipFile) -> list[tuple[str, str]]:
    """(sheet name, part path) in workbook order."""
    rels = ET.fromstring(book.read(WORKBOOK_RELS_PART))
    targets = {r.get("Id"): r.get("Target") for r in rels.iter(f"{PKG_REL_NS}Relationship")}
    workbook = ET.fromstring(book.read(WORKBOOK_PART))
    sheets = []
    for sheet in workbook.iter(f"{MAIN_NS}sheet"):
        target = targets.get(sheet.get(f"{REL_NS}id"), "")
        part = target.lstrip("/") if target.startswith("/") else str(PurePosixPath(XL_DIR) / target)
        sheets.append((sheet.get("name", ""), part))
    return sheets


def shared_strings(book: zipfile.ZipFile) -> list[str]:
    if SHARED_STRINGS_PART not in book.namelist():
        return []
    root = ET.fromstring(book.read(SHARED_STRINGS_PART))
    return ["".join(t.text or "" for t in item.iter(f"{MAIN_NS}t")) for item in root.iter(f"{MAIN_NS}si")]


def is_date_format(code: str) -> bool:
    """A number format shows a date when, outside quoted text and [..] sections, it has a day or year token."""
    plain = re.sub(r'"[^"]*"|\[[^\]]*\]', "", code).lower()
    return bool(DATE_TOKENS & set(plain))


def date_styles(book: zipfile.ZipFile) -> set[str]:
    """Indexes (as in a cell's s attribute) of cell styles that display numbers as dates."""
    if STYLES_PART not in book.namelist():
        return set()
    root = ET.fromstring(book.read(STYLES_PART))
    custom = {f.get("numFmtId"): f.get("formatCode", "") for f in root.iter(f"{MAIN_NS}numFmt")}
    cell_xfs = root.find(f"{MAIN_NS}cellXfs")
    styles = list(cell_xfs.iter(f"{MAIN_NS}xf")) if cell_xfs is not None else []
    return {
        str(index) for index, xf in enumerate(styles)
        if int(xf.get("numFmtId", "0")) in BUILTIN_DATE_FORMATS or is_date_format(custom.get(xf.get("numFmtId"), ""))
    }


def excel_date(serial: str) -> str:
    """ISO date (and time when present) for an Excel 1900-system serial number."""
    value = float(serial)
    moment = EXCEL_EPOCH + timedelta(days=value)
    return moment.date().isoformat() if value == int(value) else moment.isoformat(sep=" ", timespec="minutes")


def cell_value(cell: ET.Element, strings: list[str], dates: set[str]) -> str:
    kind = cell.get("t")
    if kind == "inlineStr":
        return "".join(t.text or "" for t in cell.iter(f"{MAIN_NS}t"))
    raw = cell.findtext(f"{MAIN_NS}v") or ""
    formula = cell.findtext(f"{MAIN_NS}f")
    if not raw and formula:
        return "=" + formula
    if kind == "s" and raw.isdigit() and int(raw) < len(strings):
        return strings[int(raw)]
    if kind == "b":
        return "TRUE" if raw == "1" else "FALSE"
    if kind in (None, "n") and cell.get("s") in dates and NUMBER.fullmatch(raw):
        return excel_date(raw)
    return raw


def sheet_rows(book: zipfile.ZipFile, part: str, strings: list[str], dates: set[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in ET.fromstring(book.read(part)).iter(f"{MAIN_NS}row"):
        values: dict[int, str] = {}
        for cell in row.iter(f"{MAIN_NS}c"):
            match = CELL_REF.match(cell.get("r", ""))
            column = column_index(match.group(1)) if match else len(values)
            values[column] = cell_value(cell, strings, dates)
        number = int(row.get("r", len(rows) + 1))
        while len(rows) < number - 1:
            rows.append([])
        rows.append([values.get(i, "") for i in range(max(values, default=-1) + 1)])
    return rows


def open_workbook(ctx: ToolContext, path: str) -> zipfile.ZipFile:
    target = resolve_in_root(ctx.root, path)
    if target.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise SpreadsheetError(f"Only .xlsx and .xlsm are supported, not {target.suffix or 'this file'}; "
                               "convert old .xls files or read CSV with read_file")
    try:
        return zipfile.ZipFile(target)
    except (zipfile.BadZipFile, OSError) as err:
        raise SpreadsheetError(f"Cannot open {path!r} as a workbook: {err}") from err


def read_spreadsheet(
    ctx: ToolContext, path: str, sheet: Optional[str] = None, start_row: int = 1, max_rows: int = DEFAULT_MAX_ROWS
) -> str:
    with open_workbook(ctx, path) as book:
        sheets = sheet_parts(book)
        if not sheets:
            raise SpreadsheetError(f"{path!r} has no sheets")
        chosen = next((s for s in sheets if s[0] == sheet), None) if sheet else sheets[0]
        if chosen is None:
            raise SpreadsheetError(f"No sheet {sheet!r}; sheets: {[name for name, _ in sheets]}")
        rows = sheet_rows(book, chosen[1], shared_strings(book), date_styles(book))
    first = max(start_row, 1)
    count = max(1, min(max_rows, MAX_ROWS_LIMIT))
    page = rows[first - 1 : first - 1 + count]
    lines = [f"Sheets: {', '.join(name for name, _ in sheets)}", f"Sheet {chosen[0]!r}, rows {first}-"
             f"{first + len(page) - 1} of {len(rows)}:"]
    lines += [f"{first + i}: {CELL_SEPARATOR.join(row)}" for i, row in enumerate(page)]
    if first - 1 + len(page) < len(rows):
        lines.append(MORE_ROWS_NOTE.format(shown=len(page), total=len(rows)))
    return "\n".join(lines)


def register_spreadsheet_tool(registry: NativeToolRegistry, ctx: ToolContext) -> None:
    """Add read_spreadsheet, bound to `ctx`, to `registry`."""
    registry.register(
        "read_spreadsheet",
        "Read an Excel workbook (.xlsx/.xlsm): its sheet names and one sheet's rows, in pages.",
        SPREADSHEET_PARAMETERS,
        lambda path, sheet=None, start_row=1, max_rows=DEFAULT_MAX_ROWS: read_spreadsheet(
            ctx, path, sheet, start_row, max_rows
        ),
    )
