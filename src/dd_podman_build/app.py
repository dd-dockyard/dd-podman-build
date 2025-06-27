import typer

from .container import app as container_app

app = typer.Typer()
app.add_typer(container_app)
