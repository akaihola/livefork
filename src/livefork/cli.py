"""livefork CLI."""

import typer

app = typer.Typer(
    name="livefork",
    help="Keep your personal fork alive.",
    no_args_is_help=True,
)


@app.callback(invoke_without_command=True)
def main(
    version: bool = typer.Option(
        False, "--version", "-V", help="Print version and exit."
    ),
) -> None:
    if version:
        from livefork import __version__

        typer.echo(f"livefork {__version__}")
        raise typer.Exit()


if __name__ == "__main__":
    app()
