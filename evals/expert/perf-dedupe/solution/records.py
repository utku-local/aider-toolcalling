"""Reference solution: duplicate detection for customer records.
Two records are duplicates when their normalized emails match, or when their normalized names and zip codes match.
Duplicates are transitive: if A matches B and B matches C, all three form one group.
"""

import re

SPACES = re.compile(r"\s+")
GMAIL_DOMAINS = ("gmail.com", "googlemail.com")
Record = dict[str, str]


def normalize_email(email: str) -> str:
    """Lower case; for Gmail, dots and a +suffix in the local part are ignored."""
    local, _, domain = email.strip().lower().partition("@")
    if domain in GMAIL_DOMAINS:
        local = local.split("+")[0].replace(".", "")
        domain = GMAIL_DOMAINS[0]
    return f"{local}@{domain}"


def normalize_name(name: str) -> str:
    return SPACES.sub(" ", name.strip().lower())


def is_duplicate(first: Record, second: Record) -> bool:
    if first["email"] and normalize_email(first["email"]) == normalize_email(second["email"]):
        return True
    return (normalize_name(first["name"]), first["zip"]) == (normalize_name(second["name"]), second["zip"])


def find_duplicates(records: list[Record]) -> list[list[int]]:
    """Groups of indexes of duplicate records.

    Only groups with at least two records are returned. Indexes inside a group are ascending and the groups are
    ordered by their smallest index. A record with an empty email can match by name and zip only.
    """
    parent = list(range(len(records)))

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    seen: dict[tuple, int] = {}
    for index, record in enumerate(records):
        keys = [("name", normalize_name(record["name"]), record["zip"])]
        if record["email"]:
            keys.append(("email", normalize_email(record["email"])))
        for key in keys:
            if key in seen:
                low, high = sorted((root(seen[key]), root(index)))
                parent[high] = low
            else:
                seen[key] = index
    groups: dict[int, list[int]] = {}
    for index in range(len(records)):
        groups.setdefault(root(index), []).append(index)
    return [group for group in groups.values() if len(group) > 1]
