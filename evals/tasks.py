"""The evaluation tasks: each one is a tiny project, an instruction for the agent and a Python check.
A check is a script run in the project directory after the agent finishes; exit code 0 means the task passed.
Tasks cover bug fixes, new code, renames across files, search in a larger tree and writing tests, and none of them
needs the agent to run shell commands, so they work with commands left unapproved.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class EvalTask:
    name: str
    files: dict[str, str]
    prompt: str
    check: str


TASKS: tuple[EvalTask, ...] = (
    EvalTask(
        "fix-discount",
        {
            "shop/__init__.py": "",
            "shop/pricing.py": "def total(prices, discount):\n    subtotal = sum(prices)\n"
            "    return subtotal - subtotal * discount\n",
            "test_pricing.py": "from shop.pricing import total\n\n\ndef test_total():\n"
            "    assert total([10, 20], 10) == 27\n",
        },
        "The test in test_pricing.py fails. Find the bug and fix it.",
        "from shop.pricing import total\nassert total([10, 20], 10) == 27\nassert total([50], 0) == 50\n",
    ),
    EvalTask(
        "add-function",
        {"calc.py": "def add(a, b):\n    return a + b\n"},
        "Add a subtract(a, b) function to calc.py.",
        "from calc import add, subtract\nassert subtract(5, 3) == 2\nassert add(1, 2) == 3\n",
    ),
    EvalTask(
        "rename-across-files",
        {
            "billing.py": "def calc_total(items):\n    return sum(items)\n",
            "report.py": "from billing import calc_total\n\n\ndef report(items):\n"
            "    return f'Total: {calc_total(items)}'\n",
        },
        "Rename calc_total to compute_total everywhere.",
        "import billing, report\nassert not hasattr(billing, 'calc_total')\n"
        "assert billing.compute_total([1, 2]) == 3\nassert report.report([1, 2]) == 'Total: 3'\n",
    ),
    EvalTask(
        "off-by-one",
        {"lists.py": "def last_n(items, n):\n    return items[len(items) - n - 1:]\n"},
        "last_n(items, n) should return the last n items but returns one too many. Fix it.",
        "from lists import last_n\nassert last_n([1, 2, 3, 4], 2) == [3, 4]\nassert last_n([1], 1) == [1]\n",
    ),
    EvalTask(
        "validate-input",
        {"bank.py": "def withdraw(balance, amount):\n    return balance - amount\n"},
        "withdraw must raise ValueError when amount is negative or larger than balance.",
        "from bank import withdraw\nassert withdraw(10, 3) == 7\n"
        "for bad in (-1, 11):\n    try:\n        withdraw(10, bad)\n    except ValueError:\n        pass\n"
        "    else:\n        raise SystemExit(1)\n",
    ),
    EvalTask(
        "implement-stub",
        {"text.py": "def is_palindrome(s):\n    raise NotImplementedError\n"},
        "Implement is_palindrome(s): ignore case, spaces and punctuation.",
        "from text import is_palindrome\nassert is_palindrome('A man, a plan, a canal: Panama')\n"
        "assert not is_palindrome('hello')\n",
    ),
    EvalTask(
        "config-constant",
        {
            "config.py": "DEBUG = False\n",
            "app.py": "def timeout():\n    return 30\n",
        },
        "Add TIMEOUT_SECONDS = 45 to config.py and make app.timeout() return it.",
        "import app, config\nassert config.TIMEOUT_SECONDS == 45\nassert app.timeout() == 45\n",
    ),
    EvalTask(
        "find-the-bug",
        {
            "pkg/__init__.py": "",
            "pkg/io/__init__.py": "",
            "pkg/io/readers.py": "def read_lines(text):\n    return text.split('\\n')\n",
            "pkg/core/__init__.py": "",
            "pkg/core/stats.py": "def average(values):\n    return sum(values) / (len(values) + 1)\n",
            "pkg/core/format.py": "def percent(x):\n    return f'{x:.0%}'\n",
        },
        "Somewhere in pkg the average of [2, 4] comes out wrong. Find and fix the bug.",
        "from pkg.core.stats import average\nassert average([2, 4]) == 3\n",
    ),
    EvalTask(
        "write-tests",
        {"slug.py": "def slugify(title):\n    return '-'.join(title.lower().split())\n"},
        "Create test_slug.py with at least two pytest test functions for slugify.",
        "import ast, pathlib\ntree = ast.parse(pathlib.Path('test_slug.py').read_text())\n"
        "names = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]\n"
        "assert sum(name.startswith('test') for name in names) >= 2\n"
        "ns = {}\nexec(pathlib.Path('test_slug.py').read_text(), ns)\n"
        "[ns[name]() for name in names if name.startswith('test')]\n",
    ),
    EvalTask(
        "change-message",
        {"greet.py": "def greet(name):\n    return 'Hello ' + name\n"},
        "Make greet return 'Hello, <name>!' with a comma and an exclamation mark.",
        "from greet import greet\nassert greet('Ada') == 'Hello, Ada!'\n",
    ),
)
