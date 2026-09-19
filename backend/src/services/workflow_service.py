import json
from pathlib import Path

from loguru import logger


def _derive_category(rel_path: str, parts: tuple[str, ...]) -> str:
    """Derive workflow category based on folder hierarchy first, then filename"""
    # 1. Check directory path components first (excluding filename)
    dir_parts = [p.lower() for p in parts[:-1]]
    if any("video" in p for p in dir_parts):
        return "video"
    if any(p in ("audio", "tts", "voice", "sound") for p in dir_parts):
        return "audio"
    if any(p in ("image", "img", "photo", "picture") for p in dir_parts):
        return "image"
    if any(p in ("analysis", "analyse") for p in dir_parts):
        return "analysis"

    # If in a custom subfolder, use the subfolder name
    if dir_parts:
        return dir_parts[0]

    # 2. Fallback to filename analysis if in root directory
    lower_path = rel_path.lower()
    if "analysis" in lower_path or "analyse" in lower_path:
        return "analysis"
    if "video" in lower_path:
        return "video"
    if "audio" in lower_path or "tts" in lower_path:
        return "audio"
    if "image" in lower_path or "img" in lower_path:
        return "image"

    return "custom"


def _format_friendly_title(stem: str) -> str:
    """Convert filename stem into a clean human-readable title without hardcoding"""
    cleaned = stem
    # Strip common category prefixes for cleaner display
    for prefix in ("image_", "video_", "tts_", "analyse_", "audio_"):
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix) :]
            break

    # Replace underscores/hyphens with spaces and capitalize
    words = cleaned.replace("_", " ").replace("-", " ").split()
    formatted_words = []
    for w in words:
        if "." in w:
            formatted_words.append(w)
        else:
            formatted_words.append(w.capitalize())
    return " ".join(formatted_words) or stem


def _extract_workflow_title(file_path: Path) -> str:
    """Try to read workflow title from JSON metadata, fallback to filename formatting"""
    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                # Check top-level metadata
                if "title" in data and isinstance(data["title"], str) and data["title"].strip():
                    return data["title"].strip()
                if "name" in data and isinstance(data["name"], str) and data["name"].strip():
                    return data["name"].strip()
                # Check ComfyUI _meta
                meta = data.get("_meta", {})
                if isinstance(meta, dict) and "title" in meta and isinstance(meta["title"], str):
                    return meta["title"].strip()
                # Check extra_data
                extra = data.get("extra_data", {})
                if isinstance(extra, dict) and "title" in extra and isinstance(extra["title"], str):
                    return extra["title"].strip()
    except Exception:
        pass

    return _format_friendly_title(file_path.stem)


class WorkflowService:
    """Service for discovering, categorizing, and resolving ComfyUI workflow files"""

    @staticmethod
    def get_workflows_dir() -> Path:
        """Get the base workflows directory path"""
        return Path(__file__).resolve().parent.parent.parent / "workflows"

    @classmethod
    def scan_workflows(
        cls, workflows_dir: Path | None = None, category: str | None = None
    ) -> list[dict]:
        """
        Recursively scan the workflows directory, dynamically grouping by subfolder
        and determining category & friendly name without hardcoded lists.
        """
        base_dir = workflows_dir or cls.get_workflows_dir()
        items = []

        if not base_dir.exists():
            logger.warning(f"Workflows directory does not exist: {base_dir}")
            return items

        for file in base_dir.rglob("*.json"):
            if not file.is_file():
                continue

            rel_path = file.relative_to(base_dir).as_posix()
            parts = file.relative_to(base_dir).parts
            subfolder = parts[0] if len(parts) > 1 else "root"
            cat = _derive_category(rel_path, parts)

            if category and cat != category and subfolder != category:
                continue

            title = _extract_workflow_title(file)
            if title and title.lower() != file.stem.lower() and title != rel_path:
                display_name = f"{rel_path} - {title}"
            else:
                display_name = rel_path

            items.append(
                {
                    "id": rel_path,
                    "path": rel_path,
                    "name": display_name,
                    "title": title,
                    "type": cat,
                    "subfolder": subfolder,
                    "file_name": file.name,
                }
            )

        # Sort: image -> video -> audio -> analysis -> others, then alphabetically by id
        type_priority = {"image": 0, "video": 1, "audio": 2, "analysis": 3}
        items.sort(key=lambda x: (type_priority.get(x["type"], 99), x["id"]))
        return items

    @classmethod
    def resolve_workflow_file(
        cls, workflow_target: str | None, workflows_dir: Path | None = None
    ) -> Path | None:
        """
        Resolve a canonical workflow catalog id to an actual existing file.

        Workflow ids are persisted in task/provider snapshots, so resolution
        must not guess from a basename or silently select a different file.
        """
        if not workflow_target or not workflow_target.strip():
            return None

        base_dir = (workflows_dir or cls.get_workflows_dir()).resolve()
        target_path = Path(workflow_target.strip())

        # Never allow an absolute path or ``..`` to escape the application
        # workflow directory.  Provider-selected workflows are persisted in
        # task payloads, so this boundary must be enforced at resolution time.
        if target_path.is_absolute():
            return None
        try:
            candidate = (base_dir / target_path).resolve()
            candidate.relative_to(base_dir)
        except ValueError:
            return None

        return candidate if candidate.is_file() else None

    @classmethod
    def get_workflow_snapshot(
        cls, workflow_target: str | None, expected_type: str | None = None
    ) -> dict[str, str] | None:
        """Resolve a workflow and capture stable metadata for a task."""
        path = cls.resolve_workflow_file(workflow_target)
        if path is None:
            if workflow_target:
                raise ValueError(f"工作流不存在或不在应用工作流目录内: {workflow_target}")
            return None
        base_dir = cls.get_workflows_dir().resolve()
        relative_path = path.resolve().relative_to(base_dir).as_posix()
        item = next((entry for entry in cls.scan_workflows() if entry["id"] == relative_path), None)
        if item is None:
            raise ValueError(f"工作流不存在或不在应用工作流目录内: {workflow_target}")
        if expected_type and item["type"] != expected_type:
            raise ValueError(f"工作流类型不匹配: 需要 {expected_type}，实际为 {item['type']}")
        return {
            "id": item["id"],
            "path": item["path"],
            "name": item["name"],
            "type": item["type"],
            "file_name": item["file_name"],
        }


workflow_service = WorkflowService()
