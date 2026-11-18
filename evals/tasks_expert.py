"""Loads the expert evaluation tasks from the fixture folders under evals/expert.
Each folder holds prompt.txt, a hidden check.py, the starting project/ and a reference solution/ overlay
(plus solution-removes.txt for files the solution deletes); the folders exist because the hard set saturated at 20/20.
An ExpertTask carries its project folder as `origin`, which the runner passes to the check as EVAL_ORIGIN so a
check can restore the visible tests before running them.
"""

from dataclasses import dataclass
from pathlib import Path

from evals.tasks import EvalTask

EXPERT_ROOT = Path(__file__).resolve().parent / "expert"
PROMPT_FILE = "prompt.txt"
CHECK_FILE = "check.py"
PROJECT_DIR = "project"
SOLUTION_DIR = "solution"
SOLUTION_REMOVES_FILE = "solution-removes.txt"
ORIGIN_ENV = "EVAL_ORIGIN"
SKIPPED_DIRS = frozenset({"__pycache__"})


@dataclass(frozen=True)
class ExpertTask(EvalTask):
    origin: str


def read_tree(root: Path) -> dict[str, str]:
    """Every text file under `root` by its relative POSIX path, in sorted order."""
    return {
        path.relative_to(root).as_posix(): path.read_text()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not SKIPPED_DIRS & set(path.relative_to(root).parts)
    }


def solution_removes(folder: Path) -> tuple[str, ...]:
    """Project paths the reference solution deletes; empty when the task has no removal list."""
    listing = folder / SOLUTION_REMOVES_FILE
    return tuple(line.strip() for line in listing.read_text().splitlines() if line.strip()) if listing.exists() else ()


def load_expert_tasks(root: Path = EXPERT_ROOT) -> tuple[ExpertTask, ...]:
    """One task per folder of `root` that holds a prompt, in name order."""
    return tuple(
        ExpertTask(
            folder.name,
            read_tree(folder / PROJECT_DIR),
            (folder / PROMPT_FILE).read_text().strip(),
            (folder / CHECK_FILE).read_text(),
            str(folder / PROJECT_DIR),
        )
        for folder in sorted(root.iterdir())
        if (folder / PROMPT_FILE).is_file()
    )
