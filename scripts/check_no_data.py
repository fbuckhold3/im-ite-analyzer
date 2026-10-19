"""Fail if files about to be committed look like resident or program data.

Usage: python scripts/check_no_data.py FILE [FILE ...]   (pre-commit passes staged files; CI passes git ls-files)

Blocks: data file types; email addresses; 7-digit numbers (ACP Candidate IDs are 7 digits); and any term
listed in an optional, gitignored `.data-guard-local.txt` (one term per line, e.g. your institution's name).
Reports file:line and the rule only — never the matched value, so CI logs don't echo data.
"""

import re
import sys
from pathlib import Path

BLOCKED_EXT = {".xlsx", ".xls", ".csv", ".pdf", ".rds", ".sav", ".dta", ".parquet", ".feather", ".html"}
SKIP_CONTENT = {"LICENSE"}  # official license text
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
EMAIL_OK = re.compile(r"@(example\.(com|org)|users\.noreply\.github\.com)$|^noreply@", re.I)
CANDIDATE_ID = re.compile(r"(?<![\w.-])\d{7}(?![\w.-])")  # standalone, not inside a hash or code

root = Path(__file__).resolve().parents[1]
local = root / ".data-guard-local.txt"
TERMS = (
    [t.strip() for t in local.read_text().splitlines() if t.strip() and not t.startswith("#")] if local.exists() else []
)
TERM_RE = re.compile("|".join(rf"\b{re.escape(t)}\b" for t in TERMS), re.I) if TERMS else None


def scan(path: Path) -> list[str]:
    if path.suffix.lower() in BLOCKED_EXT:
        return [f"{path}: data file type {path.suffix} is not allowed in this repo"]
    if path.name in SKIP_CONTENT or not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    problems = []
    for n, line in enumerate(text.splitlines(), 1):
        if any(not EMAIL_OK.search(m) for m in EMAIL.findall(line)):
            problems.append(f"{path}:{n}: email address")
        if CANDIDATE_ID.search(line):
            problems.append(f"{path}:{n}: 7-digit number (possible ACP Candidate ID)")
        if TERM_RE and TERM_RE.search(line):
            problems.append(f"{path}:{n}: term from .data-guard-local.txt")
    return problems


def main(argv: list[str]) -> int:
    problems = [p for f in argv for p in scan(Path(f))]
    for p in problems:
        print(p)
    if problems:
        print(
            f"\n{len(problems)} problem(s). Remove the data, or (if a false positive) adjust scripts/check_no_data.py."
        )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
