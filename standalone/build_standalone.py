"""Stage the built frontend and create a platform-specific PyInstaller executable."""

from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STANDALONE_DIR = PROJECT_ROOT / "standalone"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
BUILD_DIR = STANDALONE_DIR / ".build"
FRONTEND_STAGE_DIR = BUILD_DIR / "frontend"
PYINSTALLER_WORK_DIR = BUILD_DIR / "pyinstaller"
OUTPUT_DIR = STANDALONE_DIR / "dist"


def build_version() -> str:
    with (PROJECT_ROOT / "backend" / "pyproject.toml").open("rb") as handle:
        version = tomllib.load(handle)["project"]["version"]

    if not re.fullmatch(
        r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?",
        version,
    ):
        raise ValueError(f"Invalid semantic version: {version!r}")

    release_tag = os.environ.get("TRENDLUME_RELEASE_TAG", "").strip()
    if release_tag and release_tag.removeprefix("v") != version:
        raise ValueError(
            f"Release tag {release_tag!r} does not match project version {version!r}"
        )
    return version


def versioned_artifact_stem(version: str, platform_name: str, runner_arch: str) -> str:
    configured = os.environ.get("TRENDLUME_STANDALONE_ARTIFACT")
    stem = configured or f"Trendlume-{platform_name}-{runner_arch}"
    version_marker = f"v{version}"
    if version_marker in stem:
        return stem
    if stem.startswith("Trendlume-"):
        return f"Trendlume-{version_marker}-{stem.removeprefix('Trendlume-')}"
    return f"{stem}-{version_marker}"


def write_windows_version_info(version: str) -> Path | None:
    if os.name != "nt":
        return None

    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )

    core_version = re.split(r"[-+]", version, maxsplit=1)[0]
    numeric_version = tuple(int(part) for part in core_version.split(".")) + (0,)
    version_info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=numeric_version, prodvers=numeric_version),
        kids=[
            StringFileInfo(
                [
                    StringTable(
                        "040904B0",
                        [
                            StringStruct("CompanyName", "Trendlume"),
                            StringStruct(
                                "FileDescription", "Trendlume AI Video Studio"
                            ),
                            StringStruct("FileVersion", version),
                            StringStruct("InternalName", "Trendlume"),
                            StringStruct("OriginalFilename", "Trendlume.exe"),
                            StringStruct("ProductName", "Trendlume"),
                            StringStruct("ProductVersion", version),
                        ],
                    )
                ]
            ),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    )
    version_info_path = BUILD_DIR / "version_info.txt"
    version_info_path.parent.mkdir(parents=True, exist_ok=True)
    version_info_path.write_text(str(version_info), encoding="utf-8")
    return version_info_path


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> str:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            check=True,
            text=True,
            capture_output=True,
            env=env,
        )
    except subprocess.CalledProcessError as exc:
        if exc.stdout:
            print(exc.stdout, end="")
        if exc.stderr:
            print(exc.stderr, end="", file=sys.stderr)
        raise
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    return completed.stdout.strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_node() -> Path:
    configured = os.environ.get("TRENDLUME_NODE_BINARY")
    if configured:
        path = Path(configured).expanduser().resolve()
        if path.is_file():
            return path
        raise FileNotFoundError(f"TRENDLUME_NODE_BINARY does not exist: {path}")

    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node.js is required to resolve the static FFmpeg binaries")
    return Path(node).resolve()


def resolve_static_binary(
    node: Path,
    expression: str,
    env_name: str,
) -> Path:
    configured = os.environ.get(env_name)
    if configured:
        path = Path(configured).expanduser().resolve()
    else:
        output = run([str(node), "-p", expression], cwd=STANDALONE_DIR)
        path = Path(output.strip()).expanduser().resolve()

    if not path.is_file():
        raise FileNotFoundError(f"Static binary was not found for {env_name}: {path}")
    return path


def resolve_browser_dir() -> Path:
    configured = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    path = (
        Path(configured).expanduser().resolve()
        if configured
        else BUILD_DIR / "playwright-browsers"
    )
    if not path.is_dir():
        raise FileNotFoundError(
            "PLAYWRIGHT_BROWSERS_PATH must point to the installed Playwright browser directory: "
            f"{path}"
        )
    if not any(path.iterdir()):
        raise RuntimeError(f"Playwright browser directory is empty: {path}")
    return path


