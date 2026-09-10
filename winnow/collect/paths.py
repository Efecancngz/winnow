"""One conversion point between jest's absolute host paths and the
repo-relative posix paths every other table stores.

Getting this wrong raises nothing: the selector simply matches no rows,
falls back to the full suite, and reports success. Same failure shape as
the Cobertura backslash defect.
"""

from pathlib import Path


def relative_posix(repo_root: Path, path: str) -> str:
    normalized = str(path).replace("\\", "/")
    root = str(repo_root).replace("\\", "/").rstrip("/")

    # casefold, not ==: node sometimes lowercases the Windows drive letter
    # while pathlib preserves the caller's casing.
    if normalized.casefold().startswith(root.casefold() + "/"):
        return normalized[len(root) + 1 :]

    raise ValueError(f"path {path!r} is outside repo root {repo_root!r}")
