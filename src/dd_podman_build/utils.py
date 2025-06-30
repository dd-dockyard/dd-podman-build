import os
import shlex
import subprocess
import sys
from functools import cache
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

    try:
        return subprocess.run(args, encoding="utf-8", **merged_kwargs)
    finally:
        if running_in_github_actions():
            _ = sys.stderr.flush()
            _ = sys.stdout.flush()
            print("\n::endgroup::")
            _ = sys.stdout.flush()
