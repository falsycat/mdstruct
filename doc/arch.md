# Architecture

## Overview

mdstruct processes a Markdown document in three sequential stages:

```
YAML schema file
      │
      ▼
 Schema loader          (schema/loader.py)
      │  Pydantic model tree
      ▼
 Markdown parser        (md_parser.py)
      │  Internal AST (section tree)
      ▼
 Validator / Extractor  (validator.py / extractor.py)
      │
      ▼
 ValidationError list / extracted dict
```

1. **Schema loader** — reads `schema.yaml` and validates it into a typed Pydantic model tree.
2. **Markdown parser** — converts the document into an internal section-tree AST.
3. **Validator / Extractor** — walks the schema and AST in tandem to produce errors or extract data.

---

## Directory layout

```
mdstruct/
├── src/
│   └── mdstruct/
│       ├── __init__.py
│       ├── schema/
│       │   ├── __init__.py
│       │   ├── models.py       # Pydantic model tree for schema nodes
│       │   └── loader.py       # YAML → schema model tree
│       ├── md_parser.py        # Markdown → internal AST
│       ├── validator.py        # schema vs AST validation
│       ├── extractor.py        # data extraction driven by schema
│       └── cli.py              # Click CLI entry point
├── tests/
│   ├── fixtures/
│   │   ├── schema.yaml
│   │   └── document.md
│   ├── test_schema.py
│   ├── test_validator.py
│   └── test_extractor.py
├── doc/
│   ├── syntax.md
│   └── arch.md
└── pyproject.toml
```

---

## Schema layer (`schema/`)

### `schema/models.py`

Pydantic v2 models that represent every schema node type. All nodes share `name`, `required`, and `repeat`. The following are schema errors detected at load time:

- `required` and `repeat` set on the same node.
- `name` omitted on a node that has `repeat`.
- Two nodes in the same output scope share the same `name` — including names introduced by merging an unnamed `group` into its parent.

#### Building blocks

Shared types used across multiple node models.

```python
TypeName = Literal["str", "int", "float", "bool", "json"]

class PatternSpec(BaseModel):
    regex: str | None = None
    # types matches the capture-group shape:
    #   single value   → TypeName
    #   unnamed groups → list[TypeName]
    #   named groups   → dict[str, TypeName]
    types: TypeName | list[TypeName] | dict[str, TypeName] | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_from_string(cls, value: Any) -> Any:
        # accept a plain string as shorthand for PatternSpec(regex=value)
        if isinstance(value, str):
            return {"regex": value}
        return value

PatternField = str | PatternSpec   # used as the field type in node models

class RepeatSpec(BaseModel):
    min: int = 0
    max: int | None = None

class TitleMatch(BaseModel):
    pattern: PatternField   # str | PatternSpec — supports regex + optional types
    capture: str | None = None

class ColumnSchema(BaseModel):
    header: str
    name: str
    pattern: PatternField | None = None

class ItemSchema(BaseModel):
    pattern: PatternField | None = None
    children: list["NodeSchema"] = []   # nested list schema

class FrontmatterSchema(BaseModel):
    required: bool = False
    name: str | None = None   # if set, extracted under this key; else merged into root
    schema_: dict | None = Field(None, alias="schema")  # JSON Schema (Draft 7)
```

#### Leaf nodes

```python
class TextNode(BaseModel):
    type: Literal["text"]
    name: str | None = None
    required: bool = True
    repeat: RepeatSpec | None = None
    pattern: PatternField | None = None

class ListNode(BaseModel):
    type: Literal["list"]
    name: str | None = None
    required: bool = True
    repeat: RepeatSpec | None = None
    numbered: bool | None = None   # None = either
    item: ItemSchema = ItemSchema()

class TableNode(BaseModel):
    type: Literal["table"]
    name: str | None = None
    required: bool = True
    repeat: RepeatSpec | None = None
    columns: list[ColumnSchema] = []

class CodeNode(BaseModel):
    type: Literal["code"]
    name: str | None = None
    required: bool = True
    repeat: RepeatSpec | None = None
    language: str | None = None

class BlockquoteNode(BaseModel):
    type: Literal["blockquote"]
    name: str | None = None
    required: bool = True
    repeat: RepeatSpec | None = None
    pattern: PatternField | None = None

class ThematicBreakNode(BaseModel):
    type: Literal["thematic_break"]
    name: str | None = None
    required: bool = True
    repeat: RepeatSpec | None = None
```

#### Container nodes

