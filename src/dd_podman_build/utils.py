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


def flush_stdio():
    _ = sys.stdout.write("\n")
    _ = sys.stdout.flush()
    _ = sys.stderr.write("\n")
    _ = sys.stderr.flush()


def sh(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
    args = tuple(map(str, args))
    merged_kwargs: dict[str, Any] = {"check": True}
    merged_kwargs.update(kwargs)

    flush_stdio()

    if running_in_github_actions():
        print(f"::group::{shlex.join(args)}")
    else:
        print(f"+++ {shlex.join(args)}")

    start = datetime.now()
    returncode = 0

    try:
        cmd = subprocess.run(args, encoding="utf-8", **merged_kwargs)
        return cmd
    except subprocess.CalledProcessError as e:
        returncode = e.returncode
        raise
    finally:
        runtime = datetime.now() - start
        flush_stdio()
        if running_in_github_actions():
            print("::endgroup::")
        print(f"+++ exit status: {returncode}, runtime: {runtime}")


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
