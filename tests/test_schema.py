import pytest
from pydantic import ValidationError as PydanticValidationError

from mdstruct.schema.loader import load_schema
from mdstruct.schema.models import (
    PatternSpec, RepeatSpec, Schema, SectionNode, TableNode, TextNode,
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
