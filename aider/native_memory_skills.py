"""Project memory and skills for the agent: what it learned last time, and reusable instructions it can load.
remember appends a dated note to .aider-agent/memory.md, which the next session reads as project instructions.
Skills are Markdown files in .aider-agent/skills/ (project) or ~/.aider-agent/skills/ (user, overridden by a project
skill of the same name); their first line is the description listed for the model, and use_skill returns the rest.
"""

from datetime import date
from pathlib import Path

from aider.native_toolcalling import NativeToolError, NativeToolRegistry

AGENT_DIR = ".aider-agent"
MEMORY_FILE = Path(AGENT_DIR) / "memory.md"
SKILLS_DIR = Path(AGENT_DIR) / "skills"
SKILL_SUFFIX = ".md"
ENCODING = "utf-8"
MAX_NOTE_CHARS = 1_000
MAX_SKILL_CHARS = 20_000
MEMORY_HEADER = "# Agent memory\n\nNotes the agent saved for later sessions in this project.\n"
SKILLS_HEADING = "Skills you can load with use_skill (name: what it is for):"
NO_SKILLS = "No skills found. Add Markdown files to .aider-agent/skills/ or ~/.aider-agent/skills/."
NO_REQUEST = "Apply this skill to the project now."
REMEMBER_PARAMETERS = {
    "type": "object",
    "properties": {"note": {"type": "string", "description": "One line."}},
    "required": ["note"],
}
SKILL_PARAMETERS = {
    "type": "object",
    "properties": {"name": {"type": "string", "description": "The skill's name, as listed in your instructions."}},
    "required": ["name"],
}


class MemorySkillError(NativeToolError):
    """Raised for an empty or oversized note, or an unknown skill."""


def remember(root: Path, note: str, today: date) -> str:
    text = " ".join(note.split())
    if not text or len(text) > MAX_NOTE_CHARS:
        raise MemorySkillError(f"note must be one line of 1 to {MAX_NOTE_CHARS} characters")
    path = root / MEMORY_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding=ENCODING) if path.is_file() else MEMORY_HEADER
    path.write_text(existing.rstrip("\n") + f"\n- {today.isoformat()}: {text}\n", encoding=ENCODING)
    return f"Saved to {MEMORY_FILE}; later sessions will read it."


def find_skills(root: Path, home: Path) -> dict[str, Path]:
    """Skill name -> file; a project skill wins over a user skill with the same name."""
    found: dict[str, Path] = {}
    for folder in (home / SKILLS_DIR, root / SKILLS_DIR):
        if folder.is_dir():
            for path in sorted(folder.glob(f"*{SKILL_SUFFIX}")):
                found[path.stem] = path
    return found


def skill_description(path: Path) -> str:
    lines = path.read_text(encoding=ENCODING, errors="replace").splitlines()
    first = next((line for line in lines if line.strip()), "")
    return first.lstrip("# ").strip()


def skills_listing(skills: dict[str, Path]) -> str:
    """The system-prompt section naming the skills; empty when there are none."""
    if not skills:
        return ""
    lines = [f"- {name}: {skill_description(path)}" for name, path in sorted(skills.items())]
    return "\n".join([SKILLS_HEADING, *lines]) + "\n"


def use_skill(skills: dict[str, Path], name: str) -> str:
    path = skills.get(name.strip())
    if path is None:
        raise MemorySkillError(f"Unknown skill {name!r}; available: {sorted(skills) or 'none'}")
    text = path.read_text(encoding=ENCODING, errors="replace")[:MAX_SKILL_CHARS]
    return f"Skill {name}. Follow these instructions for the current task:\n\n{text}"


def skill_message(skills: dict[str, Path], args: str) -> tuple[str, str]:
    """For /skill: (listing, "") when no name is given, else ("", the request that loads the skill and asks for args)."""
    name, _, request = args.strip().partition(" ")
    if not name:
        return (skills_listing(skills) or NO_SKILLS), ""
    return "", use_skill(skills, name) + "\n\nRequest: " + (request.strip() or NO_REQUEST)


def register_memory_skill_tools(registry: NativeToolRegistry, root: Path, skills: dict[str, Path]) -> None:
    registry.register(
        "remember",
        "Save one durable project fact (a convention, a working command, a pitfall) for later sessions; no "
        "secrets.",
        REMEMBER_PARAMETERS,
        lambda note: remember(root, note, date.today()),
    )
    if skills:
        registry.register("use_skill", "Load a skill's instructions by name.", SKILL_PARAMETERS,
                          lambda name: use_skill(skills, name))
