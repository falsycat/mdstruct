import pytest

from mdstruct.md_parser import parse_markdown
from mdstruct.schema.loader import load_schema
from mdstruct.schema.models import Schema
from mdstruct.validator import validate


def _schema(children):
    return Schema.model_validate({"version": "1.0", "root": {"children": children}})


def test_valid_fixture():
    schema = load_schema("tests/fixtures/schema.yaml")
    with open("tests/fixtures/document.md") as f:
        doc = parse_markdown(f.read())
    errors = validate(schema, doc)
    assert errors == []


def test_missing_required_section():
    schema = _schema([{"type": "section", "title": "Overview", "required": True}])
    doc = parse_markdown("# Other\n\ntext\n")
    errors = validate(schema, doc)
    assert any(e.error_type == "missing_element" for e in errors)


def test_pattern_mismatch():
    schema = _schema([
        {"type": "section", "title": "S", "children": [
            {"type": "text", "name": "v", "pattern": r"\d+"},
        ]},
    ])
    doc = parse_markdown("# S\n\nnotanumber\n")
    errors = validate(schema, doc)
    assert any(e.error_type == "pattern_mismatch" for e in errors)


def test_unexpected_element():
    schema = _schema([{"type": "section", "title": "A", "required": True}])
    doc = parse_markdown("# A\n\n# B\n\n")
    errors = validate(schema, doc)
    assert any(e.error_type == "unexpected_element" for e in errors)


def test_repeat_underflow():
    schema = _schema([{
        "type": "section",
        "title": {"pattern": r"Ch \d+", "capture": "t"},
        "name": "chapters",
        "repeat": {"min": 2, "max": None},
    }])
    doc = parse_markdown("# Ch 1\n\ntext\n")
    errors = validate(schema, doc)
    assert any(e.error_type == "repeat_underflow" for e in errors)


def test_wrong_language():
    schema = _schema([
        {"type": "section", "title": "S", "children": [
            {"type": "code", "name": "ex", "language": "python"},
        ]},
    ])
    doc = parse_markdown("# S\n\n```javascript\ncode\n```\n")
    errors = validate(schema, doc)
    assert any(e.error_type == "wrong_language" for e in errors)


def test_missing_table_column():
    schema = _schema([
        {"type": "section", "title": "S", "children": [
            {"type": "table", "name": "t", "columns": [
                {"header": "Name", "name": "name"},
                {"header": "Missing", "name": "m"},
            ]},
        ]},
    ])
    doc = parse_markdown("# S\n\n| Name |\n|------|\n| foo  |\n")
    errors = validate(schema, doc)
    assert any(e.error_type == "missing_column" for e in errors)


def test_frontmatter_required():
    schema = Schema.model_validate({
        "version": "1.0",
        "root": {
            "frontmatter": {"required": True, "schema": {"type": "object"}},
            "children": [],
        },
    })
    doc = parse_markdown("# No frontmatter\n")
    errors = validate(schema, doc)
    assert any(e.error_type == "missing_element" for e in errors)


def test_title_mismatch():
    schema = _schema([{"type": "section", "title": "Expected"}])
    doc = parse_markdown("# Actual\n\n")
    errors = validate(schema, doc)
    assert any(e.error_type == "title_mismatch" or e.error_type == "missing_element" for e in errors)
