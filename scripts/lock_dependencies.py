"""Record tested runtime versions, excluding developer and platform-only packages."""

from importlib.metadata import distributions
from pathlib import Path

exclude = {
    "ai-crm-lifecycle-agent",
    "pip",
    "setuptools",
    "pytest",
    "ruff",
    "playwright",
    "pyee",
    "greenlet",
    "pluggy",
    "iniconfig",
}
lines = ["# Runtime snapshot tested on Python 3.14 / Windows; portable markers below."]
for package in sorted(distributions(), key=lambda d: d.metadata["Name"].lower()):
    name = package.metadata["Name"]
    normalized = name.lower().replace("_", "-")
    if normalized in exclude:
        continue
    if normalized == "numpy":
        lines.append(f"numpy=={package.version}; python_version >= '3.12'")
        lines.append("numpy==2.3.5; python_version < '3.12'")
    elif normalized == "colorama":
        lines.append(f"{name}=={package.version}; sys_platform == 'win32'")
    else:
        lines.append(f"{name}=={package.version}")
Path("requirements.lock").write_text("\n".join(lines) + "\n", encoding="utf-8")
