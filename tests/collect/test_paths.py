from pathlib import Path

import pytest

from winnow.collect.paths import relative_posix


def test_windows_absolute_path_becomes_repo_relative_posix():
    root = Path(r"C:\dev\winnow\data\mobx\repo")
    given = r"C:\dev\winnow\data\mobx\repo\packages\mobx\__tests__\v5\base\api.js"

    assert relative_posix(root, given) == "packages/mobx/__tests__/v5/base/api.js"


def test_posix_absolute_path_becomes_repo_relative():
    root = Path("/home/e/winnow/data/mobx/repo")
    given = "/home/e/winnow/data/mobx/repo/packages/mobx/src/api.ts"

    assert relative_posix(root, given) == "packages/mobx/src/api.ts"


def test_drive_letter_case_difference_still_matches():
    """node prints a lowercased drive letter on some Windows setups, while
    pathlib keeps whatever the caller wrote. A case-sensitive prefix compare
    would silently store an absolute path and break every later lookup."""
    root = Path(r"C:\dev\winnow\repo")
    given = r"c:\dev\winnow\repo\test\a.test.js"

    assert relative_posix(root, given) == "test/a.test.js"


def test_path_outside_the_repo_root_raises():
    root = Path("/home/e/winnow/data/mobx/repo")

    with pytest.raises(ValueError, match="outside"):
        relative_posix(root, "/etc/passwd")
