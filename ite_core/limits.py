"""Upload limits for a public app. Every check raises UploadError with a message safe to show users.

Messages never contain file contents (names, IDs, scores) — only file names and counts.
"""

from __future__ import annotations

from pathlib import Path

MAX_FILE_MB = 25  # a whole-program MKSAP export is ~9 MB
MAX_FILES = 12  # rosters per session
MAX_PDF_PAGES = 1500  # composite score-report PDF: ~4-6 pages per resident
MAX_ROSTER_ROWS = 2_000
MAX_MKSAP_ROWS = 3_000_000  # ~3,200 rows per MKSAP account

ROSTER_EXT = {".xlsx", ".xls", ".csv"}
MKSAP_EXT = {".csv"}
PDF_EXT = {".pdf"}
CROSSWALK_EXT = {".csv"}

ISSUE_HINT = (
    "If this is a genuine ACP or MKSAP file, the format may have changed — please open an issue at "
    "github.com/fbuckhold3/im-ite-analyzer/issues describing the columns (not the data)."
)


class UploadError(ValueError):
    """A problem with an uploaded file, phrased for the person who uploaded it."""


def check_file(name: str, nbytes: int, allowed: set[str], kind: str) -> None:
    ext = Path(name).suffix.lower()
    if ext not in allowed:
        raise UploadError(f"“{name}” is not a {kind} file (expected {', '.join(sorted(allowed))}).")
    if nbytes > MAX_FILE_MB * 1024 * 1024:
        raise UploadError(f"“{name}” is {nbytes / 1024 / 1024:.0f} MB; the limit is {MAX_FILE_MB} MB.")
    if nbytes == 0:
        raise UploadError(f"“{name}” is empty.")


def check_rows(name: str, n: int, limit: int) -> None:
    if n > limit:
        raise UploadError(f"“{name}” has more than {limit:,} rows — that is larger than any expected export.")


def check_pages(name: str, n: int) -> None:
    if n > MAX_PDF_PAGES:
        raise UploadError(f"“{name}” has {n:,} pages; the limit is {MAX_PDF_PAGES:,}.")
