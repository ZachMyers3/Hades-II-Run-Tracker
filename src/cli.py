import typer

from hades_ii_run_tracker.hades_ii_run_tracker import hades_ii_run_tracker

app = typer.Typer()


@app.command()
def command() -> None:
    typer.echo(hades_ii_run_tracker())


def main():
    app()


if __name__ == "__main__":
    main()
