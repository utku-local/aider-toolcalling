"""Harder evaluation tasks: several files, several bugs, new classes and CLIs, and refactors that must keep behaviour.
They exist because the basic set saturated at 10/10; each still ships a self-contained Python check, so pass or fail
is decided automatically, and none needs network access.
Checks exercise behaviour through imports or a subprocess, never by matching the agent's exact text.
"""

from evals.tasks import EvalTask

HARD_TASKS: tuple[EvalTask, ...] = (
    EvalTask(
        "extract-module",
        {
            "app.py": "def slug(s):\n    return s.strip().lower().replace(' ', '-')\n\n\n"
            "def initials(name):\n    return ''.join(p[0].upper() for p in name.split())\n\n\n"
            "def main(name):\n    return f'{initials(name)}:{slug(name)}'\n",
        },
        "Move slug and initials from app.py into a new module textutils.py; app.py must import them from there.",
        "import ast, pathlib, app, textutils\n"
        "tree = ast.parse(pathlib.Path('app.py').read_text())\n"
        "assert not [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('slug', 'initials')]\n"
        "assert app.main('Ada Lovelace') == 'AL:ada-lovelace'\nassert textutils.slug(' A B ') == 'a-b'\n",
    ),
    EvalTask(
        "two-bugs",
        {
            "inventory.py": "class Inventory:\n    def __init__(self):\n        self.items = {}\n\n"
            "    def add(self, name, qty):\n        self.items[name] = qty\n\n"
            "    def remove(self, name, qty):\n        self.items[name] -= qty\n\n"
            "    def total(self):\n        return len(self.items)\n",
        },
        "Inventory.add should accumulate quantities and total() should return the sum of all quantities. "
        "remove must raise ValueError when removing more than is available. Fix it.",
        "from inventory import Inventory\ninv = Inventory()\ninv.add('a', 2)\ninv.add('a', 3)\ninv.add('b', 1)\n"
        "assert inv.total() == 6\ninv.remove('a', 4)\nassert inv.items['a'] == 1\n"
        "try:\n    inv.remove('b', 5)\nexcept ValueError:\n    pass\nelse:\n    raise SystemExit(1)\n",
    ),
    EvalTask(
        "cli-flag",
        {
            "count.py": "import argparse\nimport sys\n\n\ndef main(argv=None):\n"
            "    parser = argparse.ArgumentParser()\n    parser.add_argument('words', nargs='*')\n"
            "    args = parser.parse_args(argv)\n    print(len(args.words))\n\n\n"
            "if __name__ == '__main__':\n    main(sys.argv[1:])\n",
        },
        "Add a --unique flag to count.py that counts distinct words only.",
        "import subprocess, sys\nrun = lambda *a: subprocess.run([sys.executable, 'count.py', *a], "
        "capture_output=True, text=True).stdout.strip()\n"
        "assert run('a', 'b', 'a') == '3'\nassert run('--unique', 'a', 'b', 'a') == '2'\n",
    ),
    EvalTask(
        "type-mismatch",
        {
            "prices.py": "def parse_price(text):\n    return text.replace('$', '').strip()\n",
            "cart.py": "from prices import parse_price\n\n\ndef cart_total(lines):\n"
            "    return sum(parse_price(line) for line in lines)\n",
        },
        "cart_total(['$1.50', '$2']) crashes. Make it return 3.5, and keep parse_price returning a number.",
        "from cart import cart_total\nfrom prices import parse_price\n"
        "assert cart_total(['$1.50', '$2']) == 3.5\nassert isinstance(parse_price('$3'), float)\n",
    ),
    EvalTask(
        "implement-class",
        {"stack.py": "class Stack:\n    pass\n"},
        "Implement Stack with push(x), pop(), peek() and is_empty(); pop and peek on an empty stack raise IndexError, "
        "and len(stack) returns the number of items.",
        "from stack import Stack\ns = Stack()\nassert s.is_empty() and len(s) == 0\ns.push(1)\ns.push(2)\n"
        "assert s.peek() == 2 and len(s) == 2\nassert s.pop() == 2 and s.pop() == 1\n"
        "for op in (s.pop, s.peek):\n    try:\n        op()\n    except IndexError:\n        pass\n"
        "    else:\n        raise SystemExit(1)\n",
    ),
    EvalTask(
        "dedupe-callers",
        {
            "listutil.py": "def dedupe(items):\n    return list(set(items))\n",
            "report.py": "from listutil import dedupe\n\n\ndef tags(post_tags):\n    return dedupe(post_tags)\n",
        },
        "dedupe must keep the original order of first occurrences; report.tags relies on that. Fix it.",
        "from listutil import dedupe\nfrom report import tags\n"
        "assert dedupe([3, 1, 3, 2, 1]) == [3, 1, 2]\nassert tags(['b', 'a', 'b']) == ['b', 'a']\n",
    ),
    EvalTask(
        "config-defaults",
        {
            "config.py": "import json\n\nDEFAULTS = {'port': 8000, 'debug': False}\n\n\n"
            "def load(path):\n    with open(path) as f:\n        return json.load(f)\n",
        },
        "load(path) must merge the file over DEFAULTS, and return DEFAULTS (a copy) when the file does not exist.",
        "import json, config\njson.dump({'debug': True}, open('c.json', 'w'))\n"
        "assert config.load('c.json') == {'port': 8000, 'debug': True}\n"
        "d = config.load('missing.json')\nassert d == {'port': 8000, 'debug': False}\n"
        "d['port'] = 1\nassert config.DEFAULTS['port'] == 8000\n",
    ),
    EvalTask(
        "fast-fib",
        {"fib.py": "def fib(n):\n    if n < 2:\n        return 1\n    return fib(n - 1) + fib(n - 2)\n"},
        "fib(n) must return the n-th Fibonacci number with fib(0) == 0 and fib(1) == 1, and fib(90) must be fast.",
        "import time\nfrom fib import fib\nassert [fib(i) for i in range(7)] == [0, 1, 1, 2, 3, 5, 8]\n"
        "start = time.time()\nassert fib(90) == 2880067194370816120\nassert time.time() - start < 1\n",
    ),
    EvalTask(
        "rename-class",
        {
            "models.py": "class Usr:\n    def __init__(self, name):\n        self.name = name\n",
            "service.py": "from models import Usr\n\n\ndef make(name):\n    return Usr(name)\n",
            "views.py": "from models import Usr\n\n\ndef label(u: Usr):\n    return f'User {u.name}'\n",
        },
        "Rename the class Usr to User in every file.",
        "import pathlib, models, service, views\nassert not hasattr(models, 'Usr')\n"
        "assert isinstance(service.make('a'), models.User)\nassert views.label(models.User('b')) == 'User b'\n"
        "assert 'Usr' not in ''.join(pathlib.Path(f).read_text() for f in ('models.py', 'service.py', 'views.py'))\n",
    ),
    EvalTask(
        "parse-logs",
        {"logs.py": "def parse(line):\n    raise NotImplementedError\n"},
        "Implement parse(line) for lines like '2026-10-27 14:03:11 ERROR db: timeout after 5s': return a dict with "
        "date, time, level, source and message; return None for lines that do not match.",
        "from logs import parse\nr = parse('2026-10-27 14:03:11 ERROR db: timeout after 5s')\n"
        "assert r == {'date': '2026-10-27', 'time': '14:03:11', 'level': 'ERROR', 'source': 'db', "
        "'message': 'timeout after 5s'}, r\nassert parse('garbage') is None\n"
        "assert parse('2026-01-02 00:00:00 INFO web: ok')['source'] == 'web'\n",
    ),
)
