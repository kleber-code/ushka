"""Plain, professional text: no em dashes and no emoji in what users and contributors read."""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF\U00002B00-\U00002BFF\U0000FE0F]")
ALLOWED = set("✓✗")  # check mark and ballot x, used in command output
SKIP_SUFFIXES = (".png", ".webp", ".woff2", ".ico", ".gif", ".jpg", ".lock", ".svg")
#: test data that needs real emoji, and the lock file
SKIP_FILES = {"tests/test_imap.py", "tests/test_style.py", "pdm.lock"}


def tracked_text_files():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    for name in out:
        if name.endswith(SKIP_SUFFIXES) or name in SKIP_FILES:
            continue
        path = ROOT / name
        try:
            yield name, path.read_text("utf-8")
        except (UnicodeDecodeError, OSError):
            continue


def test_no_em_dashes_anywhere():
    found = {name: text.count("—") for name, text in tracked_text_files() if "—" in text}
    assert not found, f"em dashes (use a colon, a comma or a full stop): {found}"


def test_no_emoji_anywhere():
    found = {}
    for name, text in tracked_text_files():
        bad = {c for c in EMOJI.findall(text) if c not in ALLOWED}
        if bad:
            found[name] = "".join(sorted(bad))
    assert not found, f"emoji in text users read: {found}"


@pytest.mark.parametrize("name", ["README.md", ".github/CODE_OF_CONDUCT.md", ".github/CONTRIBUTING.md", ".github/SECURITY.md"])
def test_community_files_exist_and_are_plain(name):
    text = (ROOT / name).read_text("utf-8")
    assert re.search(r"^# ", text, re.MULTILINE) and len(text.split()) > 60
