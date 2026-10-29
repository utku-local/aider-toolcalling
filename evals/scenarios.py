"""Behaviour scenarios for the agent: small projects that test whether it plans, re-tests after a failure, and
checks a stopped service before touching code.
Each scenario is files plus a prompt; the runner in evals.run_scenarios builds a git project from them and the
scoring in evals.scenario_scoring judges the agent's saved session.
The prompts are fixed so runs on different models and days stay comparable; change one only with a note in docs.
"""

PLANNING = {
    "files": {
        "notes/__init__.py": "",
        "notes/store.py": '"""In-memory note store."""\n\n\nclass NoteStore:\n    def __init__(self):\n'
        "        self.notes = []\n\n    def add(self, text):\n        self.notes.append(text)\n\n"
        "    def all(self):\n        return list(self.notes)\n",
        "notes/cli.py": '"""Command line: notes add TEXT | notes list."""\nimport sys\n\nfrom notes.store import '
        "NoteStore\n\n\ndef main(argv, store=None):\n    store = store or NoteStore()\n    command = argv[0]\n"
        '    if command == "add":\n        store.add(" ".join(argv[1:]))\n        return "added"\n'
        '    if command == "list":\n        return "\\n".join(store.all())\n    return "unknown command"\n',
        "tests/__init__.py": "",
        "tests/test_cli.py": "import unittest\n\nfrom notes.cli import main\nfrom notes.store import NoteStore\n\n\n"
        "class CliTest(unittest.TestCase):\n    def test_add_and_list(self):\n        store = NoteStore()\n"
        '        main(["add", "buy", "milk"], store)\n        self.assertEqual(main(["list"], store), "buy milk")\n',
    },
    "prompt": "Add tags to notes: `notes add --tag work buy milk` stores the note with the tag 'work', and "
    "`notes list --tag work` lists only notes with that tag. Notes without --tag keep working as before. "
    "Add tests for the new behaviour.",
}

RETEST = {
    "files": {
        "stats/__init__.py": "",
        "stats/summary.py": '"""Summary statistics for a list of numbers."""\n\n\ndef mean(values):\n'
        "    return sum(values) / len(values) + 1\n\n\ndef median(values):\n    ordered = sorted(values)\n"
        "    middle = len(ordered) // 2\n    return ordered[middle]\n",
        "tests/__init__.py": "",
        "tests/test_summary.py": "import unittest\n\nfrom stats.summary import mean, median\n\n\n"
        "class SummaryTest(unittest.TestCase):\n    def test_mean(self):\n        self.assertEqual(mean([1, 2, 3]), 2)\n\n"
        "    def test_median_odd(self):\n        self.assertEqual(median([3, 1, 2]), 2)\n\n"
        "    def test_median_even(self):\n        self.assertEqual(median([4, 1, 3, 2]), 2.5)\n",
    },
    # Two bugs: fixing the obvious one (mean) leaves a failing test, so the agent must re-test and fix again.
    "prompt": "The tests in tests/test_summary.py fail. Make all of them pass.",
}

SERVICE = {
    "files": {
        "config.toml": '[cache]\nhost = "127.0.0.1"\nport = 6851\n',
        "README.md": "# Cache client\n\nNeeds the cache server running: `python cache_server.py` (reads config.toml).\n",
        "cache_server.py": '"""Tiny cache server on the port from config.toml."""\nimport http.server\nimport tomllib\n\n'
        'PORT = tomllib.load(open("config.toml", "rb"))["cache"]["port"]\n\n\nclass Handler(http.server.'
        "BaseHTTPRequestHandler):\n    def do_GET(self):\n        self.send_response(200)\n        self.end_headers()\n"
        '        self.wfile.write(b"pong")\n\n\nif __name__ == "__main__":\n    http.server.HTTPServer(("127.0.0.1", '
        "PORT), Handler).serve_forever()\n",
        "client.py": '"""Pings the cache server named in config.toml."""\nimport tomllib\nimport urllib.request\n\n'
        'CONFIG = tomllib.load(open("config.toml", "rb"))["cache"]\n\n\ndef ping():\n'
        "    url = f\"http://{CONFIG['host']}:{CONFIG['port']}/\"\n"
        "    with urllib.request.urlopen(url, timeout=3) as reply:\n        return reply.read().decode()\n\n\n"
        'if __name__ == "__main__":\n    print(ping())\n',
    },
    "prompt": "Running `python client.py` fails. Find out why and fix it.",
}

SCENARIOS = {"planning": PLANNING, "retest": RETEST, "service": SERVICE}
SERVICE_CODE_FILES = ("client.py", "cache_server.py", "config.toml")
SERVICE_START_HINT = "cache_server.py"
