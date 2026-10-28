"""Tests for read_spreadsheet against small workbooks built from raw XML parts with zipfile.
They cover shared and inline strings, numbers, booleans, gaps between cells and rows, several sheets, paging and
the errors for unsupported or broken files; no spreadsheet library is needed.
The parts mirror what Excel writes, including relationship ids that map sheet names to sheet files.
"""

import tempfile
import unittest
import zipfile
from pathlib import Path

from aider.native_tool_context import ToolContext
from aider.native_tools_spreadsheet import SpreadsheetError, column_index, read_spreadsheet

NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
RNS = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
WORKBOOK = f'<workbook {NS} {RNS}><sheets><sheet name="Sales" sheetId="1" r:id="rId1"/>' \
           f'<sheet name="Notes" sheetId="2" r:id="rId2"/></sheets></workbook>'
RELS = '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' \
       '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Target="worksheets/sheet2.xml"/>' \
       '</Relationships>'
STRINGS = f'<sst {NS}><si><t>Product</t></si><si><t>Qty</t></si><si><t>Apple</t></si></sst>'
SHEET1 = f'<worksheet {NS}><sheetData>' \
         '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>' \
         '<row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2"><v>12</v></c><c r="D2" t="b"><v>1</v></c></row>' \
         '<row r="4"><c r="A4" t="inlineStr"><is><t>Total</t></is></c><c r="B4"><f>SUM(B2:B3)</f><v>12</v></c></row>' \
         '</sheetData></worksheet>'
SHEET2 = f'<worksheet {NS}><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>hello</t></is></c></row>' \
         '</sheetData></worksheet>'


class ReadSpreadsheetTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        with zipfile.ZipFile(self.root / "book.xlsx", "w") as book:
            for name, text in (("xl/workbook.xml", WORKBOOK), ("xl/_rels/workbook.xml.rels", RELS),
                               ("xl/sharedStrings.xml", STRINGS), ("xl/worksheets/sheet1.xml", SHEET1),
                               ("xl/worksheets/sheet2.xml", SHEET2)):
                book.writestr(name, text)
        self.ctx = ToolContext(self.root, list, lambda a, r: [], lambda p, t, d: True, lambda p: None, False)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_first_sheet_with_gaps_and_types(self) -> None:
        text = read_spreadsheet(self.ctx, "book.xlsx")
        self.assertIn("Sheets: Sales, Notes", text)
        self.assertIn("1: Product | Qty", text)
        self.assertIn("2: Apple | 12 |  | TRUE", text)
        self.assertIn("3: \n", text + "\n")
        self.assertIn("4: Total | 12", text)

    def test_named_sheet_and_paging(self) -> None:
        self.assertIn("1: hello", read_spreadsheet(self.ctx, "book.xlsx", sheet="Notes"))
        page = read_spreadsheet(self.ctx, "book.xlsx", start_row=2, max_rows=1)
        self.assertIn("rows 2-2 of 4", page)
        self.assertIn("1 of 4 rows shown", page)
        with self.assertRaises(SpreadsheetError):
            read_spreadsheet(self.ctx, "book.xlsx", sheet="Missing")

    def test_unsupported_and_broken_files(self) -> None:
        (self.root / "old.xls").write_bytes(b"\xd0\xcf\x11\xe0")
        (self.root / "broken.xlsx").write_text("not a zip")
        for path in ("old.xls", "broken.xlsx"):
            with self.subTest(path=path), self.assertRaises(SpreadsheetError):
                read_spreadsheet(self.ctx, path)

    def test_dates_and_formulas_without_cached_values(self) -> None:
        styles = f'<styleSheet {NS}><numFmts><numFmt numFmtId="164" formatCode="dd.mm.yyyy"/>' \
                 '<numFmt numFmtId="165" formatCode="&quot;day&quot; 0.00"/></numFmts><cellXfs>' \
                 '<xf numFmtId="0"/><xf numFmtId="14"/><xf numFmtId="164"/><xf numFmtId="165"/></cellXfs></styleSheet>'
        sheet = f'<worksheet {NS}><sheetData><row r="1"><c r="A1" s="1"><v>46297</v></c>' \
                '<c r="B1" s="2"><v>46297.5</v></c><c r="C1" s="3"><v>2.5</v></c><c r="D1" s="0"><v>46297</v></c>' \
                '<c r="E1"><f>SUM(A1:B1)</f></c></row></sheetData></worksheet>'
        rels = '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' \
               '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>'
        workbook = f'<workbook {NS} {RNS}><sheets><sheet name="D" sheetId="1" r:id="rId1"/></sheets></workbook>'
        with zipfile.ZipFile(self.root / "dates.xlsx", "w") as book:
            for name, text in (("xl/workbook.xml", workbook), ("xl/_rels/workbook.xml.rels", rels),
                               ("xl/styles.xml", styles), ("xl/worksheets/sheet1.xml", sheet)):
                book.writestr(name, text)
        self.assertIn("1: 2026-10-02 | 2026-10-02 12:00 | 2.5 | 46297 | =SUM(A1:B1)",
                      read_spreadsheet(self.ctx, "dates.xlsx"))

    def test_column_index(self) -> None:
        self.assertEqual([column_index(c) for c in ("A", "Z", "AA", "AZ")], [0, 25, 26, 51])


if __name__ == "__main__":
    unittest.main()
