# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules

project_root = Path(SPEC).resolve().parents[1]
standalone_dir = project_root / "standalone"
backend_dir = project_root / "backend"
build_root = Path(os.environ["TRENDLUME_STANDALONE_BUILD_ROOT"]).resolve()
frontend_dir = build_root / "frontend"
browser_dir = Path(os.environ["TRENDLUME_PLAYWRIGHT_BROWSERS"]).resolve()

node_binary = Path(os.environ["TRENDLUME_NODE_BINARY"]).resolve()
ffmpeg_binary = Path(os.environ["TRENDLUME_FFMPEG_BINARY"]).resolve()
ffprobe_binary = Path(os.environ["TRENDLUME_FFPROBE_BINARY"]).resolve()
icon_path = project_root / "frontend" / "public" / "favicon.ico"
version_file = os.environ.get("TRENDLUME_VERSION_FILE")

sys.path.insert(0, str(backend_dir))

playwright_datas, playwright_binaries, playwright_hiddenimports = collect_all("playwright")
hiddenimports = (
    collect_submodules("src")
    + collect_submodules("src.api")
    + collect_submodules("alembic")
    + collect_submodules("aiosqlite")
    + playwright_hiddenimports
)

datas = [
    (str(frontend_dir), "frontend"),
    (str(backend_dir / "alembic"), "alembic"),
    (str(backend_dir / "alembic.ini"), "."),
    (str(backend_dir / "pyproject.toml"), "backend"),
    (str(backend_dir / "templates"), "templates"),
    (str(backend_dir / "resources"), "resources"),
    (str(backend_dir / "workflows"), "workflows"),
    (str(browser_dir), "playwright-browsers"),
]
datas.extend(playwright_datas)

binaries = [
    (str(node_binary), "runtime"),
    (str(ffmpeg_binary), "runtime"),
    (str(ffprobe_binary), "runtime"),
]
binaries.extend(playwright_binaries)

a = Analysis(
    [str(standalone_dir / "launcher.py")],
    pathex=[str(project_root), str(backend_dir)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Trendlume",
    icon=str(icon_path) if sys.platform == "win32" and icon_path.is_file() else None,
    version=version_file,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)
