#!/usr/bin/env python3
"""BreakCheck CLI — Detect API breaking changes. Enforce semver. Ship safe."""
import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from analyzer import extract_api, diff_api, max_level, LEVEL_RANK

app = typer.Typer(help="BreakCheck: Detect breaking API changes. Enforce semver.")
console = Console()

STYLE = {"major": "bold red", "minor": "yellow", "patch": "green"}
ICON = {"major": "\U0001f534", "minor": "\U0001f7e1", "patch": "\U0001f7e2"}


@app.command()
def compare(
    old: Path = typer.Argument(..., help="Old version source directory"),
    new: Path = typer.Argument(..., help="New version source directory"),
    fmt: str = typer.Option("table", "--format", "-f", help="Output: table|json"),
):
    """Compare two source trees and report all public API changes."""
    changes = diff_api(extract_api(old), extract_api(new))
    if fmt == "json":
        typer.echo(json.dumps({"changes": changes, "recommended": max_level(changes)}, indent=2))
        return
    if not changes:
        console.print("[green]No public API changes detected.[/green]")
        return
    tbl = Table(title="BreakCheck API Diff Report", show_lines=True)
    tbl.add_column("Level", width=10)
    tbl.add_column("Kind", width=22)
    tbl.add_column("Symbol", max_width=36)
    tbl.add_column("Detail")
    for c in sorted(changes, key=lambda x: -LEVEL_RANK[x["level"]]):
        lv = c["level"]
        tbl.add_row(f"{ICON[lv]} {lv}", c["kind"], c["symbol"], c["detail"], style=STYLE[lv])
    console.print(tbl)
    rec = max_level(changes)
    console.print(f"\nRecommended minimum bump: [{STYLE[rec]}]{rec}[/{STYLE[rec]}]")


@app.command()
def gate(
    old: Path = typer.Argument(..., help="Old version source directory"),
    new: Path = typer.Argument(..., help="New version source directory"),
    declared: str = typer.Option(..., "--declared", "-d", help="Declared bump: patch|minor|major"),
):
    """Gate a release: exit 1 if actual changes exceed declared bump level."""
    if declared not in LEVEL_RANK:
        console.print(f"[red]Invalid level '{declared}'. Use: patch, minor, major[/red]")
        raise typer.Exit(2)
    changes = diff_api(extract_api(old), extract_api(new))
    actual = max_level(changes)
    if LEVEL_RANK[actual] > LEVEL_RANK[declared]:
        console.print(f"\n[bold red]RELEASE BLOCKED[/bold red]")
        console.print(f"  Declared: [yellow]{declared}[/yellow] | Required: [bold red]{actual}[/bold red]\n")
        for c in changes:
            if LEVEL_RANK[c["level"]] > LEVEL_RANK[declared]:
                console.print(f"  {ICON['major']} {c['detail']}")
        console.print()
        raise typer.Exit(1)
    n = len(changes)
    console.print(f"[green]Gate passed[/green] | {n} change(s) | declared={declared} required={actual}")


if __name__ == "__main__":
    app()
