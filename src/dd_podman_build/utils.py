import os
import shlex
import subprocess
import sys
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any


@cache
def running_in_github_actions():
    return "GITHUB_ACTIONS" in os.environ and os.environ["GITHUB_ACTIONS"] == "true"


def sh(*args: str, **kwargs: Any) -> subprocess.CompletedProcess[str]:
    merged_kwargs: dict[str, Any] = {"check": True}
    merged_kwargs.update(kwargs)

    if running_in_github_actions():
        _ = sys.stderr.flush()
        _ = sys.stdout.flush()
        print(f"::group::{shlex.join(args)}")
        _ = sys.stdout.flush()
    else:
        _ = sys.stderr.write(f" + {shlex.join(args)}\n")
        _ = sys.stdout.flush()

    start = datetime.now()
    try:
        return subprocess.run(args, encoding="utf-8", **merged_kwargs)
    except subprocess.CalledProcessError as e:
        _ = sys.stderr.write(f"+++ command failed with status {e.returncode}\n")
        _ = sys.stderr.flush()
        raise
    finally:
        runtime = datetime.now() - start
        if running_in_github_actions():
            _ = sys.stderr.flush()
            _ = sys.stdout.flush()
            print("\n::endgroup::")
            _ = sys.stdout.flush()
        _ = sys.stderr.write(f"+++ command completed in {runtime}\n")
        _ = sys.stderr.flush()


@cache
def find_authfile() -> Path | None:
    if "REGISTRY_AUTH_FILE" in os.environ:
        env_config = Path(os.environ["REGISTRY_AUTH_FILE"])
        if env_config.exists():
            return env_config

    docker_config = Path(os.path.expanduser("~")).joinpath(".docker/config.json")
    if docker_config.exists():
        return docker_config

    redhat_config = Path(
        os.getenv("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    ).joinpath("containers/auth.json")
    if redhat_config.exists():
        return redhat_config

    return None
