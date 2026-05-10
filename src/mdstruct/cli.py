import json
import sys

import click
import yaml
from rich.console import Console

from .extractor import ExtractionError, extract
from .md_parser import parse_markdown
from .schema.loader import load_schema
from .validator import validate

console = Console(stderr=True)


@click.group()
def cli() -> None:
    pass


@cli.command("validate")
@click.argument("schema_path")
@click.argument("document_path")
@click.option("--format", "fmt", default="text", type=click.Choice(["text", "json"]))
def validate_cmd(schema_path: str, document_path: str, fmt: str) -> None:
    schema = load_schema(schema_path)
    with open(document_path) as f:
        doc = parse_markdown(f.read())
    errors = validate(schema, doc)

    if fmt == "json":
        click.echo(json.dumps({
            "errors": [
                {"path": e.path, "error_type": e.error_type, "message": e.message, "line": e.line}
                for e in errors
            ],
            "total": len(errors),
        }, indent=2))
    else:
        for e in errors:
            line_info = f" (line {e.line})" if e.line else ""
            click.echo(f"ERROR  {e.path}{line_info}: {e.message}")
        click.echo(f"Total: {len(errors)} error(s)")

    sys.exit(1 if errors else 0)


@cli.command("extract")
@click.argument("schema_path")
@click.argument("document_path")
@click.option("--format", "fmt", default="yaml", type=click.Choice(["yaml", "json"]))
def extract_cmd(schema_path: str, document_path: str, fmt: str) -> None:
    schema = load_schema(schema_path)
    with open(document_path) as f:
        doc = parse_markdown(f.read())
    try:
        data = extract(schema, doc)
    except ExtractionError:
        sys.exit(1)

    if fmt == "json":
        click.echo(json.dumps(data, indent=2, default=str))
    else:
        click.echo(yaml.dump(data, allow_unicode=True, sort_keys=False))

