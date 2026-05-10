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


def test_title_mismatch_pattern():
    # A section that doesn't match the repeat pattern is not consumed.
    # With min=0 there's no underflow, but the leftover node becomes unexpected_element.
    schema = _schema([{
        "type": "section",
        "title": {"pattern": r"Chapter \d+", "capture": "t"},
        "name": "chapters",
        "repeat": {"min": 0},
    }])
    doc = parse_markdown("# Not a chapter\n\n")
    errors = validate(schema, doc)
    assert not any(e.error_type == "repeat_underflow" for e in errors)
    assert any(e.error_type == "unexpected_element" for e in errors)


def test_level_mismatch():
    # ## heading at root → level 2, but schema expects level 1
    schema = _schema([{"type": "section", "title": "S"}])
    doc = parse_markdown("## S\n\n")
    errors = validate(schema, doc)
    assert any(e.error_type == "level_mismatch" for e in errors)


def test_missing_field_in_frontmatter():
    schema = Schema.model_validate({
        "version": "1.0",
        "root": {
            "frontmatter": {
                "required": False,
                "schema": {
                    "type": "object",
                    "required": ["author"],
                    "properties": {"author": {"type": "string"}},
                },
            },
            "children": [],
        },
    })
    doc = parse_markdown("---\ntitle: test\n---\n")
    errors = validate(schema, doc)
    assert any(e.error_type == "missing_field" for e in errors)


def test_ordered_allow_extra_skips_unknown():
    # ordered=True, allow_extra=True: unrecognised nodes are skipped
    schema = _schema([{
        "type": "section", "title": "S",
        "ordered": True, "allow_extra": True,
        "children": [{"type": "text", "name": "body", "required": True}],
    }])
    doc = parse_markdown("# S\n\n| A |\n|---|\n| 1 |\n\nHello\n")
    errors = validate(schema, doc)
    assert errors == []


def test_ordered_allow_extra_missing_required():
    # ordered=True, allow_extra=True: missing required node → error
    schema = _schema([{
        "type": "section", "title": "S",
        "ordered": True, "allow_extra": True,
        "children": [{"type": "text", "name": "body", "required": True}],
    }])
    doc = parse_markdown("# S\n\n| A |\n|---|\n| 1 |\n")
    errors = validate(schema, doc)
    assert any(e.error_type == "missing_element" for e in errors)


def test_unordered_children_any_order_valid():
    # ordered=False, allow_extra=False: children can appear in any order
    schema = _schema([{
        "type": "section", "title": "S",
        "ordered": False, "allow_extra": False,
        "children": [
            {"type": "text", "name": "body", "required": True},
            {"type": "code", "name": "ex", "required": True},
        ],
    }])
    doc = parse_markdown("# S\n\n```python\ncode\n```\n\nHello\n")
    errors = validate(schema, doc)
    assert errors == []


def test_unordered_children_extra_element():
    # ordered=False, allow_extra=False: extra element → unexpected_element
    schema = _schema([{
        "type": "section", "title": "S",
        "ordered": False, "allow_extra": False,
        "children": [{"type": "text", "name": "body", "required": True}],
    }])
    doc = parse_markdown("# S\n\nHello\n\n```python\nextra\n```\n")
    errors = validate(schema, doc)
    assert any(e.error_type == "unexpected_element" for e in errors)


def test_unordered_allow_extra_finds_match_anywhere():
    # ordered=False, allow_extra=True: scans all nodes for each schema child
    schema = _schema([{
        "type": "section", "title": "S",
        "ordered": False, "allow_extra": True,
        "children": [{"type": "code", "name": "ex", "required": True}],
    }])
    doc = parse_markdown("# S\n\nText before.\n\n```python\ncode\n```\n\nText after.\n")
    errors = validate(schema, doc)
    assert errors == []


