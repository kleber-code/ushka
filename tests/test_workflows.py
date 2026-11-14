"""Static checks on the GitHub Actions workflows.

The docs deployment silently failed for weeks because a step key was spelled
`name of:` instead of `name:`. GitHub accepts the file, then aborts the run in
zero seconds with a workflow-syntax error and no job log, so nothing here is
covered by the runtime tests.
"""

from pathlib import Path

import pytest
import yaml

WORKFLOW_DIR = Path(__file__).resolve().parent.parent / ".github" / "workflows"
WORKFLOWS = sorted(WORKFLOW_DIR.glob("*.yml")) + sorted(WORKFLOW_DIR.glob("*.yaml"))

# Keys GitHub accepts on a single step.
STEP_KEYS = {
    "id",
    "if",
    "name",
    "uses",
    "run",
    "shell",
    "with",
    "env",
    "working-directory",
    "continue-on-error",
    "timeout-minutes",
}


def _load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_there_is_at_least_one_workflow():
    assert WORKFLOWS


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_workflow_is_valid_yaml(path):
    assert isinstance(_load(path), dict)


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_workflow_declares_jobs_with_steps(path):
    workflow = _load(path)

    assert workflow.get("jobs"), f"{path.name} declares no jobs"
    for job_name, job in workflow["jobs"].items():
        assert "runs-on" in job, f"{path.name}:{job_name} has no runner"
        assert job.get("steps"), f"{path.name}:{job_name} has no steps"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_every_step_uses_only_known_keys(path):
    workflow = _load(path)

    for job_name, job in workflow["jobs"].items():
        for index, step in enumerate(job["steps"]):
            unknown = set(step) - STEP_KEYS
            assert not unknown, (
                f"{path.name}:{job_name} step {index} has unknown key(s) "
                f"{sorted(unknown)} - a typo such as 'name of:' silently "
                f"breaks the whole workflow"
            )
            assert "uses" in step or "run" in step, (
                f"{path.name}:{job_name} step {index} neither runs a command "
                f"nor uses an action"
            )


def test_ci_checks_the_docs_with_ushka_docs():
    """The docs are rendered by ushka.docs; CI must fail on broken links."""
    workflow = _load(WORKFLOW_DIR / "ci.yml")
    steps = workflow["jobs"]["docs"]["steps"]
    assert any("ushka docs check" in str(step.get("run", "")) for step in steps)
    assert not any("mkdocs" in str(step.get("run", "")) for step in steps)
