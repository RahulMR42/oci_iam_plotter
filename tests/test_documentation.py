"""Consistency checks for user-facing project documentation."""

from pathlib import Path
import re


ROOT = Path(__file__).parents[1]


def test_readme_local_links_exist() -> None:
    """Keep relative README links from drifting away from project files."""
    content = (ROOT / "README.md").read_text(encoding="utf-8")
    targets = re.findall(r"\[[^]]+\]\(([^)]+)\)", content)
    local_targets = [target.split("#", 1)[0] for target in targets
                     if target and not target.startswith(("http://", "https://", "#"))]
    assert local_targets
    assert all((ROOT / target).exists() for target in local_targets)


def test_docs_match_multi_focus_and_pdf_features() -> None:
    """Protect the main documentation from stale single-focus/report wording."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    skills = (ROOT / "SKILLS.md").read_text(encoding="utf-8")
    assert "one or more subjects" in readme
    assert "zero, one, or multiple users" in readme
    assert "Markdown and PDF" in readme
    assert "one or more selected entities" in skills
    assert "paginated PDF" in skills
