import typer

from .container import app as container_app

# eventually there will be more subcommands here
app = typer.Typer()
app.add_typer(container_app)
