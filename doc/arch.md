# Architecture

## Overview

mdstruct has three logical stages that run in sequence:

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

Pydantic v2 models that represent every schema node type.  
All nodes share a base with `name`, `required`, and `repeat`.

```python
# ── type coercion ────────────────────────────────────────
TypeName = Literal["str", "int", "float", "bool", "json"]

# pattern field: string shorthand or object with regex + types
class PatternSpec(BaseModel):
    regex: str | None = None
    # types matches the capture-group shape:
    #   single value  → TypeName
    #   unnamed groups → list[TypeName]
    #   named groups   → dict[str, TypeName]
    types: TypeName | list[TypeName] | dict[str, TypeName] | None = None

    @classmethod
    def __get_validators__(cls):
        # also accept a plain string (shorthand for PatternSpec(regex=value))
        ...

PatternField = str | PatternSpec   # the actual type used in node models

# ── schema building blocks ───────────────────────────────
class RepeatSpec(BaseModel):
    min: int = 0
    max: int | None = None

class TitleMatch(BaseModel):
    pattern: str
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

# ── leaf nodes ──────────────────────────────────────────
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
    ordered: bool | None = None   # None = either
    item: ItemSchema = ItemSchema()

class TaskListNode(BaseModel):
    type: Literal["task_list"]
    name: str | None = None
    required: bool = True
    repeat: RepeatSpec | None = None
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
    required: bool = False

# ── container nodes ─────────────────────────────────────
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

NodeSchema = Annotated[
    TextNode | ListNode | TaskListNode | TableNode | CodeNode |
    BlockquoteNode | ThematicBreakNode | GroupNode | SectionNode,
    Field(discriminator="type"),
]

class RootSchema(BaseModel):
    frontmatter: FrontmatterSchema | None = None
    children: list[NodeSchema] = []

class Schema(BaseModel):
    version: str
    root: RootSchema
```

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

Converts a Markdown document into an **internal section tree** using `mistletoe`.

### Internal AST nodes

```python
@dataclass
class DocumentNode:
    frontmatter: dict | None
    children: list[SectionNode | ContentNode]

@dataclass
class SectionNode:
    level: int
    title: str
    line: int
    children: list[SectionNode | ContentNode]

# ── content nodes ────────────────────────────────────────
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
class TaskItem:
    text: str
    checked: bool
    line: int

@dataclass
class TaskListNode:
    items: list[TaskItem]
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
    line: int
```

### Parsing strategy

1. `mistletoe` tokenises the Markdown into a flat token list.
2. YAML front matter (if present) is stripped before tokenisation and parsed separately with `pyyaml`.
3. The flat token list is converted into a **section tree**: whenever a `Heading` token is encountered, a new `SectionNode` is opened. Subsequent content tokens become children until a heading of equal or higher level is seen. The `SectionNode.level` field stores the actual heading level read from the document (`#` = 1, `##` = 2, …).
4. Task lists are detected by scanning list item text for the `[ ]` / `[x]` prefix; if all items in a list qualify, the list becomes a `TaskListNode`.

### Heading level inference

The schema has no `level` field on `section` nodes. Instead, the validator derives the **expected heading level** from the nesting depth of the schema:

- `root.children` sections → expected level 1
- their `children` sections → expected level 2
- and so on recursively

During validation, the AST `SectionNode.level` is compared against this derived expected level. A mismatch produces a `title_mismatch` error.

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

| `error_type`          | Meaning                                              |
|-----------------------|------------------------------------------------------|
| `missing_element`     | A `required=true` node has no matching AST element   |
| `pattern_mismatch`    | Text / cell / item did not match `pattern`           |
| `unexpected_element`  | An AST element has no schema match (`allow_extra=false`) |
| `wrong_type`          | AST element type does not match schema node type     |
| `repeat_underflow`    | Repeat count below `min`                             |
| `repeat_overflow`     | Repeat count above `max`                             |
| `missing_column`      | Table column header not found                        |
| `wrong_language`      | Code block language does not match schema            |
| `missing_field`       | Required front matter field absent                   |
| `title_mismatch`      | Section heading did not match title pattern/string   |

### Group matching algorithm

The core of validation is `match_group`, which handles all four `ordered × allow_extra` combinations:

