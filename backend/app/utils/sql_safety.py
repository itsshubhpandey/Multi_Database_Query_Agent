from __future__ import annotations

import re

DANGEROUS_PATTERNS = (
    r"\bdrop\s+database\b",
    r"\btruncate\b",
    r"\balter\s+server\b",
    r"\bshutdown\b",
    r"\bbackup\s+database\b",
    r"\brestore\s+database\b",
    r"\bxp_cmdshell\b",
)
WRITE_WITHOUT_WHERE = re.compile(r"\b(update|delete)\b(?![\s\S]*\bwhere\b)", re.IGNORECASE)


def validate_sql_safety(sql: str) -> tuple[bool, str | None]:
    normalized = sql.strip()
    if not normalized:
        return False, "SQL query is empty."
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE):
            return False, "Blocked unsafe SQL operation."
    if WRITE_WITHOUT_WHERE.search(normalized):
        return False, "UPDATE/DELETE queries must include a WHERE clause."
    return True, None


def looks_like_sql(text: str) -> bool:
    first = text.strip().split(None, 1)[0].lower().rstrip(";") if text.strip() else ""
    return first in {"select", "with", "insert", "update", "delete", "create", "alter", "drop"}
