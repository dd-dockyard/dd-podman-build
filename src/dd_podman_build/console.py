import os

from rich.console import Console

# Not using .github.running_in_github_actions here because that file
# imports this one.

console = Console(
    force_terminal=True if "GITHUB_ACTIONS" in os.environ else None,
    width=100 if "GITHUB_ACTIONS" in os.environ else None,
)
