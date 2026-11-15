"""Node on the host for the general agent (M8).

The agent's own commands run on this machine, not in the Docker image, so each case's
Node must be here too: OpossumUI and wps need Node 16, kubeflow Node 22. The versions
are the ones the Docker images pin (``migrator.execs.NODE_IMAGES``), so the agent's
test runs and Verify's agree. Each is downloaded once from nodejs.org into the
Migrator's cache, checked against the release's ``SHASUMS256.txt``, and never put on
the user's own PATH.
"""

from __future__ import annotations

import hashlib
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

from migrator.general_agent.errors import GeneralAgentError

# The exact versions of the pinned Docker images, by major.
HOST_NODE = {"16": "16.20.2", "18": "18.20.8", "20": "20.20.2", "22": "22.21.1"}
# yarn v1 for the repos that use it, installed into the Node folder (no global install).
YARN_V1 = "1.22.22"
DIST = "https://nodejs.org/dist"


def _platform() -> str:
    system = {"Darwin": "darwin", "Linux": "linux"}.get(platform.system())
    arch = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "x64"}.get(platform.machine())
    if system is None or arch is None:
        raise GeneralAgentError(
            f"no Node build for {platform.system()} {platform.machine()}; the general "
            "agent runs on macOS or Linux"
        )
    return f"{system}-{arch}"


def node_version(node: str | None) -> str:
    major = (node or "20").strip().removeprefix("v").split(".")[0]
    if major not in HOST_NODE:
        raise GeneralAgentError(
            f"no pinned host Node {major} (pinned: {', '.join(sorted(HOST_NODE))})"
        )
    return HOST_NODE[major]


def _fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as resp:
        data: bytes = resp.read()
    return data


def ensure_node(node: str | None, cache: Path, package_manager: str = "npm") -> Path:
    """The ``bin`` folder of the pinned Node for ``node`` (a major such as "16"),
    downloaded once; with yarn v1 in it when the repo uses yarn."""
    version = node_version(node)
    name = f"node-v{version}-{_platform()}"
    home = cache / name
    bin_dir = home / "bin"
    if not (bin_dir / "node").is_file():
        cache.mkdir(parents=True, exist_ok=True)
        archive = f"{name}.tar.gz"
        sums = _fetch(f"{DIST}/v{version}/SHASUMS256.txt").decode()
        wanted = next((ln.split()[0] for ln in sums.splitlines() if ln.endswith(archive)), None)
        if wanted is None:
            raise GeneralAgentError(f"{archive} is not in Node {version}'s SHASUMS256.txt")
        data = _fetch(f"{DIST}/v{version}/{archive}")
        if hashlib.sha256(data).hexdigest() != wanted:
            raise GeneralAgentError(f"{archive}: checksum does not match SHASUMS256.txt")
        with tempfile.TemporaryDirectory(dir=cache) as tmp:
            path = Path(tmp) / archive
            path.write_bytes(data)
            with tarfile.open(path) as tar:
                tar.extractall(tmp, filter="tar")
            shutil.rmtree(home, ignore_errors=True)
            (Path(tmp) / name).rename(home)
    if package_manager == "yarn" and not (bin_dir / "yarn").exists():
        # npm ships with Node; --prefix keeps yarn inside this Node's folder.
        done = subprocess.run(
            [
                str(bin_dir / "npm"),
                "install",
                "--global",
                "--prefix",
                str(home),
                "--ignore-scripts",
                "--no-audit",
                "--no-fund",
                f"yarn@{YARN_V1}",
            ],
            env={"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(cache)},
            capture_output=True,
            text=True,
            check=False,
        )
        if done.returncode != 0:
            raise GeneralAgentError(f"could not install yarn {YARN_V1}: {done.stdout[-400:]}")
    return bin_dir