def test_blockquote_valid():
    schema = _schema([{
        "type": "section", "title": "S",
        "children": [{"type": "blockquote", "name": "note"}],
    }])
    doc = parse_markdown("# S\n\n> Some note.\n")
    errors = validate(schema, doc)
    assert errors == []


def test_blockquote_pattern_mismatch():
    schema = _schema([{
        "type": "section", "title": "S",
        "children": [{"type": "blockquote", "name": "note", "pattern": r"NOTE:.*"}],
    }])
    doc = parse_markdown("# S\n\n> Warning: not a note\n")
    errors = validate(schema, doc)
    assert any(e.error_type == "pattern_mismatch" for e in errors)


def test_thematic_break_valid():
    schema = _schema([{
        "type": "section", "title": "S",
        "children": [{"type": "thematic_break", "name": "div"}],
    }])
    doc = parse_markdown("# S\n\n---\n")
    errors = validate(schema, doc)
    assert errors == []


def test_thematic_break_missing():
    schema = _schema([{
        "type": "section", "title": "S",
        "children": [{"type": "thematic_break", "name": "div", "required": True}],
    }])
    doc = parse_markdown("# S\n\nSome text.\n")
    errors = validate(schema, doc)
    assert any(e.error_type == "missing_element" for e in errors)


def test_list_numbered_wrong_type():
    schema = _schema([{
        "type": "section", "title": "S",
        "children": [{"type": "list", "name": "items", "numbered": True}],
    }])
    doc = parse_markdown("# S\n\n- bullet\n- list\n")
    errors = validate(schema, doc)
    assert any(e.error_type == "wrong_type" for e in errors)


def test_list_bullet_wrong_type():
    schema = _schema([{
        "type": "section", "title": "S",
        "children": [{"type": "list", "name": "items", "numbered": False}],
    }])
    doc = parse_markdown("# S\n\n1. numbered\n2. list\n")
    errors = validate(schema, doc)
    assert any(e.error_type == "wrong_type" for e in errors)


def test_list_item_pattern_mismatch():
    schema = _schema([{
        "type": "section", "title": "S",
        "children": [{"type": "list", "name": "nums", "item": {"pattern": r"\d+"}}],
    }])
    doc = parse_markdown("# S\n\n- 123\n- abc\n")
    errors = validate(schema, doc)
    assert any(e.error_type == "pattern_mismatch" for e in errors)


def test_table_cell_pattern_mismatch():
    schema = _schema([{
        "type": "section", "title": "S",
        "children": [{"type": "table", "name": "t", "columns": [
            {"header": "Val", "name": "val", "pattern": r"\d+"},
        ]}],
    }])
    doc = parse_markdown("# S\n\n| Val |\n|-----|\n| abc |\n")
    errors = validate(schema, doc)
    assert any(e.error_type == "pattern_mismatch" for e in errors)


def test_required_false_section_missing_no_error():
    schema = _schema([{"type": "section", "title": "Optional", "required": False}])
    doc = parse_markdown("# Other\n\n")
    errors = validate(schema, doc)
    # Optional section missing → missing_element from "Other" being unexpected instead
    assert not any(e.error_type == "missing_element" and "Optional" in e.path for e in errors)


def test_repeat_max_respected():
    # repeat.max=1: a second match is treated as unexpected_element
    schema = _schema([{
        "type": "section",
        "title": {"pattern": r"Ch \d+", "capture": "t"},
        "name": "chapters",
        "repeat": {"min": 0, "max": 1},
    }])
    doc = parse_markdown("# Ch 1\n\n# Ch 2\n\n")
    errors = validate(schema, doc)
    assert any(e.error_type == "unexpected_element" for e in errors)


def test_nested_section_level():
    # subsections must be h2 inside h1 sections
    schema = _schema([{
        "type": "section", "title": "Top",
        "children": [{"type": "section", "title": "Sub"}],
    }])
    doc = parse_markdown("# Top\n\n## Sub\n\n")
    errors = validate(schema, doc)
    assert errors == []