```python
class GroupNode(BaseModel):
    type: Literal["group"]
    name: str | None = None
    required: bool = True
    repeat: RepeatSpec | None = None
    ordered: bool = True
    allow_extra: bool = False
    children: list["NodeSchema"] = []

class SectionNode(BaseModel):
    type: Literal["section"]
    title: str | TitleMatch
    # no level field: heading level is inferred from nesting depth
    name: str | None = None
    required: bool = True
    repeat: RepeatSpec | None = None
    ordered: bool = True        # shorthand for implicit group over children
    allow_extra: bool = False
    children: list["NodeSchema"] = []
```

#### Schema root

```python
NodeSchema = Annotated[
    TextNode | ListNode | TableNode | CodeNode |
    BlockquoteNode | ThematicBreakNode | GroupNode | SectionNode,
    Field(discriminator="type"),
]

class RootSchema(BaseModel):
    frontmatter: FrontmatterSchema | None = None
    children: list[NodeSchema] = []   # optional in YAML; defaults to empty list

class Schema(BaseModel):
    version: str
    root: RootSchema
```

`RootSchema` has no `ordered` or `allow_extra` fields. Root-level children are always matched with `ordered=true, allow_extra=false` (strict sequential). This cannot be changed; use a top-level `group` node if flexibility is needed.

### `schema/loader.py`

Reads a YAML file and instantiates `Schema` via `Schema.model_validate(data)`.

```python
def load_schema(path: str | Path) -> Schema:
    with open(path) as f:
        data = yaml.safe_load(f)
    return Schema.model_validate(data)
```

---

## Markdown parser (`md_parser.py`)

Converts a Markdown document into an internal section tree using `mistletoe`.

### Internal AST nodes

The AST has two kinds of nodes: **structural** (document root and sections) and **content** (everything else).

> **Naming note:** Several AST dataclass names here — `TextNode`, `ListNode`, `TableNode`, `CodeNode`, `BlockquoteNode`, `ThematicBreakNode`, and `SectionNode` — also appear as Pydantic models in `schema/models.py`. They are distinct types in different namespaces; the AST dataclasses carry parsed document data, while the schema models carry schema declarations.

```python
@dataclass
class DocumentNode:
    frontmatter: dict | None
    children: list[SectionNode | ContentNode]

@dataclass
class SectionNode:    # AST dataclass — distinct from schema.models.SectionNode
    level: int
    title: str
    line: int
    children: list[SectionNode | ContentNode]
```

Content nodes appear as direct children of `DocumentNode` or `SectionNode`:

```python
@dataclass
class TextNode:
    text: str       # plain text, Markdown stripped
    line: int

@dataclass
class ListItemNode:
    text: str
    children: list["ListNode"]   # nested lists
    line: int

@dataclass
class ListNode:
    ordered: bool
    items: list[ListItemNode]
    line: int

@dataclass
class TableNode:
    headers: list[str]
    rows: list[list[str]]
    line: int

@dataclass
class CodeNode:
    language: str | None
    content: str
    line: int

@dataclass
class BlockquoteNode:
    text: str       # plain text of the quoted content
    line: int

@dataclass
class ThematicBreakNode:
    raw: str        # raw text, e.g. "---", "***", "___"
    line: int

ContentNode = (
    TextNode | ListNode | TableNode |
    CodeNode | BlockquoteNode | ThematicBreakNode
)
```

### Parsing strategy

1. `mistletoe` tokenises the Markdown into a flat token list.
2. YAML front matter (if present) is stripped before tokenisation and parsed separately with `pyyaml`.
3. The flat token list is converted into a **section tree**: whenever a `Heading` token is encountered, a new `SectionNode` is opened. Subsequent content tokens become children until a heading of equal or higher level is seen. The `SectionNode.level` field stores the actual heading level read from the document (`#` = 1, `##` = 2, …).

### Heading level inference

The schema has no `level` field on `section` nodes. Instead, the validator derives the **expected heading level** from the nesting depth of the schema:

- `root.children` sections → expected level 1
- their `children` sections → expected level 2
- and so on recursively

During validation, the AST `SectionNode.level` is compared against this derived expected level. A mismatch produces a `level_mismatch` error.

---

## Validator (`validator.py`)

Walks the schema tree and the document AST in tandem, producing a list of `ValidationError` objects.

### `ValidationError`

```python
@dataclass
class ValidationError:
    path: str        # e.g. "root > Chapter 1 > group[api_details] > table[params]"
    error_type: str  # see table below
    message: str
    line: int | None
```