```
match_group(schema_children, doc_nodes, ordered, allow_extra):

  ordered=true,  allow_extra=false  →  strict 1-to-1 sequential match
  ordered=true,  allow_extra=true   →  schema children form a queue;
                                       doc_nodes are scanned left to right;
                                       unrecognised nodes are skipped;
                                       remaining required schema nodes → error
  ordered=false, allow_extra=true   →  for each schema child, scan all doc_nodes
                                       for a first match; required + not found → error
  ordered=false, allow_extra=false  →  bipartite matching: every doc_node must
                                       match exactly one schema child;
                                       unmatched doc_nodes or required unmatched
                                       schema children → error
```

`SectionNode.ordered` / `SectionNode.allow_extra` are shorthands that apply the same logic to the section's `children` list.

---

## Extractor (`extractor.py`)

Runs after validation (or independently). Traverses the same schema + AST pair and builds a nested dict.

### Extraction rules by node type

| Schema node    | AST node(s)     | Extracted value                                        |
|----------------|-----------------|--------------------------------------------------------|
| `section`      | `SectionNode`   | dict of children's results; list when `repeat` set     |
| `group`        | *(none)*        | dict of children (if named), or merged into parent     |
| `text`         | `TextNode`      | `str`, `tuple`, or `dict` (see capture group rules)    |
| `list`         | `ListNode`      | `list[str \| tuple \| dict]`                           |
| `task_list`    | `TaskListNode`  | `list[{"text": str, "checked": bool}]`                 |
| `table`        | `TableNode`     | `list[dict]` — one dict per row                        |
| `code`         | `CodeNode`      | `{"language": str \| None, "content": str}`            |
| `blockquote`   | `BlockquoteNode`| `str`, `tuple`, or `dict` (capture group rules)        |
| `thematic_break`| `ThematicBreakNode` | not extracted                                     |
| `frontmatter`  | *(doc root)*    | raw dict; merged into root (or under `name` if set)    |

### Pattern resolution

`PatternField` is resolved at extraction time as follows:

1. If `pattern` is a plain string, treat it as `PatternSpec(regex=pattern, types=None)`.
2. Apply `regex` (if present) to the text; fail validation if no match.
3. Determine the **shape** from the capture groups in `regex`:
   - No groups → single value (the full match, or the full text if no `regex`)
   - Unnamed groups → `tuple`
   - Named groups → `dict`
4. Apply `types` coercion element-by-element to the captured strings.

| `regex` groups    | `types` form        | Final Python type           |
|-------------------|---------------------|-----------------------------|
| None              | `None`              | `str`                       |
| None              | `"int"`             | `int`                       |
| Unnamed           | `None`              | `tuple[str, ...]`           |
| Unnamed           | `[int, float]`      | `tuple[int, float]`         |
| Named             | `None`              | `dict[str, str]`            |
| Named             | `{a: int, b: bool}` | `dict[str, int \| bool]`    |

### Nested list items

When `item.children` is defined, each list item is extracted as a dict:

```python
{
  "_text":   str,         # raw item text
  # named pattern groups merged in (or "_groups": tuple if unnamed)
  "child_name": ...,      # results from item.children schemas
}
```

### Repeat sections / groups

When `repeat` is set on a `section` or `group`, all matched instances are collected into a list under the node's `name` key. The `name` defaults to the snake_case of the section title when omitted.

---

## CLI (`cli.py`)

Built with [Click](https://click.palletsprojects.com/).

### Commands

```
mdstruct validate <schema> <document> [--format text|json]
mdstruct extract  <schema> <document> [--format yaml|json]
```

`validate` exits with code `0` on success, `1` when errors are found.  
`extract` always exits `0` if parsing succeeds (validation is not enforced).

### `validate` text output format

```
ERROR  root > Section[Overview] (line 5): missing required element
ERROR  root > Chapter 1 > table[results] > row 2 > col_count (line 23): pattern '\d+' not matched: 'N/A'
Total: 2 error(s)
```

---

## Dependencies

| Package      | Purpose                                        |
|--------------|------------------------------------------------|
| `pydantic ≥2`| Schema model definition & validation           |
| `pyyaml`     | YAML loading                                   |
| `mistletoe`  | Markdown parsing                               |
| `jsonschema` | Front matter validation via JSON Schema Draft 7|
| `click`      | CLI framework                                  |
| `rich`       | Formatted terminal output                      |

---

## Implementation order

1. `pyproject.toml` + package skeleton
2. `schema/models.py` — Pydantic models
3. `schema/loader.py` — YAML → model tree
4. `md_parser.py` — Markdown → internal AST
5. `validator.py` — validation logic
6. `extractor.py` — extraction logic
7. `cli.py` — CLI commands
8. `tests/` — tests + fixtures
