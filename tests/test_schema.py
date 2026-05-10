import pytest
from pydantic import ValidationError as PydanticValidationError

from mdstruct.schema.loader import load_schema
from mdstruct.schema.models import (
    PatternSpec, RepeatSpec, Schema, SectionNode, TableNode, TextNode,
    resolve_pattern,
)


def test_load_schema_fixture():
    schema = load_schema("tests/fixtures/schema.yaml")
    assert schema.version == "1.0"
    assert schema.root.frontmatter is not None
    assert len(schema.root.children) == 2


def test_section_title_exact():
    schema = Schema.model_validate({
        "version": "1.0",
        "root": {
            "children": [{"type": "section", "title": "Hello"}],
        },
    })
    sec = schema.root.children[0]
    assert isinstance(sec, SectionNode)
    assert sec.title == "Hello"


def test_section_title_pattern():
    schema = Schema.model_validate({
        "version": "1.0",
        "root": {
            "children": [{
                "type": "section",
                "title": {"pattern": r"Chapter \d+", "capture": "title"},
                "name": "chapters",
                "repeat": {"min": 0},
            }],
        },
    })
    sec = schema.root.children[0]
    assert sec.repeat is not None


def test_pattern_spec_coerce_from_string():
    spec = PatternSpec.model_validate(r"\d+")
    assert spec.regex == r"\d+"
    assert spec.types is None


def test_repeat_requires_name():
    with pytest.raises(PydanticValidationError):
        Schema.model_validate({
            "version": "1.0",
            "root": {
                "children": [{"type": "text", "repeat": {"min": 0}}],
            },
        })


def test_frontmatter_schema():
    schema = load_schema("tests/fixtures/schema.yaml")
    fm = schema.root.frontmatter
    assert fm is not None
    assert fm.schema_ is not None
    assert "author" in fm.schema_["properties"]


def test_pattern_spec_with_single_type():
    spec = PatternSpec.model_validate({"regex": r"\d+", "types": "int"})
    assert spec.regex == r"\d+"
    assert spec.types == "int"


def test_pattern_spec_with_list_types():
    spec = PatternSpec.model_validate({"regex": r"(\d+)\.(\d+)", "types": ["int", "int"]})
    assert spec.types == ["int", "int"]


def test_pattern_spec_with_dict_types():
    spec = PatternSpec.model_validate({
        "regex": r"(?P<y>\d{4})-(?P<m>\d{2})",
        "types": {"y": "int", "m": "int"},
    })
    assert spec.types == {"y": "int", "m": "int"}


def test_pattern_spec_types_only():
    spec = PatternSpec.model_validate({"types": "float"})
    assert spec.regex is None
    assert spec.types == "float"


def test_repeat_spec_defaults():
    r = RepeatSpec.model_validate({})
    assert r.min == 0
    assert r.max is None


def test_repeat_spec_with_max():
    r = RepeatSpec.model_validate({"min": 1, "max": 3})
    assert r.min == 1
    assert r.max == 3


def test_resolve_pattern_none():
    assert resolve_pattern(None) is None


def test_resolve_pattern_string():
    spec = resolve_pattern(r"\d+")
    assert spec is not None
    assert spec.regex == r"\d+"


def test_resolve_pattern_spec():
    original = PatternSpec(regex=r"\d+", types="int")
    resolved = resolve_pattern(original)
    assert resolved is original


def test_frontmatter_name_field():
    schema = Schema.model_validate({
        "version": "1.0",
        "root": {
            "frontmatter": {"required": False, "name": "meta", "schema": {"type": "object"}},
            "children": [],
        },
    })
    assert schema.root.frontmatter is not None
    assert schema.root.frontmatter.name == "meta"


def test_section_defaults():
    schema = Schema.model_validate({
        "version": "1.0",
        "root": {"children": [{"type": "section", "title": "X"}]},
    })
    sec = schema.root.children[0]
    assert isinstance(sec, SectionNode)
    assert sec.ordered is True
    assert sec.allow_extra is False
    assert sec.required is True
    assert sec.children == []
