"""Duplicate detection for customer records.
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
    groups = [[index] for index in range(len(records))]
    merged = True
    while merged:
        merged = False
        for first in range(len(groups)):
            for second in range(first + 1, len(groups)):
                if any(is_duplicate(records[a], records[b]) for a in groups[first] for b in groups[second]):
                    groups[first] = sorted(groups[first] + groups[second])
                    del groups[second]
                    merged = True
                    break
            if merged:
                break
    return sorted((group for group in groups if len(group) > 1), key=lambda group: group[0])
