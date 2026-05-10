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


def test_extract_blockquote_plain():
    schema = _schema([{
        "type": "section", "title": "S",
        "children": [{"type": "blockquote", "name": "note"}],
    }])
    doc = parse_markdown("# S\n\n> Some note text.\n")
    data = extract(schema, doc)
    assert data["note"] == "Some note text."


def test_extract_blockquote_with_pattern():
    schema = _schema([{
        "type": "section", "title": "S",
        "children": [{"type": "blockquote", "name": "info",
                      "pattern": r"(?P<level>\w+): (?P<msg>.+)"}],
    }])
    doc = parse_markdown("# S\n\n> NOTE: important\n")
    data = extract(schema, doc)
    assert data["info"] == {"level": "NOTE", "msg": "important"}


def test_extract_thematic_break_with_name():
    schema = _schema([{
        "type": "section", "title": "S",
        "children": [{"type": "thematic_break", "name": "divider"}],
    }])
    doc = parse_markdown("# S\n\n---\n")
    data = extract(schema, doc)
    assert data["divider"] == "---"


def test_extract_thematic_break_no_name():
    schema = _schema([{
        "type": "section", "title": "S",
        "children": [
            {"type": "thematic_break"},
            {"type": "text", "name": "body"},
        ],
    }])
    doc = parse_markdown("# S\n\n---\n\nAfter break.\n")
    data = extract(schema, doc)
    assert "divider" not in data
    assert data["body"] == "After break."


def test_extract_list_unnamed_groups():
    schema = _schema([{
        "type": "section", "title": "S",
        "children": [{"type": "list", "name": "coords",
                      "item": {"pattern": {"regex": r"(\d+),\s*(\d+)", "types": ["int", "int"]}}}],
    }])
    doc = parse_markdown("# S\n\n- 10, 20\n- 30, 40\n")
    data = extract(schema, doc)
    assert data["coords"] == [(10, 20), (30, 40)]


def test_extract_list_nested_children():
    schema = _schema([{
        "type": "section", "title": "S",
        "children": [{"type": "list", "name": "entries", "item": {
            "pattern": r"(?P<name>.+)",
            "children": [{"type": "list", "name": "scores"}],
        }}],
    }])
    doc = parse_markdown("# S\n\n- Alice\n  - math\n  - english\n")
    data = extract(schema, doc)
    assert data["entries"] == [{"name": "Alice", "scores": ["math", "english"]}]


def test_extract_section_title_capture_full_match():
    # title pattern with no capture groups → full match string stored under capture key
    schema = _schema([{
        "type": "section",
        "title": {"pattern": r"Chapter \d+", "capture": "title"},
        "name": "chapters",
        "repeat": {"min": 0},
    }])
    doc = parse_markdown("# Chapter 3\n\n")
    data = extract(schema, doc)
    assert data["chapters"][0]["title"] == "Chapter 3"


def test_extract_section_title_capture_unnamed_groups():
    # unnamed groups → tuple stored under capture key
    schema = _schema([{
        "type": "section",
        "title": {"pattern": {"regex": r"v(\d+)\.(\d+)", "types": ["int", "int"]}, "capture": "ver"},
        "name": "releases",
        "repeat": {"min": 0},
    }])
    doc = parse_markdown("# v2.5\n\n")
    data = extract(schema, doc)
    assert data["releases"][0]["ver"] == (2, 5)


def test_extract_type_coerce_float():
    schema = _schema([{
        "type": "section", "title": "S",
        "children": [{"type": "text", "name": "price",
                      "pattern": {"regex": r"\d+\.\d+", "types": "float"}}],
    }])
    doc = parse_markdown("# S\n\n3.14\n")
    data = extract(schema, doc)
    assert data["price"] == pytest.approx(3.14)


def test_extract_type_coerce_bool_true():
    schema = _schema([{
        "type": "section", "title": "S",
        "children": [{"type": "text", "name": "flag", "pattern": {"types": "bool"}}],
    }])
    for truthy in ["true", "yes", "1", "y", "True", "YES"]:
        doc = parse_markdown(f"# S\n\n{truthy}\n")
        data = extract(schema, doc)
        assert data["flag"] is True, f"Expected True for {truthy!r}"


def test_extract_type_coerce_bool_false():
    schema = _schema([{
        "type": "section", "title": "S",
        "children": [{"type": "text", "name": "flag", "pattern": {"types": "bool"}}],
    }])
    for falsy in ["false", "no", "0", "f", "False", "NO"]:
        doc = parse_markdown(f"# S\n\n{falsy}\n")
        data = extract(schema, doc)
        assert data["flag"] is False, f"Expected False for {falsy!r}"


def test_extract_type_coerce_json():
    schema = _schema([{
        "type": "section", "title": "S",
        "children": [{"type": "text", "name": "data", "pattern": {"types": "json"}}],
    }])
    doc = parse_markdown("# S\n\n[1, 2, 3]\n")
    data = extract(schema, doc)
    assert data["data"] == [1, 2, 3]


def test_extract_group_named():
    schema = _schema([{
        "type": "section", "title": "S",
        "children": [{
            "type": "group", "name": "info",
            "children": [
                {"type": "text", "name": "body"},
                {"type": "code", "name": "ex"},
            ],
        }],
    }])
    doc = parse_markdown("# S\n\nHello.\n\n```python\nprint()\n```\n")
    data = extract(schema, doc)
    assert "info" in data
    assert data["info"]["body"] == "Hello."
    assert data["info"]["ex"]["language"] == "python"


def test_extract_group_unnamed():
    # unnamed group: children merged into parent scope
    schema = _schema([{
        "type": "section", "title": "S",
        "children": [{
            "type": "group",
            "children": [
                {"type": "text", "name": "body"},
                {"type": "code", "name": "ex"},
            ],
        }],
    }])
    doc = parse_markdown("# S\n\nHello.\n\n```python\nprint()\n```\n")
    data = extract(schema, doc)
    assert data["body"] == "Hello."
    assert data["ex"]["language"] == "python"


def test_extract_frontmatter_merged():
    # frontmatter without name → fields merged into root dict
    schema = Schema.model_validate({
        "version": "1.0",
        "root": {
            "frontmatter": {"required": True, "schema": {"type": "object"}},
            "children": [],
        },
    })
    doc = parse_markdown("---\nauthor: Alice\nversion: v1\n---\n")
    data = extract(schema, doc)
    assert data["author"] == "Alice"
    assert data["version"] == "v1"


def test_extract_table_no_columns():
    # table with no column spec → all headers used as keys
    schema = _schema([{
        "type": "section", "title": "S",
        "children": [{"type": "table", "name": "rows"}],
    }])
    doc = parse_markdown("# S\n\n| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n")
    data = extract(schema, doc)
    assert data["rows"] == [{"A": "1", "B": "2"}, {"A": "3", "B": "4"}]


def test_extract_repeat_section_collects_list():
    schema = _schema([{
        "type": "section",
        "title": {"pattern": r"Item \d+", "capture": "label"},
        "name": "items",
        "repeat": {"min": 0},
    }])
    doc = parse_markdown("# Item 1\n\n# Item 2\n\n# Item 3\n\n")
    data = extract(schema, doc)
    assert len(data["items"]) == 3
    assert data["items"][0]["label"] == "Item 1"
    assert data["items"][2]["label"] == "Item 3"
