"""Guards the minimum Python version the package claims to support.

`import ushka` was broken on 3.10 because `ushka.utils.flash` imported
`enum.StrEnum`, which only exists from 3.11 on. The failure was invisible
locally (development happens on a newer interpreter) and only showed up on the
oldest entry of the CI matrix.
"""

import re
from pathlib import Path

import tomlkit
import yaml

from ushka.utils.flash import Category

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = tomlkit.parse((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
CI = yaml.safe_load(
    (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
)


def _version_tuple(text):
    return tuple(int(part) for part in text.split("."))


def _requires_python_floor():
    match = re.search(r">=\s*(\d+\.\d+)", PYPROJECT["project"]["requires-python"])
    assert match, "requires-python has no lower bound"
    return _version_tuple(match.group(1))


def test_category_behaves_like_a_str_enum():
    """The 3.10 shim has to keep `StrEnum`'s stringification, not `Enum`'s."""
    assert Category.INFO == "info"
    assert str(Category.INFO) == "info"
    assert f"{Category.DANGER}" == "danger"


def test_ci_matrix_covers_the_oldest_supported_python():
    matrix = CI["jobs"]["test"]["strategy"]["matrix"]["python-version"]
    oldest = min(_version_tuple(str(version)) for version in matrix)

    assert oldest == _requires_python_floor(), (
        "the CI matrix must start at the version `requires-python` promises, "
        "otherwise breakage on the oldest interpreter goes unnoticed"
    )


def test_classifiers_list_every_python_in_the_ci_matrix():
    declared = {
        classifier.rsplit(" :: ", 1)[-1]
        for classifier in PYPROJECT["project"]["classifiers"]
        if classifier.startswith("Programming Language :: Python :: 3.")
    }
    matrix = {str(version) for version in CI["jobs"]["test"]["strategy"]["matrix"]["python-version"]}

    assert matrix <= declared, f"missing classifiers for {sorted(matrix - declared)}"
