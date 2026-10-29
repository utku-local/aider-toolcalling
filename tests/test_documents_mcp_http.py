"""Tests for reading notebooks, PDFs and binary files, and for the MCP Streamable HTTP client.
The notebook and binary checks use small files; the PDF check builds a one-page PDF and runs pdftotext when it is
installed. The MCP client talks to a local HTTP server that answers in JSON and in an event stream and checks that
the session id from initialize comes back on later requests.
"""

import json
import shutil
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from aider.coders.native_agent_config import AgentConfigError, parse_config
from aider.native_documents import DocumentError, document_text, render_notebook
from aider.native_mcp_http import MCPHttpClient, expand_env, messages_in

NOTEBOOK = json.dumps({"cells": [
    {"cell_type": "markdown", "source": ["# Title\n", "Some notes"]},
    {"cell_type": "code", "source": "print(1 + 1)", "outputs": [{"output_type": "stream", "text": ["2\n"]}]},
]})
SESSION = "session-42"


def one_page_pdf(text: str) -> bytes:
    """A minimal valid PDF with one line of text."""
    stream = f"BT /F1 24 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
               b"/Resources << /Font << /F1 5 0 R >> >> >>",
               b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    return out + f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()


class DocumentTest(unittest.TestCase):
    def test_notebook_cells_and_outputs(self) -> None:
        text = render_notebook(NOTEBOOK)
        self.assertIn("# [1] markdown\n# Title\nSome notes", text)
        self.assertIn("# [2] code\nprint(1 + 1)\n\n# output\n2", text)
        with self.assertRaises(DocumentError):
            render_notebook("not json")

    def test_binary_and_image_files_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            image, blob, plain = Path(tmp) / "shot.png", Path(tmp) / "data.bin", Path(tmp) / "a.txt"
            image.write_bytes(b"\x89PNG\0\0data")
            blob.write_bytes(b"\0\1\2")
            plain.write_text("hello")
            with self.assertRaisesRegex(DocumentError, "image"):
                document_text(image, "shot.png")
            with self.assertRaisesRegex(DocumentError, "binary"):
                document_text(blob, "data.bin")
            self.assertIsNone(document_text(plain, "a.txt"))

    @unittest.skipUnless(shutil.which("pdftotext"), "pdftotext is not installed")
    def test_pdf_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "doc.pdf"
            pdf.write_bytes(one_page_pdf("Invoice total 42"))
            self.assertIn("Invoice total 42", document_text(pdf, "doc.pdf"))


class MCPHandler(BaseHTTPRequestHandler):
    seen_sessions: list = []

    def do_POST(self) -> None:
        message = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        MCPHandler.seen_sessions.append(self.headers.get("Mcp-Session-Id"))
        if "id" not in message:
            self.send_response(202)
            self.end_headers()
            return
        method, request_id = message["method"], message["id"]
        if method == "tools/list":
            event = json.dumps({"jsonrpc": "2.0", "id": request_id,
                                "result": {"tools": [{"name": "echo", "inputSchema": {"type": "object"}}]}})
            self.reply(f"event: message\ndata: {event}\n\n", "text/event-stream")
            return
        result = ({"content": [{"type": "text", "text": f"echo {message['params']['arguments']['word']}"}]}
                  if method == "tools/call" else {"protocolVersion": "2025-06-18"})
        self.reply(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}), "application/json")

    def reply(self, body: str, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Mcp-Session-Id", SESSION)
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *args: object) -> None:
        """Keep test output quiet."""


class MCPHttpTest(unittest.TestCase):
    def test_initialize_list_and_call(self) -> None:
        server = HTTPServer(("127.0.0.1", 0), MCPHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            client = MCPHttpClient(f"http://127.0.0.1:{server.server_port}/mcp", {})
            client.initialize()
            self.assertEqual([t.name for t in client.list_tools()], ["echo"])
            self.assertEqual(client.call_tool("echo", {"word": "hi"}), "echo hi")
        finally:
            server.shutdown()
        self.assertEqual(MCPHandler.seen_sessions[0], None)
        self.assertTrue(all(s == SESSION for s in MCPHandler.seen_sessions[1:]))

    def test_helpers_and_config(self) -> None:
        self.assertEqual(expand_env("Bearer ${TOKEN}", {"TOKEN": "abc"}), "Bearer abc")
        self.assertEqual(len(messages_in('[{"id": 1}, {"id": 2}]', "application/json")), 2)
        config = parse_config({"mcp_servers": {"docs": {"url": "https://mcp.example.com/mcp",
                                                        "headers": {"Authorization": "Bearer ${KEY}"}}}})
        self.assertEqual(config.mcp_servers[0].url, "https://mcp.example.com/mcp")
        with self.assertRaises(AgentConfigError):
            parse_config({"mcp_servers": {"docs": {"url": "ftp://x"}}})
