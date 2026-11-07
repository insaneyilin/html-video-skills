"""Project validation and audio-timing invariants shared by the workflow tools."""

import hashlib
import json
import math
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    """Read UTF-8 JSON.

    Args:
        path: Input file path.

    Returns:
        Parsed JSON value.
    """
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    """Atomically write readable UTF-8 JSON.

    Args:
        path: Destination path.
        value: JSON-serializable value.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".pending")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def fingerprint(value):
    """Hash canonical JSON for cache identity.

    Args:
        value: JSON-serializable configuration or source data.

    Returns:
        Hexadecimal SHA-256 digest.
    """
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def normalized(text):
    """Normalize transcript characters for alignment matching.

    Args:
        text: Script or recognized text.

    Returns:
        Lowercase Unicode letters and numbers, without punctuation.
    """
    return "".join(
        c for c in unicodedata.normalize("NFKC", text).lower() if c.isalnum()
    )


def source_signature(root):
    """Hash manifest bytes consistently across Python and JavaScript.

    Args:
        root: Project directory.

    Returns:
        SHA-256 digest of project.json.
    """
    return hashlib.sha256((Path(root) / "project.json").read_bytes()).hexdigest()


def inside(root, relative):
    """Resolve a project-relative path without escaping through symlinks.

    Args:
        root: Project root.
        relative: Relative asset or output path.

    Returns:
        Resolved path inside the project.

    Raises:
        ValueError: If the path is absolute or escapes the project.
    """
    root = Path(root).resolve()
    if (
        not isinstance(relative, str)
        or not relative
        or "\\" in relative
        or Path(relative).is_absolute()
    ):
        raise ValueError("Expected a project-relative path")
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Path leaves the project")
    return target


def load_project(root):
    """Validate the editable project manifest.

    Args:
        root: Project directory.

    Returns:
        Validated project dictionary.

    Raises:
        ValueError: If required values or scene identities are invalid.
    """
    p = read_json(Path(root) / "project.json")
    if (
        p.get("version") != 1
        or not isinstance(p.get("title"), str)
        or not p["title"].strip()
    ):
        raise ValueError("Expected project version 1 and a title")
    scenes = p.get("scenes", [])
    if not scenes:
        raise ValueError("At least one scene is required")
    ids = set()
    for scene in scenes:
        key = scene.get("id", "")
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", key) or key in ids:
            raise ValueError("Scene IDs must be unique lowercase identifiers")
        ids.add(key)
        lines = scene.get("narration")
        if (
            not isinstance(lines, list)
            or not lines
            or not all(isinstance(s, str) and s.strip() for s in lines)
        ):
            raise ValueError(f"Scene {key} needs nonempty narration lines")
        if scene.get("kind", "steps") not in [
            "title",
            "steps",
            "image",
            "video",
            "code",
        ]:
            raise ValueError(f"Unsupported scene kind: {scene.get('kind')}")
        if scene.get("kind") in ["image", "video"]:
            inside(root, scene.get("media"))
        if scene.get("poster"):
            inside(root, scene["poster"])
    video = p.get("video", {})
    if video.get("fps") not in [24, 25, 30, 60]:
        raise ValueError("Supported frame rates: 24, 25, 30, 60")
    for dimension in ["width", "height"]:
        n = video.get(dimension)
        if not isinstance(n, int) or n < 240 or n > 3840 or n % 2:
            raise ValueError(
                "Video dimensions must be even integers between 240 and 3840"
            )
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", video.get("accent", "#087f68")):
        raise ValueError("Accent must be a six-digit hex color")
    if not isinstance(p.get("voice"), dict) or not isinstance(p.get("alignment"), dict):
        raise ValueError("Voice and alignment configuration are required")
    for key in ["pre_roll_seconds", "end_hold_seconds"]:
        value = p["alignment"].get(key)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"Invalid {key}")
    plan_groups(p)
    return p


def plan_groups(project):
    """Group adjacent scenes while preserving order and a bounded text budget.

    Args:
        project: Manifest with scenes, voice configuration and optional groups.

    Returns:
        Ordered lists of scene IDs; group count is not fixed.

    Raises:
        ValueError: If explicit groups reorder/duplicate scenes, or a scene
            exceeds the configured text budget.
    """
    scenes = project["scenes"]
    ids = [s["id"] for s in scenes]
    budget = project["voice"].get("max_group_chars", 200)
    if not isinstance(budget, int) or budget < 20:
        raise ValueError("max_group_chars must be an integer of at least 20")
    sizes = {s["id"]: len(" ".join(s["narration"])) for s in scenes}
    if "groups" in project:
        groups = project["groups"]
        if not isinstance(groups, list) or any(
            not isinstance(g, list) or not g for g in groups
        ):
            raise ValueError("groups must contain nonempty lists")
        if [key for group in groups for key in group] != ids:
            raise ValueError(
                "Groups must cover every scene exactly once in scene order"
            )
        if any(sum(sizes[k] for k in group) > budget for group in groups):
            raise ValueError(
                "A group exceeds max_group_chars; split it or adjust the budget"
            )
        return groups
    groups, current, size = [], [], 0
    for key in ids:
        if sizes[key] > budget:
            raise ValueError(
                f"Scene {key} exceeds the narration budget; split its script or adjust the budget"
            )
        if current and size + sizes[key] > budget:
            groups.append(current)
            current, size = [], 0
        current.append(key)
        size += sizes[key]
    if current:
        groups.append(current)
    return groups


def run(command):
    """Run a utility without shell interpolation.

    Args:
        command: Executable and argument list.

    Returns:
        Captured standard output.

    Raises:
        RuntimeError: If the process fails, with a bounded diagnostic message.
    """
    result = subprocess.run([str(x) for x in command], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"{command[0]} failed: {result.stderr[-1800:]}")
    return result.stdout


def init_project(root):
    """Copy the synthetic starter into a new project without overwriting files.

    Args:
        root: New or empty destination directory.

    Raises:
        ValueError: If the destination contains existing files.
    """
    root = Path(root)
    if root.exists() and any(root.iterdir()):
        raise ValueError("Initialization requires a new or empty project directory")
    shutil.copytree(SKILL_ROOT / "assets/starter", root, dirs_exist_ok=True)


def subtitle_time(seconds, separator=","):
    """Format a nonnegative time for SRT or VTT.

    Args:
        seconds: Time in seconds.
        separator: Millisecond separator.

    Returns:
        Hours, minutes, seconds and milliseconds.
    """
    ms = round(seconds * 1000)
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02}{separator}{ms % 1000:03}"
