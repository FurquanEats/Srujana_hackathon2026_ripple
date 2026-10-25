"""`ripple certs` creates the local network's keys and certificates; `ripple up` starts every service.

Each member of `network.toml` runs as its own process on its own localhost port, with its own database file,
and accepts only mutually authenticated TLS connections. All processes share one simulated clock.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from ripple_cli import certs
from ripple_core.clock import IST
from ripple_core.network import Kind, Member, Network, load_network
from ripple_service.config import Paths, repo_root

APPS = {Kind.HUB: "ripple_hubs.cfcfrms:create_app"}
NODE_APP = "ripple_node.app:create_app"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ripple", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    certs_cmd = commands.add_parser("certs", help="create keys and certificates under .ripple/")
    certs_cmd.add_argument("--force", action="store_true", help="replace existing keys and certificates")
    up_cmd = commands.add_parser("up", help="start every service in network.toml")
    up_cmd.add_argument(
        "--speed", type=float, default=1.0, help="how much faster than real time the clock runs"
    )
    up_cmd.add_argument("--start", help="simulated start time, ISO 8601 (default: now in IST)")
    args = parser.parse_args(argv)

    root = repo_root()
    network = load_network(root / "network.toml")
    paths = Paths(root / ".ripple")
    if args.command == "certs":
        try:
            written = certs.create_all(network, paths, force=args.force)
        except FileExistsError as exc:
            print(exc, file=sys.stderr)
            return 1
        print(f"Wrote {len(written)} files under {paths.home}")
        return 0
    return up(network, paths, root, args.speed, args.start)


def command_for(member: Member, paths: Paths) -> list[str]:
    return [
        sys.executable, "-m", "uvicorn", APPS.get(member.kind, NODE_APP), "--factory",
        "--host", "127.0.0.1", "--port", str(member.port),
        "--ssl-keyfile", str(paths.tls_key(member.id)), "--ssl-certfile", str(paths.tls_cert(member.id)),
        "--ssl-ca-certs", str(paths.ca_cert), "--ssl-cert-reqs", "2",  # 2 = CERT_REQUIRED: mutual TLS
        "--log-level", "warning",
    ]  # fmt: skip


def up(network: Network, paths: Paths, root: Path, speed: float, start: str | None) -> int:
    if not paths.ca_cert.exists():
        print("No certificates yet. Run `uv run ripple certs` first.", file=sys.stderr)
        return 1
    clock_start = datetime.fromisoformat(start) if start else datetime.now(IST).replace(microsecond=0)
    env = {
        **os.environ,
        "RIPPLE_ROOT": str(root),
        "RIPPLE_CLOCK_START": clock_start.isoformat(),
        "RIPPLE_CLOCK_SPEED": str(speed),
        "RIPPLE_CLOCK_ANCHOR": repr(time.time()),
    }
    processes: dict[str, subprocess.Popen[bytes]] = {}
    try:
        for member in network.members:
            processes[member.id] = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
                command_for(member, paths), env={**env, "RIPPLE_MEMBER": member.id}
            )
            print(f"  {member.id:<12} {member.url}  {member.name}")
        print(f"Clock starts at {clock_start.isoformat()} and runs {speed:g}x. Press Ctrl+C to stop.")
        while True:
            for member_id, process in processes.items():
                if process.poll() is not None:
                    print(f"{member_id} stopped with exit code {process.returncode}; stopping the network.")
                    return 1
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("Stopping the network.")
        return 0
    finally:
        for process in processes.values():
            if process.poll() is None:
                process.terminate()
        for process in processes.values():
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    sys.exit(main())
