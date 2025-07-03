import os
from contextlib import contextmanager
from functools import cache

from .console import console


@cache
def running_in_github_actions():
    return "GITHUB_ACTIONS" in os.environ and os.environ["GITHUB_ACTIONS"] == "true"


@contextmanager
def github_group(summary: str, heading: str | None = None):
    if heading:
        console.rule(heading)
    else:
        console.rule()

    if running_in_github_actions():
        console.print(f"::group::{summary}")
    else:
        console.print(f"[bold]{summary}[/bold]")
        console.rule()

    try:
        yield
    finally:
        if running_in_github_actions():
            print("::endgroup::")
        else:
            console.rule()