def clean_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def stage_frontend() -> None:
    standalone_dir = FRONTEND_DIR / ".next" / "standalone"
    static_dir = FRONTEND_DIR / ".next" / "static"
    public_dir = FRONTEND_DIR / "public"

    if not (standalone_dir / "server.js").is_file():
        raise FileNotFoundError(
            "The standalone Next.js server was not found. Run npm run build in frontend first."
        )
    if not static_dir.is_dir():
        raise FileNotFoundError(f"Next.js static assets were not found: {static_dir}")

    clean_directory(FRONTEND_STAGE_DIR)
    shutil.copytree(standalone_dir, FRONTEND_STAGE_DIR, dirs_exist_ok=True)
    shutil.copytree(
        static_dir,
        FRONTEND_STAGE_DIR / ".next" / "static",
        dirs_exist_ok=True,
    )
    if public_dir.is_dir():
        shutil.copytree(
            public_dir,
            FRONTEND_STAGE_DIR / "public",
            dirs_exist_ok=True,
        )


def build() -> None:
    version = build_version()
    version_info_path = write_windows_version_info(version)
    if version_info_path:
        os.environ["TRENDLUME_VERSION_FILE"] = str(version_info_path)
    else:
        os.environ.pop("TRENDLUME_VERSION_FILE", None)

    node = resolve_node()
    ffmpeg = resolve_static_binary(
        node,
        "require('ffmpeg-static')",
        "TRENDLUME_FFMPEG_BINARY",
    )
    ffprobe = resolve_static_binary(
        node,
        "require('@derhuerst/ffprobe-static')",
        "TRENDLUME_FFPROBE_BINARY",
    )
    browser_dir = resolve_browser_dir()

    stage_frontend()

    os.environ.update(
        {
            "TRENDLUME_STANDALONE_BUILD_ROOT": str(BUILD_DIR),
            "TRENDLUME_NODE_BINARY": str(node),
            "TRENDLUME_FFMPEG_BINARY": str(ffmpeg),
            "TRENDLUME_FFPROBE_BINARY": str(ffprobe),
            "TRENDLUME_PLAYWRIGHT_BROWSERS": str(browser_dir),
        }
    )

    clean_directory(PYINSTALLER_WORK_DIR)
    clean_directory(OUTPUT_DIR)

    pyinstaller_command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(OUTPUT_DIR),
        "--workpath",
        str(PYINSTALLER_WORK_DIR),
        str(STANDALONE_DIR / "trendlume-standalone.spec"),
    ]
    print(f"Building Trendlume v{version} executable...")
    run(pyinstaller_command, cwd=PROJECT_ROOT)

    suffix = ".exe" if os.name == "nt" else ""
    built_path = OUTPUT_DIR / f"Trendlume{suffix}"
    if not built_path.is_file():
        raise FileNotFoundError(f"PyInstaller did not produce {built_path}")

    run([str(built_path), "--check-runtime"])
    reported_version = run([str(built_path), "--version"])
    if reported_version != version:
        raise RuntimeError(
            f"Packaged version mismatch: expected {version}, executable reported "
            f"{reported_version or '<empty>'}"
        )

    backend_smoke_dir = BUILD_DIR / "backend-smoke"
    clean_directory(backend_smoke_dir)
    backend_smoke_env = os.environ.copy()
    backend_smoke_env.update(
        {
            "TRENDLUME_DATA_DIR": str(backend_smoke_dir),
        }
    )
    run(
        [str(built_path), "--check-backend"],
        cwd=PROJECT_ROOT,
        env=backend_smoke_env,
    )

    runner_arch = os.environ.get("RUNNER_ARCH") or platform.machine()
    runner_arch = runner_arch.replace(" ", "_").replace("/", "_")
    platform_name = os.environ.get(
        "TRENDLUME_STANDALONE_PLATFORM",
        platform.system().lower(),
    )
    artifact_stem = versioned_artifact_stem(version, platform_name, runner_arch)
    artifact_name = artifact_stem if artifact_stem.endswith(suffix) else artifact_stem + suffix
    artifact_path = OUTPUT_DIR / artifact_name
    built_path.replace(artifact_path)

    if os.name != "nt":
        artifact_path.chmod(artifact_path.stat().st_mode | 0o111)

    archive_format = "zip" if os.name == "nt" else "gztar"
    archive_path = Path(
        shutil.make_archive(
            str(OUTPUT_DIR / artifact_stem),
            archive_format,
            root_dir=OUTPUT_DIR,
            base_dir=artifact_path.name,
        )
    )
    digest = sha256_file(archive_path)
    checksum_path = archive_path.with_name(archive_path.name + ".sha256")
    checksum_path.write_text(f"{digest}  {archive_path.name}\n", encoding="utf-8")
    artifact_path.unlink()

    print(
        f"Created {archive_path} "
        f"({archive_path.stat().st_size / 1024 / 1024:.1f} MiB)"
    )


if __name__ == "__main__":
    build()
