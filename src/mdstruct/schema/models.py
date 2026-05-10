from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator


TypeName = Literal["str", "int", "float", "bool", "json"]


class PatternSpec(BaseModel):
    # NOTE: regex comes from user-supplied schema files. Catastrophic backtracking
    # (ReDoS) is possible if untrusted parties can provide schema files. Mitigate by
    # running in a sandboxed process or switching to the `regex` package with timeout=.
    regex: str | None = None
    types: TypeName | list[TypeName] | dict[str, TypeName] | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_from_string(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"regex": value}
        return value

    @model_validator(mode="after")
    def _validate_regex(self) -> "PatternSpec":
        if self.regex is not None:
            try:
                re.compile(self.regex)
            except re.error as e:
                raise ValueError(f"invalid regex pattern: {e}") from e
        return self


PatternField = str | PatternSpec


class RepeatSpec(BaseModel):
    min: int = 0
    max: int | None = None


class TitleMatch(BaseModel):
    pattern: PatternField
    capture: str | None = None


class ColumnSchema(BaseModel):
    header: str
    name: str
    pattern: PatternField | None = None


class ItemSchema(BaseModel):
    pattern: PatternField | None = None
    children: list[NodeSchema] = []


class FrontmatterSchema(BaseModel):
    required: bool = False
    name: str | None = None
    schema_: dict | None = Field(None, alias="schema")

    model_config = {"populate_by_name": True}


class TextNode(BaseModel):
    type: Literal["text"]
    name: str | None = None
    required: bool = True
    repeat: RepeatSpec | None = None
    pattern: PatternField | None = None

    @model_validator(mode="after")
    def _check_repeat_required(self) -> "TextNode":
        _validate_repeat_required(self)
        return self


class ListNode(BaseModel):
    type: Literal["list"]
    name: str | None = None
    required: bool = True
    repeat: RepeatSpec | None = None
    numbered: bool | None = None
    item: ItemSchema = Field(default_factory=ItemSchema)

    @model_validator(mode="after")
    def _check_repeat_required(self) -> "ListNode":
        _validate_repeat_required(self)
        return self


class TableNode(BaseModel):
    type: Literal["table"]
    name: str | None = None
    required: bool = True
    repeat: RepeatSpec | None = None
    columns: list[ColumnSchema] = []

    @model_validator(mode="after")
    def _check_repeat_required(self) -> "TableNode":
        _validate_repeat_required(self)
        return self


class CodeNode(BaseModel):
    type: Literal["code"]
    name: str | None = None
    required: bool = True
    repeat: RepeatSpec | None = None
    language: str | None = None

    @model_validator(mode="after")
    def _check_repeat_required(self) -> "CodeNode":
        _validate_repeat_required(self)
        return self


class BlockquoteNode(BaseModel):
    type: Literal["blockquote"]
    name: str | None = None
    required: bool = True
    repeat: RepeatSpec | None = None
    pattern: PatternField | None = None

    @model_validator(mode="after")
    def _check_repeat_required(self) -> "BlockquoteNode":
        _validate_repeat_required(self)
        return self


class ThematicBreakNode(BaseModel):
    type: Literal["thematic_break"]
    name: str | None = None
    required: bool = True
    repeat: RepeatSpec | None = None

    @model_validator(mode="after")
    def _check_repeat_required(self) -> "ThematicBreakNode":
        _validate_repeat_required(self)
        return self


class GroupNode(BaseModel):
    type: Literal["group"]
    name: str | None = None
    required: bool = True
    repeat: RepeatSpec | None = None
    ordered: bool = True
    allow_extra: bool = False
    children: list[NodeSchema] = []

    @model_validator(mode="after")
    def _check_repeat_required(self) -> "GroupNode":
        _validate_repeat_required(self)
        return self


class SectionNode(BaseModel):
    type: Literal["section"]
    title: str | TitleMatch
    name: str | None = None
    required: bool = True
    repeat: RepeatSpec | None = None
    ordered: bool = True
    allow_extra: bool = False
    children: list[NodeSchema] = []

    @model_validator(mode="after")
    def _check_repeat_required(self) -> "SectionNode":
        _validate_repeat_required(self)
        return self


def _validate_repeat_required(node: Any) -> None:
    if node.repeat is not None and node.required is not True:
        pass  # required defaults to True but repeat overrides intent
    if node.repeat is not None and node.name is None:
        raise ValueError("'name' is required when 'repeat' is set")


NodeSchema = Annotated[
    TextNode | ListNode | TableNode | CodeNode |
    BlockquoteNode | ThematicBreakNode | GroupNode | SectionNode,
    Field(discriminator="type"),
]

# Update forward references
ItemSchema.model_rebuild()
GroupNode.model_rebuild()
SectionNode.model_rebuild()


class RootSchema(BaseModel):
    frontmatter: FrontmatterSchema | None = None
    children: list[NodeSchema] = []


class Schema(BaseModel):
    version: str
    root: RootSchema


def resolve_pattern(pattern: PatternField | None) -> PatternSpec | None:
    if pattern is None:
        return None
    if isinstance(pattern, str):
        return PatternSpec(regex=pattern)
    return pattern
