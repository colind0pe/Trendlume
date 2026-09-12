"""Entry point for the packaged standalone Trendlume application.

The frozen executable starts the FastAPI service and the standalone Next.js
server, waits for both services to become ready, and opens the local UI.
"""

from __future__ import annotations

import atexit
import importlib
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Iterable
from pathlib import Path

APP_NAME = "Trendlume"
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8000
FRONTEND_HOST = "127.0.0.1"
FRONTEND_PORT = 3000
STARTUP_TIMEOUT_SECONDS = 90.0


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    if is_frozen():
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[1]


def bundled_path(*parts: str) -> Path:
    return bundle_root().joinpath(*parts)


def application_version() -> str:
    with bundled_path("backend", "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def default_data_dir() -> Path:
    configured = os.environ.get("TRENDLUME_DATA_DIR") or os.environ.get("DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()

    if not is_frozen():
        return bundle_root() / "data"

    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME

    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / APP_NAME


def ensure_encryption_key(data_dir: Path) -> str:
    existing = (
        os.environ.get("CREDENTIAL_ENCRYPTION_KEY")
        or os.environ.get("ENCRYPTION_KEY")
        or ""
    ).strip()
    if existing:
        return existing

    key_path = data_dir / "encryption.key"
    if key_path.exists():
        stored = key_path.read_text(encoding="utf-8").strip()
        if stored:
            return stored

    key = secrets.token_urlsafe(32)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text(key + "\n", encoding="utf-8")
    if os.name != "nt":
        key_path.chmod(0o600)
    return key


def sqlite_url(data_dir: Path) -> str:
    database_path = (data_dir / "trendlume.db").resolve()
    return f"sqlite+aiosqlite:///{database_path.as_posix()}"


def prepare_backend_environment() -> dict[str, str]:
    data_dir = default_data_dir()
    storage_dir = data_dir / "storage"
    data_dir.mkdir(parents=True, exist_ok=True)
    storage_dir.mkdir(parents=True, exist_ok=True)

    runtime_dir = bundled_path("runtime")
    browser_dir = bundled_path("playwright-browsers")
    env = os.environ.copy()
    env.update(
        {
            "APP_NAME": APP_NAME,
            "APP_VERSION": application_version(),
            "DEBUG": "false",
            "HOST": BACKEND_HOST,
            "PORT": str(BACKEND_PORT),
            "DATA_DIR": str(data_dir),
            "STORAGE_DIR": str(storage_dir),
            "DATABASE_URL": sqlite_url(data_dir),
            "CORS_ORIGINS": json.dumps(
                [
                    f"http://{FRONTEND_HOST}:{FRONTEND_PORT}",
                    f"http://localhost:{FRONTEND_PORT}",
                ]
            ),
            "CREDENTIAL_ENCRYPTION_KEY": ensure_encryption_key(data_dir),
            "PLAYWRIGHT_BROWSERS_PATH": str(browser_dir),
            "PYTHONUNBUFFERED": "1",
        }
    )
    if runtime_dir.is_dir():
        env["PATH"] = str(runtime_dir) + os.pathsep + env.get("PATH", "")
    return env


def runtime_executable(name: str) -> Path:
    suffix = ".exe" if sys.platform == "win32" else ""
    return bundled_path("runtime", name + suffix)


def required_runtime_paths() -> Iterable[Path]:
    yield bundled_path("backend", "pyproject.toml")
    yield runtime_executable("node")
    yield runtime_executable("ffmpeg")
    yield runtime_executable("ffprobe")
    yield bundled_path("frontend", "server.js")
    yield bundled_path("playwright-browsers")


def check_required_runtime() -> None:
    missing = [str(path) for path in required_runtime_paths() if not path.exists()]
    if missing:
        details = "\n".join(f"  - {path}" for path in missing)
        raise RuntimeError(
            "The Trendlume package is incomplete. Missing bundled resources:\n" + details
        )

    if os.name != "nt":
        for name in ("node", "ffmpeg", "ffprobe"):
            path = runtime_executable(name)
            try:
                path.chmod(path.stat().st_mode | 0o111)
            except OSError:
                pass


def ensure_port_available(host: str, port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError as exc:
            raise RuntimeError(
                f"Port {port} is already in use. Close the other service and retry."
            ) from exc


def wait_for_http(url: str, process: subprocess.Popen[bytes], label: str) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    last_error = "no response yet"

    while time.monotonic() < deadline:
        return_code = process.poll()
        if return_code is not None:
            raise RuntimeError(
                f"{label} exited before becoming ready (exit code {return_code})."
            )

        request = urllib.request.Request(url, headers={"User-Agent": APP_NAME})
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                if 200 <= response.status < 500:
                    return
                last_error = f"HTTP {response.status}"
        except (OSError, urllib.error.HTTPError, urllib.error.URLError) as exc:
            last_error = str(exc)

        time.sleep(0.5)

    raise RuntimeError(f"{label} did not become ready within {STARTUP_TIMEOUT_SECONDS:.0f}s: {last_error}")


def backend_command() -> list[str]:
    if is_frozen():
        return [sys.executable, "--backend"]
    return [sys.executable, str(Path(__file__).resolve()), "--backend"]


def stop_process(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def configure_backend() -> None:
    env = prepare_backend_environment()
    os.environ.update(env)

    root = bundle_root()
    if not is_frozen():
        sys.path.insert(0, str(root / "backend"))


def upgrade_database() -> None:
    from alembic import command as alembic_command
    from alembic.config import Config as AlembicConfig

    alembic_config = AlembicConfig(str(bundled_path("alembic.ini")))
    alembic_config.set_main_option("script_location", str(bundled_path("alembic")))
    alembic_command.upgrade(alembic_config, "head")


def check_backend_runtime() -> None:
    configure_backend()
    upgrade_database()
    importlib.import_module("src.api.app")
    print("Backend runtime imports and database migrations are available.")


def run_backend() -> None:
    configure_backend()
    upgrade_database()

    import uvicorn

    uvicorn.run(
        "src.api.app:app",
        host=BACKEND_HOST,
        port=BACKEND_PORT,
        reload=False,
        log_level="info",
    )


def run_services() -> None:
    check_required_runtime()
    ensure_port_available(BACKEND_HOST, BACKEND_PORT)
    ensure_port_available(FRONTEND_HOST, FRONTEND_PORT)

    root = bundle_root()
    backend_env = prepare_backend_environment()
    backend_process: subprocess.Popen[bytes] | None = None
    frontend_process: subprocess.Popen[bytes] | None = None

    def cleanup() -> None:
        stop_process(frontend_process)
        stop_process(backend_process)

    atexit.register(cleanup)

    try:
        backend_process = subprocess.Popen(
            backend_command(),
            cwd=str(root),
            env=backend_env,
        )
        wait_for_http(
            f"http://{BACKEND_HOST}:{BACKEND_PORT}/api/v1/health",
            backend_process,
            "Backend",
        )

        frontend_env = backend_env.copy()
        frontend_env.update(
            {
                "NODE_ENV": "production",
                "HOSTNAME": FRONTEND_HOST,
                "PORT": str(FRONTEND_PORT),
                "BACKEND_URL": f"http://{BACKEND_HOST}:{BACKEND_PORT}",
                "NEXT_TELEMETRY_DISABLED": "1",
            }
        )
        frontend_process = subprocess.Popen(
            [
                str(runtime_executable("node")),
                str(bundled_path("frontend", "server.js")),
            ],
            cwd=str(bundled_path("frontend")),
            env=frontend_env,
        )
        frontend_url = f"http://{FRONTEND_HOST}:{FRONTEND_PORT}"
        wait_for_http(frontend_url, frontend_process, "Frontend")
        webbrowser.open(frontend_url)

        print(f"{APP_NAME} v{application_version()} is running at {frontend_url}")
        print("Keep this window open while using Trendlume. Press Ctrl+C to stop it.")

        while True:
            if backend_process.poll() is not None:
                raise RuntimeError(
                    f"Backend stopped unexpectedly (exit code {backend_process.returncode})."
                )
            if frontend_process.poll() is not None:
                raise RuntimeError(
                    f"Frontend stopped unexpectedly (exit code {frontend_process.returncode})."
                )
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping Trendlume...")
    finally:
        cleanup()


def main() -> None:
    if "--version" in sys.argv[1:]:
        print(application_version())
    elif "--check-runtime" in sys.argv[1:]:
        check_required_runtime()
        print(
            f"Standalone runtime resources are available for v{application_version()}."
        )
    elif "--check-backend" in sys.argv[1:]:
        check_backend_runtime()
    elif "--backend" in sys.argv[1:]:
        run_backend()
    else:
        run_services()


if __name__ == "__main__":
    main()
