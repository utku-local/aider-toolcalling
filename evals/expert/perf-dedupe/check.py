"""Hidden check for the perf-dedupe task.
It compares find_duplicates with a slow reference on random records, then times it on 100,000 records.
Exit code 0 means the task passed; an alarm ends the check when the code under test is still slow.
"""

import random
import signal
import time

import records

LIMIT_SECONDS = 3
BIG = 100_000
NAMES = ("Ada Lovelace", "ada  lovelace", "Alan Turing", "Grace Hopper", " grace hopper", "Linus T", "Edsger D")
ZIPS = ("10115", "80331", "20095")
# The whole check takes about two seconds on a fast solution; the unfixed code would run for hours.
CHECK_BUDGET_SECONDS = 10
signal.alarm(CHECK_BUDGET_SECONDS)


def make(rng: random.Random, count: int, people: int) -> list[dict]:
    rows = []
    for _ in range(count):
        person = rng.randrange(people)
        local = f"user{person}"
        if rng.random() < 0.3:
            local = f"{local[:2]}.{local[2:]}+tag{rng.randrange(9)}"
        domain = rng.choice(("gmail.com", "googlemail.com", "corp.example"))
        email = "" if rng.random() < 0.2 else f"{local.upper() if rng.random() < 0.2 else local}@{domain}"
        rows.append({"name": f"{rng.choice(NAMES)} {rng.randrange(people)}", "zip": rng.choice(ZIPS), "email": email})
    return rows


def same(first: dict, second: dict) -> bool:
    if first["email"] and records.normalize_email(first["email"]) == records.normalize_email(second["email"]):
        return True
    return (records.normalize_name(first["name"]), first["zip"]) == (
        records.normalize_name(second["name"]), second["zip"])


def reference(rows: list[dict]) -> list[list[int]]:
    group_of = list(range(len(rows)))
    changed = True
    while changed:
        changed = False
        for a in range(len(rows)):
            for b in range(a + 1, len(rows)):
                if group_of[a] != group_of[b] and same(rows[a], rows[b]):
                    low, high = sorted((group_of[a], group_of[b]))
                    group_of = [low if g == high else g for g in group_of]
                    changed = True
    groups: dict[int, list[int]] = {}
    for index, group in enumerate(group_of):
        groups.setdefault(group, []).append(index)
    return sorted((g for g in groups.values() if len(g) > 1), key=lambda g: g[0])


assert records.normalize_email(" A.b+x@GoogleMail.com ") == "ab@gmail.com"
assert records.find_duplicates([]) == []
chain = [
    {"name": "Ann", "zip": "1", "email": "ann@corp.example"},
    {"name": "Bob", "zip": "2", "email": ""},
    {"name": "ANN", "zip": "1", "email": "a.n.n@gmail.com"},
    {"name": "Bob", "zip": "2", "email": ""},
    {"name": "Zed", "zip": "9", "email": "ann+x@googlemail.com"},
    {"name": "Solo", "zip": "5", "email": ""},
]
assert records.find_duplicates(chain) == [[0, 2, 4], [1, 3]], records.find_duplicates(chain)
for seed in range(6):
    rng = random.Random(seed)
    rows = make(rng, 220, rng.choice((15, 60, 200)))
    assert records.find_duplicates(rows) == reference(rows), seed

big = make(random.Random(99), BIG, 40_000)
started = time.perf_counter()
result = records.find_duplicates(big)
elapsed = time.perf_counter() - started
assert elapsed < LIMIT_SECONDS, elapsed
assert result == sorted(result, key=lambda g: g[0]) and all(g == sorted(g) and len(g) > 1 for g in result)
assert sum(len(g) for g in result) > BIG // 2