| `error_type`          | Meaning                                                          |
|-----------------------|------------------------------------------------------------------|
| `missing_element`     | A `required=true` node has no matching AST element              |
| `pattern_mismatch`    | Text / cell / item did not match `pattern`                       |
| `type_coercion_error` | Captured value could not be converted to the declared `types`    |
| `unexpected_element`  | An AST element has no schema match (`allow_extra=false`)         |
| `wrong_type`          | AST element type does not match schema node type                 |
| `repeat_underflow`    | Repeat count below `min`                                         |
| `repeat_overflow`     | Repeat count above `max`                                         |
| `missing_column`      | Table column header not found                                    |
| `wrong_language`      | Code block language does not match schema                        |
| `missing_field`       | Required front matter field absent (`line=None`)                 |
| `title_mismatch`      | Section heading text did not match expected title pattern/string |
| `level_mismatch`      | Section heading level did not match the depth-inferred expected level |

### Group matching algorithm

The core of validation is `match_group`, which handles all four `ordered × allow_extra` combinations:

| `ordered` | `allow_extra` | Matching behaviour                                                                                                                          |
|-----------|---------------|---------------------------------------------------------------------------------------------------------------------------------------------|
| `true`    | `false`       | Strict 1-to-1 sequential match. Extra elements cause an error. **(default)**                                                                |
| `true`    | `true`        | Schema children form a queue; doc nodes are scanned left to right; unrecognised nodes are skipped; remaining required schema nodes → error. |
| `false`   | `false`       | All schema children must be present in any order, with no extra doc elements allowed. Unmatched doc nodes → `unexpected_element`; missing required schema children → `missing_element`. |
| `false`   | `true`        | For each schema child, scan all doc nodes for a first match; required + not found → error.                                                  |

`SectionNode.ordered` / `SectionNode.allow_extra` are shorthands that apply the same logic to the section's `children` list.

---

## Extractor (`extractor.py`)

Runs after validation. Traverses the same schema + AST pair and builds a nested dict. Assumes the document has already been validated; if called on an invalid document, it raises `ExtractionError` without reporting details. Always run `validate()` first and check for errors before calling `extract()`.

### Extraction rules by node type

| Schema node      | AST node(s)         | Extracted value                                              |
|------------------|---------------------|--------------------------------------------------------------|
| `section`        | `SectionNode`       | dict of children's results; list when `repeat` set           |
| `group`          | *(none)*            | dict (named) or flat into parent scope                       |
| `text`           | `TextNode`          | `str`, `tuple`, or `dict` (see pattern capture group rules)  |
| `list`           | `ListNode`          | `list[str \| tuple \| dict]`                                 |
| `table`          | `TableNode`         | `list[dict]` — one dict per row                              |
| `code`           | `CodeNode`          | `{"language": str \| None, "content": str}`                  |
| `blockquote`     | `BlockquoteNode`    | `str`, `tuple`, or `dict` (capture group rules)              |
| `thematic_break` | `ThematicBreakNode` | `str` (raw text) when `name` is set; otherwise not extracted |
| `frontmatter`    | *(doc root)*        | raw dict; merged into root (or under `name` if set)          |

Pattern resolution and capture group rules are described in [syntax.md — Pattern capture groups and type coercion](syntax.md#pattern-capture-groups-and-type-coercion). When `item.children` is defined on a `list` node, per-item extraction keys are described in [syntax.md — Nested lists](syntax.md#nested-lists).

When `repeat` is set on a `section` or `group`, all matched instances are collected into a list under the node's `name` key. `name` is required on any repeating node; omitting it is a schema error.

---

## CLI (`cli.py`)

Built with [Click](https://click.palletsprojects.com/).

`validate` exits with code `0` on success, `1` when errors are found.
`extract` exits `0` on success, `1` if the document does not conform to the schema (no detail is shown).

### `validate` text output format

```
ERROR  root > section[Overview] (line 5): missing required element
ERROR  root > Chapter 1 > table[results] > row 2 > col_count (line 23): pattern '\d+' not matched: 'N/A'
Total: 2 error(s)
```

### `validate` JSON output format (`--format json`)

```json
{
  "errors": [
    {
      "path": "root > section[Overview]",
      "error_type": "missing_element",
      "message": "missing required element",
      "line": 5
    },
    {
      "path": "root > Chapter 1 > table[results] > row 2 > col_count",
      "error_type": "pattern_mismatch",
      "message": "pattern '\\d+' not matched: 'N/A'",
      "line": 23
    }
  ],
  "total": 2
}
```

---

## Dependencies

| Package       | Purpose                                         |
|---------------|-------------------------------------------------|
| `pydantic ≥2` | Schema model definition & validation            |
| `pyyaml`      | YAML loading                                    |
| `mistletoe`   | Markdown parsing                                |
| `jsonschema`  | Front matter validation via JSON Schema Draft 7 |
| `click`       | CLI framework                                   |
| `rich`        | Formatted terminal output                       |
