"""Downloads an aider-chat release wheel from PyPI and imports its aider package and dependencies.
`--into DIR` replaces DIR/aider with the release's package (for an upstream import); `--pyproject FILE` rewrites
that file's dependencies with the release's runtime requirements. Only the standard library is used.
Run it as: python -m maintenance.import_upstream VERSION [--into DIR] [--pyproject FILE].
"""

import argparse
import io
import json
import shutil
import urllib.request
import zipfile
from pathlib import Path

from maintenance.upstream_deps import replace_dependencies, runtime_requirements

PYPI_JSON = "https://pypi.org/pypi/aider-chat/{version}/json"
WHEEL_TYPE = "bdist_wheel"
PACKAGE_PREFIX = "aider/"
METADATA_SUFFIX = ".dist-info/METADATA"
DOWNLOAD_TIMEOUT_SECONDS = 120


class UpstreamError(RuntimeError):
    """Raised when the release or its wheel cannot be found."""


def download_wheel(version: str) -> zipfile.ZipFile:
    with urllib.request.urlopen(PYPI_JSON.format(version=version), timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
        release = json.load(response)
    wheels = [f for f in release.get("urls", []) if f.get("packagetype") == WHEEL_TYPE]
    if not wheels:
        raise UpstreamError(f"aider-chat {version} has no wheel on PyPI")
    with urllib.request.urlopen(wheels[0]["url"], timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
        return zipfile.ZipFile(io.BytesIO(response.read()))


def metadata(wheel: zipfile.ZipFile) -> str:
    name = next((n for n in wheel.namelist() if n.endswith(METADATA_SUFFIX)), None)
    if name is None:
        raise UpstreamError("wheel has no METADATA")
    return wheel.read(name).decode()


def import_package(wheel: zipfile.ZipFile, dest: Path) -> int:
    """Replace dest/aider with the wheel's aider package; returns the number of files written."""
    shutil.rmtree(dest / "aider", ignore_errors=True)
    names = [n for n in wheel.namelist() if n.startswith(PACKAGE_PREFIX) and not n.endswith("/")]
    for name in names:
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(wheel.read(name))
    return len(names)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import an aider-chat release from PyPI.")
    parser.add_argument("version", help="aider-chat version, e.g. 0.86.2")
    parser.add_argument("--into", default="", help="Directory whose aider/ package is replaced")
    parser.add_argument("--pyproject", default="", help="pyproject.toml whose dependencies are replaced")
    args = parser.parse_args()
    wheel = download_wheel(args.version)
    if args.into:
        print(f"Wrote {import_package(wheel, Path(args.into))} files into {args.into}/aider")
    if args.pyproject:
        path = Path(args.pyproject)
        requirements = runtime_requirements(metadata(wheel))
        path.write_text(replace_dependencies(path.read_text(), requirements))
        print(f"Wrote {len(requirements)} dependencies into {path}")


if __name__ == "__main__":
    main()
