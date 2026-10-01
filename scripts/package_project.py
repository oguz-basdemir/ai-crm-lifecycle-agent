"""Package source and portfolio artifacts; exclude runtime state and secrets."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

root = Path(__file__).resolve().parents[1]
destination = root.parent / "ai-crm-lifecycle-agent.zip"
excluded_parts = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "artifacts",
    "build",
    "dist",
}
with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
    for file in sorted(root.rglob("*")):
        relative = file.relative_to(root)
        if not file.is_file() or any(
            part in excluded_parts or part.endswith(".egg-info") for part in relative.parts
        ):
            continue
        if file.name == ".env" or ".db" in file.suffixes or file.name.startswith("crm.db"):
            continue
        archive.write(file, Path(root.name) / relative)
print(destination)
