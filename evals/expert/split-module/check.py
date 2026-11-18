"""Hidden check for the split-module task.
It restores and runs the visible tests, then checks the package layout, the import direction and the report output.
Exit code 0 means the task passed.
"""

import ast
import json
import os
import pathlib
import shutil
import subprocess
import sys

ORIGIN = os.environ.get("EVAL_ORIGIN", "")
if ORIGIN:
    shutil.copy(pathlib.Path(ORIGIN) / "tests" / "test_shop.py", "tests/test_shop.py")
assert not pathlib.Path("shop.py").exists(), "shop.py still exists"
tests = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."], capture_output=True)
assert tests.returncode == 0, tests.stderr.decode()

WHERE = {
    "models": {"ShopError", "Product", "OrderLine", "Order"},
    "storage": {"Storage"},
    "reports": {"report_totals", "report_top_products", "format_report"},
}


def defined(module: str) -> set[str]:
    tree = ast.parse(pathlib.Path("shop", f"{module}.py").read_text())
    return {node.name for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef))}


def imported(module: str) -> set[str]:
    tree = ast.parse(pathlib.Path("shop", f"{module}.py").read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return names


for module, names in WHERE.items():
    assert names <= defined(module), (module, names - defined(module))
    others = set().union(*(other for key, other in WHERE.items() if key != module))
    assert not others & defined(module), (module, others & defined(module))
assert not {"shop.storage", "shop.reports", "storage", "reports"} & imported("models"), imported("models")

import shop  # noqa: E402

for names in WHERE.values():
    for name in names:
        assert hasattr(shop, name), name
assert shop.Storage.__module__ == "shop.storage" and shop.Order.__module__ == "shop.models"

data = {
    "products": [{"sku": "p1", "name": "Pen", "price_cents": 150}, {"sku": "n1", "name": "Notebook", "price_cents": 499}],
    "orders": [
        {"order_id": 1, "customer": "ada", "lines": [{"sku": "p1", "quantity": 4}]},
        {"order_id": 2, "customer": "bob", "lines": [{"sku": "n1", "quantity": 4}]},
    ],
}
pathlib.Path("check-book.json").write_text(json.dumps(data))
done = subprocess.run([sys.executable, "-m", "shop", "check-book.json"], capture_output=True, text=True)
assert done.returncode == 0, done.stderr
assert done.stdout == "Customers\n  ada: 6.00 EUR\n  bob: 19.96 EUR\nTop products\n  Notebook x4\n  Pen x4\n", done.stdout
missing = subprocess.run([sys.executable, "-m", "shop", "nope.json"], capture_output=True, text=True)
assert missing.returncode == 1 and missing.stderr.startswith("Error: cannot read"), missing.stderr
