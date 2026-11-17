"""The README is the PyPI page: a broken link there cannot be fixed without a new release."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text("utf-8")


def test_github_file_links_point_to_files_that_exist():
    missing = []
    for path in re.findall(r"https://github\.com/kleber-code/ushka/(?:blob|tree|edit)/main/([^\s)#\"']+)", README):
        if not (ROOT / path).exists():
            missing.append(path)
    assert not missing, f"README links to files that do not exist on main: {missing}"


def test_no_url_is_glued_to_markdown_emphasis():
    # PyPI turns `**https://x/docs/**` into a link that includes the asterisks (a 404)
    glued = re.findall(r"(?:\*\*|__|\*|_)https?://[^\s)]*(?:\*\*|__|\*|_)(?=\s|$|[.,;])", README)
    assert not glued, f"write these as [text](url): {glued}"


def test_relative_links_are_not_used_in_the_readme():
    # relative links work on GitHub and 404 on PyPI
    relative = re.findall(r"\]\((?!https?:|#|mailto:)([^)\s]+)\)", README)
    assert not relative, f"use absolute URLs in the README: {relative}"
