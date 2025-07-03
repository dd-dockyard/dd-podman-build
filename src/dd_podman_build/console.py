import os

from rich.console import Console

# Not using .github.running_in_github_actions here because that file
# imports this one. Using 132 columns under GitHub Actions as a tribute
# to mainframe line printers, which are better than the Actions log
# viewer in every way.

console = Console(
    force_terminal=True if "GITHUB_ACTIONS" in os.environ else None,
    width=132 if "GITHUB_ACTIONS" in os.environ else None,
)
