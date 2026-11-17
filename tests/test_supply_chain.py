"""The CI and release workflows stay hardened: a regression here fails the build."""

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOWS = sorted((Path(__file__).resolve().parent.parent / ".github" / "workflows").glob("*.yml"))
PINNED = re.compile(r"^[\w.\-]+/[\w./\-]+@[0-9a-f]{40}$")
# Values a stranger can influence (PR titles, branch names, issue text): never inline them in a script.
INJECTABLE = re.compile(r"\$\{\{\s*(github\.event\.|github\.head_ref|inputs\.)")


def steps(workflow: dict):
    for job in workflow["jobs"].values():
        yield from job.get("steps", [])


def test_there_are_workflows():
    assert WORKFLOWS, "expected .github/workflows/*.yml"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_every_action_is_pinned_to_a_commit_sha(path):
    for step in steps(yaml.safe_load(path.read_text())):
        uses = step.get("uses")
        if uses and not uses.startswith("./"):
            assert PINNED.match(uses), f"{path.name}: '{uses}' must be pinned to a full commit SHA (a tag can be moved)"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_scripts_never_inline_attacker_controlled_expressions(path):
    for step in steps(yaml.safe_load(path.read_text())):
        run = step.get("run", "")
        assert not INJECTABLE.search(run), f"{path.name}: pass '{INJECTABLE.search(run).group(0)}' through env:, not inside run:"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_workflows_declare_permissions_and_avoid_pull_request_target(path):
    workflow = yaml.safe_load(path.read_text())
    assert "permissions" in workflow, f"{path.name}: set top-level permissions (least privilege)"
    triggers = workflow.get(True, workflow.get("on", {}))  # YAML reads a bare `on` as True
    assert "pull_request_target" not in (triggers if isinstance(triggers, (dict, list)) else [triggers])


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_checkouts_do_not_keep_the_token(path):
    for step in steps(yaml.safe_load(path.read_text())):
        if str(step.get("uses", "")).startswith("actions/checkout@"):
            assert step.get("with", {}).get("persist-credentials") is False, f"{path.name}: checkout must set persist-credentials: false"


def test_release_attests_and_publishes_with_trusted_publishing():
    release = yaml.safe_load((WORKFLOWS[0].parent / "python-publish.yml").read_text())
    used = " ".join(s.get("uses", "") for s in steps(release))
    assert "actions/attest-build-provenance@" in used and "actions/attest-sbom@" in used
    publish = release["jobs"]["pypi-publish"]
    assert publish["permissions"] == {"id-token": "write"}  # nothing else: no stored token
    assert publish["steps"][-1]["with"]["attestations"] is True
    # the job that publishes cannot be the job that builds
    assert "release-build" in publish["needs"] and "attest" in publish["needs"]


def test_dependabot_keeps_the_pins_current():
    config = yaml.safe_load((WORKFLOWS[0].parent.parent / "dependabot.yml").read_text())
    assert {u["package-ecosystem"] for u in config["updates"]} >= {"github-actions", "pip"}


def test_lockfile_covers_the_declared_groups():
    lock = (Path(__file__).resolve().parent.parent / "pdm.lock").read_text()
    assert 'groups = ["default", "crypto", "dev", "docs", "orm"]' in lock and "sha256:" in lock  # hashes of every file
