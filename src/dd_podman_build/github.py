import os
from contextlib import contextmanager
from functools import cache

from .console import console, log_console


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
        log_console.print(f"::group::{summary}", highlight=False, markup=False)
    else:
        console.print(f"[bold]{summary}[/bold]")
        console.rule()

    try:
        yield
    finally:
        if running_in_github_actions():
            log_console.print("::endgroup::", highlight=False, markup=False)
        else:
            console.rule()
