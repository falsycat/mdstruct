import pytest

from mdstruct.extractor import ExtractionError, extract
from mdstruct.md_parser import parse_markdown
from mdstruct.schema.loader import load_schema
from mdstruct.schema.models import Schema


def _schema(children, frontmatter=None):
    root = {"children": children}
    if frontmatter:
        root["frontmatter"] = frontmatter
    return Schema.model_validate({"version": "1.0", "root": root})


def test_extract_fixture():
    schema = load_schema("tests/fixtures/schema.yaml")
    with open("tests/fixtures/document.md") as f:
        doc = parse_markdown(f.read())
    data = extract(schema, doc)
    assert data["author"] == "Alice"
    assert data["overview"] == "This is the overview."
    assert len(data["chapters"]) == 2
    assert data["chapters"][0]["chapter_title"] == {"num": "1"}
    assert data["chapters"][0]["body"] == "This chapter covers the basics."
    assert data["chapters"][0]["data"][0] == {"item_name": "Alpha", "item_value": "42"}


def test_extract_text_plain():
    schema = _schema([
        {"type": "section", "title": "S", "children": [
            {"type": "text", "name": "body"},
        ]},
    ])
    doc = parse_markdown("# S\n\nHello world.\n")
    data = extract(schema, doc)
    assert data["body"] == "Hello world."


def test_extract_text_named_groups():
    schema = _schema([
        {"type": "section", "title": "S", "children": [
            {"type": "text", "name": "d",
             "pattern": r"(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})"},
        ]},
    ])
    doc = parse_markdown("# S\n\n2025-01-15\n")
    data = extract(schema, doc)
    assert data["d"] == {"year": "2025", "month": "01", "day": "15"}


def test_extract_text_unnamed_groups():
    schema = _schema([
        {"type": "section", "title": "S", "children": [
            {"type": "text", "name": "v",
             "pattern": {"regex": r"v(\d+)\.(\d+)\.(\d+)", "types": ["int", "int", "int"]}},
        ]},
    ])
    doc = parse_markdown("# S\n\nv1.2.3\n")
    data = extract(schema, doc)
    assert data["v"] == (1, 2, 3)


def test_extract_text_type_coerce():
    schema = _schema([
        {"type": "section", "title": "S", "children": [
            {"type": "text", "name": "n", "pattern": {"regex": r"\d+", "types": "int"}},
        ]},
    ])
    doc = parse_markdown("# S\n\n42\n")
    data = extract(schema, doc)
    assert data["n"] == 42


def test_extract_table():
    schema = _schema([
        {"type": "section", "title": "S", "children": [
            {"type": "table", "name": "rows", "columns": [
                {"header": "Name", "name": "name"},
                {"header": "Count", "name": "count", "pattern": {"regex": r"\d+", "types": "int"}},
            ]},
        ]},
    ])
    doc = parse_markdown("# S\n\n| Name | Count |\n|------|-------|\n| foo  | 3     |\n| bar  | 7     |\n")
    data = extract(schema, doc)
    assert data["rows"] == [{"name": "foo", "count": 3}, {"name": "bar", "count": 7}]


def test_extract_code():
    schema = _schema([
        {"type": "section", "title": "S", "children": [
            {"type": "code", "name": "ex", "language": "python"},
        ]},
    ])
    doc = parse_markdown("# S\n\n```python\nprint('hi')\n```\n")
    data = extract(schema, doc)
    assert data["ex"]["language"] == "python"
    assert "print" in data["ex"]["content"]


def test_extract_list_plain():
    schema = _schema([
        {"type": "section", "title": "S", "children": [
            {"type": "list", "name": "items"},
        ]},
    ])
    doc = parse_markdown("# S\n\n- apple\n- banana\n")
    data = extract(schema, doc)
    assert data["items"] == ["apple", "banana"]


def test_extract_list_named_groups():
    schema = _schema([
        {"type": "section", "title": "S", "children": [
            {"type": "list", "name": "kv", "item": {
                "pattern": r"(?P<key>[^:]+):\s*(?P<value>.+)",
            }},
        ]},
    ])
    doc = parse_markdown("# S\n\n- foo: bar\n- baz: qux\n")
    data = extract(schema, doc)
    assert data["kv"] == [{"key": "foo", "value": "bar"}, {"key": "baz", "value": "qux"}]


def test_extract_frontmatter_named():
    schema = Schema.model_validate({
        "version": "1.0",
        "root": {
            "frontmatter": {"required": True, "name": "meta",
                            "schema": {"type": "object"}},
            "children": [],
        },
    })
    doc = parse_markdown("---\nauthor: Bob\n---\n")
    data = extract(schema, doc)
    assert data["meta"] == {"author": "Bob"}


def test_extract_raises_on_invalid():
    schema = _schema([{"type": "section", "title": "Required", "required": True}])
    doc = parse_markdown("# Wrong\n\n")
    with pytest.raises(ExtractionError):
        extract(schema, doc)
