"""Write approved levels into the frontend learner sequence.

This is the demo bridge between the admin pipeline and the learner app. The canonical publish still
goes to SQLite; after that gated write succeeds, we also write the generated `GameLevel.tsx` into
the Vite frontend and rebuild the static `LEVELS` registry. When Vite dev is running, the app hot
reloads and the new lesson is immediately playable.
"""

import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
LEVELS_DIR = REPO_ROOT / "frontend" / "src" / "game" / "levels"
MANIFEST_PATH = LEVELS_DIR / "published-levels.json"
INDEX_PATH = LEVELS_DIR / "index.ts"

BASE_LEVEL = {
    "number": 1,
    "id": "lesson-1-see",
    "title": "Teach Your Robot to See",
    "file": "./lesson1-see",
    "component": "Lesson1",
}


def _slug(text: str, fallback: str = "generated") -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:34] or fallback


def _manifest_path(levels_dir: Path) -> Path:
    return levels_dir / MANIFEST_PATH.name


def _index_path(levels_dir: Path) -> Path:
    return levels_dir / INDEX_PATH.name


def _load_generated(levels_dir: Path = LEVELS_DIR) -> list[dict[str, Any]]:
    path = _manifest_path(levels_dir)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return sorted((dict(item) for item in data), key=lambda item: int(item.get("number", 0)))


def _save_generated(entries: list[dict[str, Any]], levels_dir: Path = LEVELS_DIR) -> None:
    _manifest_path(levels_dir).write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _component_name(number: int) -> str:
    return f"Lesson{number}"


def _render_index(generated: list[dict[str, Any]]) -> str:
    entries = [BASE_LEVEL, *generated]
    imports = "\n".join(f'import {entry["component"]} from "{entry["file"]}";' for entry in entries)
    rows = []
    for entry in entries:
        rows.append(
            "  {\n"
            f'    id: "{entry["id"]}",\n'
            f'    title: "{entry["title"]}",\n'
            f'    Component: {entry["component"]},\n'
            "  },"
        )
    return (
        'import type { ComponentType } from "react";\n'
        'import type { GameLevelProps } from "../types";\n'
        f"{imports}\n\n"
        "export interface LevelEntry {\n"
        "  id: string;\n"
        "  title: string;\n"
        "  Component: ComponentType<GameLevelProps>;\n"
        "}\n\n"
        "export const LEVELS: LevelEntry[] = [\n"
        + "\n".join(rows)
        + "\n];\n"
    )


def rebuild_levels_index(levels_dir: Path = LEVELS_DIR) -> None:
    """Regenerate the learner app's level registry from Lesson 1 + generated published levels."""
    generated = _load_generated(levels_dir)
    _index_path(levels_dir).write_text(_render_index(generated), encoding="utf-8")


def publish_to_frontend_level(spec: dict[str, Any], code: str, levels_dir: Path = LEVELS_DIR) -> dict[str, Any]:
    """Append the approved generated code as the next sequential learner lesson."""
    if not code.strip():
        raise ValueError("cannot add an empty generated level to the frontend")

    levels_dir.mkdir(parents=True, exist_ok=True)
    generated = _load_generated(levels_dir)
    next_number = max([BASE_LEVEL["number"], *(int(item["number"]) for item in generated)], default=1) + 1

    title = str(spec.get("title") or f"Lesson {next_number}")
    slug = _slug(title or spec.get("concept") or f"lesson-{next_number}")
    filename = f"lesson{next_number}-{slug}.tsx"
    component = _component_name(next_number)
    entry = {
        "number": next_number,
        "id": f"lesson-{next_number}-{slug}",
        "title": title,
        "file": f"./{filename.removesuffix('.tsx')}",
        "component": component,
    }

    (levels_dir / filename).write_text(code.rstrip() + "\n", encoding="utf-8")
    generated.append(entry)
    _save_generated(generated, levels_dir)
    rebuild_levels_index(levels_dir)

    return {
        "lesson_number": next_number,
        "id": entry["id"],
        "title": title,
        "path": str(levels_dir / filename),
    }
