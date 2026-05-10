# Schema Syntax Reference

mdstruct schemas are written in YAML and describe the expected structure of a Markdown document.

---

## Top-level structure

```yaml
version: "1.0"
root:
  frontmatter: ...   # optional
  children:
    - type: section
      ...
```

| Field         | Type   | Required | Description                             |
|---------------|--------|----------|-----------------------------------------|
| `version`     | string | yes      | Schema version (`"1.0"`)                |
| `root`        | object | yes      | Root document descriptor                |
| `root.frontmatter` | object | no  | YAML front matter schema (see below)    |
| `root.children`    | list   | yes | Ordered list of top-level schema nodes  |

---

## Node types

Each node in `children` (including nested `children`) has a `type` field:

| type           | Matches                                    | Extracted as                         |
|----------------|--------------------------------------------|--------------------------------------|
| `section`      | Markdown heading (`#`, `##`, …)            | dict / list (when `repeat`)          |
| `group`        | A logical container — no Markdown element  | dict (named) or flat into parent     |
| `text`         | Paragraph block                            | `str`, `tuple`, or `dict`            |
| `list`         | Bullet or numbered list                    | `list[str \| tuple \| dict]`         |
| `task_list`    | Task list (`- [ ]` / `- [x]`)              | `list[{text, checked}]`              |
| `table`        | Markdown table                             | `list[dict]`                         |
| `code`         | Fenced or indented code block              | `{language, content}`                |
| `blockquote`   | Block quote (`>`)                          | `str`, `tuple`, or `dict`            |
| `thematic_break` | Horizontal rule (`---`, `***`, `___`)    | `str` (raw text) when `name` is set  |

---

## Common parameters

These parameters apply to every node type unless noted otherwise.

| Parameter  | Type   | Default | Description                                                  |
|------------|--------|---------|--------------------------------------------------------------|
| `name`     | string | null    | Key name in the extracted output. Omit to discard. Required when `repeat` is set. |
| `required` | bool   | `true`  | Whether a missing element is a validation error.            |
| `repeat`   | object | null    | Allow the node to appear multiple times (see below).        |

### `repeat`

```yaml
repeat:
  min: 1      # minimum occurrences (default 0)
  max: null   # maximum occurrences; null = unlimited
```

When `repeat` is set, the extracted value becomes a **list** instead of a single item. `name` is required on any repeating node; omitting it is a schema error.

---

## `section`

Matches a Markdown heading. The heading level is inferred from nesting depth: sections directly under `root.children` match `h1`, one level deeper matches `h2`, and so on. There is no `level` parameter.

```yaml
- type: section
  title: "Introduction"     # exact match
  required: true
  ordered: true             # shorthand: apply ordered/allow_extra to all children
  allow_extra: false
  children:
    - type: section         # this matches h2 headings
      title: "Details"
      children:
        - ...
```

| Parameter     | Type             | Default | Description                                             |
|---------------|------------------|---------|---------------------------------------------------------|
| `title`       | string or object | —       | Title match rule (see below)                            |
| `ordered`     | bool             | `true`  | Whether children must appear in schema order            |
| `allow_extra` | bool             | `false` | Whether extra children are allowed                      |
| `children`    | list             | `[]`    | Child schema nodes                                      |

`ordered` and `allow_extra` on a `section` are shorthand for wrapping `children` in an implicit `group`. The matching rules are the same as described in [`group`](#group).

### Title matching

```yaml
title: "Exact Title"           # literal string match

title:
  pattern: 'Chapter \d+'       # regex match against heading text
  capture: chapter_title       # key name for the extracted value (see below)
```

The value stored under `capture` follows the same capture group rules as `pattern` elsewhere:

| `pattern` form          | Value stored under `capture`                  |
|-------------------------|-----------------------------------------------|
| No capture groups       | Full match string                             |
| Unnamed groups `(...)`  | `tuple` of group values                       |
| Named groups `(?P<>…)`  | `dict` of named group values                  |

When `repeat` is used on a section, extracted results are collected into a list under the `name` key (`name` is required; see [Common parameters](#common-parameters)).

```yaml
# pattern has no capture groups → capture stores the full match string
# Extracted as: {"chapter_title": "Chapter 1", ...}
- type: section
  title:
    pattern: 'Chapter \d+'
    capture: chapter_title
  name: chapters
  repeat:
    min: 0
    max: null

# pattern has a named group → capture stores a dict
# Extracted as: {"chapter_title": {"num": "1"}, ...}
- type: section
  title:
    pattern: 'Chapter (?P<num>\d+)'
    capture: chapter_title
  name: chapters
  repeat:
    min: 0
    max: null
```

---

## `group`

A logical container that controls matching flexibility for a set of child nodes. No Markdown element corresponds to a group — it is a schema-only concept.

```yaml
- type: group
  name: details          # optional; omit to flatten into parent scope
  required: true
  ordered: false         # children may appear in any order
  allow_extra: true      # unknown elements between children are allowed
  repeat:
    min: 0
    max: null
  children:
    - type: table
      name: params
      required: true
    - type: code
      name: example
      required: false
```

| Parameter     | Type         | Default | Description                                               |
|---------------|--------------|---------|-----------------------------------------------------------|
| `name`        | string       | null    | Extracted key. If omitted, children are merged into parent scope. |
| `required`    | bool         | `true`  | Whether at least one match is required.                   |
| `ordered`     | bool         | `true`  | Children must appear in schema-defined order.             |
| `allow_extra` | bool         | `false` | Unknown elements between children are silently skipped.   |
| `repeat`      | object       | null    | Allow the group to repeat.                                |
| `children`    | list         | —       | Child schema nodes, each with their own `required`.       |

### `ordered` × `allow_extra` behaviour

| `ordered` | `allow_extra` | Matching behaviour                                                      |
|-----------|---------------|-------------------------------------------------------------------------|
| `true`    | `false`       | Strict sequential match. Extra elements cause an error. **(default)**  |
| `true`    | `true`        | Children must appear in order, but unknown elements may appear between them. |
| `false`   | `false`       | All schema elements must be present, in any order, with no extras.      |
| `false`   | `true`        | Required elements must appear somewhere; order and extras are ignored.  |

---

## `text`

Matches a paragraph block.

```yaml
- type: text
  name: body
  required: false
  pattern: 'Version:\s+.+'   # optional regex validated against plain text
```

| Parameter | Type   | Default | Description                                    |
|-----------|--------|---------|------------------------------------------------|
| `pattern` | string | null    | Regex pattern matched against the plain text.  |

### Extraction type

Determined by capture groups in `pattern` (see [Pattern capture groups](#pattern-capture-groups-and-type-coercion)).

---

## `list`

Matches a bullet (`-`, `*`, `+`) or numbered (`1.`) list.

```yaml
- type: list
  name: items
  required: false
  numbered: false   # true = numbered list, false = bullet, null = either
  item:
    pattern: '(?P<key>[^:]+):\s*(?P<value>.+)'
    children:       # optional nested list schema
      - type: list
        name: subitems
        required: false
        item:
          pattern: '.+'
```

| Parameter      | Type    | Default | Description                                               |
|----------------|---------|---------|-----------------------------------------------------------|
| `numbered`     | bool    | null    | `true` = numbered list, `false` = bullet, `null` = either |
| `item`         | object  | null    | Optional item schema.                                     |
| `item.pattern` | string  | null    | Regex matched against each item's plain text.             |
| `item.children`| list    | null    | Schema for nested lists under each item.                  |

### Nested lists

When `item.children` is present, each item is extracted as a **dict**:

| Field            | Content                                                          |
|------------------|------------------------------------------------------------------|
| `_text`          | Raw item text (always present)                                   |
| `<group_name>`   | Named capture groups from `pattern`, merged into the dict        |
| `_groups`        | Unnamed capture groups as a tuple (only when no named groups)    |
| `<child.name>`   | Extracted value for each named child node in `item.children`     |

When `item.children` is absent, the extraction type follows the [capture group rules](#pattern-capture-groups-and-type-coercion).

---

## `task_list`

Matches a GFM task list (items starting with `[ ]` or `[x]`).

```yaml
- type: task_list
  name: todos
  required: false
  item:
    pattern: '.+'
    children:       # optional nested list schema
      - type: list
        name: subitems
        required: false
        item:
          pattern: '.+'
```

| Parameter       | Type   | Default | Description                                                 |
|-----------------|--------|---------|-------------------------------------------------------------|
| `item`          | object | null    | Optional item schema.                                       |
| `item.pattern`  | string | null    | Regex matched against each item's plain text.               |
| `item.children` | list   | null    | Schema for nested lists under each item (same as `list`).   |

Each item is always extracted as `{"text": str, "checked": bool}`.

When `item.children` is present, each item is extracted as a **dict** instead:

| Field            | Content                                                          |
|------------------|------------------------------------------------------------------|
| `_text`          | Raw item text (always present)                                   |
| `<group_name>`   | Named capture groups from `pattern`, merged into the dict        |
| `_groups`        | Unnamed capture groups as a tuple (only when no named groups)    |
| `<child.name>`   | Extracted value for each named child node in `item.children`     |

---

## `table`

Matches a Markdown pipe table.

```yaml
- type: table
  name: results
  required: false
  columns:
    - header: "Name"
      name: col_name
    - header: "Count"
      name: col_count
      pattern: '\d+'
```

| Parameter         | Type   | Default | Description                                       |
|-------------------|--------|---------|---------------------------------------------------|
| `columns`         | list   | `[]`    | Expected column definitions.                      |
| `columns[].header`| string | —       | Exact column header text.                         |
| `columns[].name`  | string | —       | Key name in extracted row dicts.                  |
| `columns[].pattern`| string or object | null | Regex (or [pattern object with `types`](#pattern-capture-groups-and-type-coercion)) validated against each cell value. |

Extraction: `list[dict]` — one dict per row, keyed by column `name`.

---

## `code`

Matches a fenced (` ``` `) or indented code block.

```yaml
- type: code
  name: example
  required: false
  language: python    # optional; validates the language identifier
```

Extraction: `{"language": str | null, "content": str}`.

---

## `blockquote`

Matches a block quote (`> ...`).

```yaml
- type: blockquote
  name: note
  required: false
  pattern: 'NOTE:.*'
```

Extraction type follows the [capture group rules](#pattern-capture-groups-and-type-coercion) applied to the quote's plain text.

---

## `thematic_break`

Matches a horizontal rule (`---`, `***`, `___`).

```yaml
- type: thematic_break
  name: divider   # optional; if set, raw text (e.g. "---") is extracted
  required: false
```

When `name` is set, the raw text of the horizontal rule (e.g. `---`, `***`, or `___`) is extracted as a `str`. When `name` is omitted, no data is extracted and the node is used only for structural validation.

---

## `frontmatter`

Matches a YAML front matter block at the very start of the document. Validation is delegated to a standard [JSON Schema](https://json-schema.org/) object.

```yaml
root:
  frontmatter:
    required: false
    name: meta      # optional: extract under this key instead of merging into root
    schema:         # standard JSON Schema (Draft 7)
      type: object
      properties:
        author:
          type: string
        date:
          type: string
          pattern: '^\d{4}-\d{2}-\d{2}$'
      required: [author]
```

| Parameter  | Type        | Default | Description                                                       |
|------------|-------------|---------|-------------------------------------------------------------------|
| `required` | bool        | `false` | Whether front matter must be present.                             |
| `name`     | string      | null    | If set, the front matter dict is extracted under this key. If omitted, all properties are merged into the root extraction result. |
| `schema`   | JSON Schema | null    | Standard JSON Schema used to validate the parsed front matter.    |

Extraction: the front matter is returned as a plain Python dict (exactly as parsed from YAML). JSON Schema validation runs against this dict; no additional type coercion is applied by mdstruct.

---

## Pattern capture groups and type coercion

The `pattern` field accepts a **string** (regex only, shorthand) or an **object** (regex + optional type coercion).

### String form (shorthand)

```yaml
pattern: '\d{4}-\d{2}-\d{2}'
```

Validates content against the regex. All extracted values are `str`.

### Object form

```yaml
pattern:
  regex: '...'    # optional – if omitted, matches any content
  types: ...      # optional – coerce extracted value(s) to the given type(s)
```

Both fields are optional. Omitting `regex` is the canonical way to add type coercion without regex validation.

### Capture groups and output shape

The presence and kind of capture groups in `regex` determines the **shape** of the extracted value, regardless of whether `types` is specified.

| `regex` form                   | Extracted shape     | Example regex                            |
|--------------------------------|---------------------|------------------------------------------|
| No capture groups              | single value        | `'\d{4}-\d{2}-\d{2}'`                   |
| Unnamed groups `(...)`         | `tuple`             | `'v(\d+)\.(\d+)\.(\d+)'`               |
| Named groups `(?P<name>...)`   | `dict`              | `'(?P<y>\d{4})-(?P<m>\d{2})'`          |
| Mixed (named + unnamed)        | — (schema error)    | mixing named and unnamed groups is invalid |

> **Error:** Mixing named and unnamed capture groups in the same `regex` is a schema error. Use either all named groups (`(?P<name>...)`) or all unnamed groups (`(...)`).

### `types` — type coercion

`types` must match the shape implied by the capture groups:

| Capture groups      | `types` form       | Example                          | Result type           |
|---------------------|--------------------|----------------------------------|-----------------------|
| None (single value) | type name (string) | `types: int`                     | `int`                 |
| Unnamed groups      | list of type names | `types: [int, int, int]`         | `tuple[int, ...]`     |
| Named groups        | dict `{name: type}`| `types: {year: int, month: int}` | `dict[str, int\|...]` |

Supported type names:

| Name    | Python type | Notes                                          |
|---------|-------------|------------------------------------------------|
| `str`   | `str`       | Default. No-op.                                |
| `int`   | `int`       | `int(value)`                                   |
| `float` | `float`     | `float(value)`                                 |
| `bool`  | `bool`      | Case-insensitive. `true`/`yes`/`y`/`t`/`1` → `True`; `false`/`no`/`n`/`f`/`0` → `False` |
| `json`  | any         | `json.loads(value)`                            |

### Examples

```yaml
# No groups, type cast → int
- type: text
  name: port
  pattern:
    regex: '\d+'
    types: int
# extraction: 8080

# Unnamed groups, per-group types → tuple[int, int, int]
- type: text
  name: version
  pattern:
    regex: 'v(\d+)\.(\d+)\.(\d+)'
    types: [int, int, int]
# extraction: (1, 2, 3)

# Named groups, per-group types → dict[str, int]
- type: text
  name: date
  pattern:
    regex: '(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})'
    types: {year: int, month: int, day: int}
# extraction: {"year": 2025, "month": 1, "day": 1}

# Type cast only (no regex validation)
- type: text
  name: count
  pattern:
    types: int
# extraction: 42  (whole paragraph text cast to int)

# Table column with type cast
- header: "Price"
  name: price
  pattern:
    regex: '\d+\.\d{2}'
    types: float
# each cell extracted as float

# List items with unnamed groups and types
- type: list
  name: coords
  item:
    pattern:
      regex: '(\d+),\s*(\d+)'
      types: [int, int]
# extraction: [(10, 20), (30, 40), ...]
```

---

## Full extraction output example

Given the schema below and a matching document, `extract()` returns:

```python
{
  # frontmatter — merged into root (name omitted) or nested under name key
  "author": "Alice",
  "date": "2025-01-01",

  # plain text (no capture groups) → str
  "overview_body": "This is the overview.",

  # unnamed capture groups → tuple
  "version": ("1", "2", "3"),

  # named capture groups → dict
  "date_info": {"year": "2025", "month": "01", "day": "01"},

  # repeat section → list of dicts
  "chapters": [
    {
      "chapter_title": "Chapter 1",   # from title.capture

      # named group → dict for each table column
      "results": [
        {"col_name": "Alice", "col_count": "3"},
      ],

      # list with no capture → list[str]
      "plain_items": ["item A", "item B"],

      # list with unnamed groups → list[tuple]
      "kv_items": [("key1", "val1"), ("key2", "val2")],

      # list with named groups → list[dict]
      "named_items": [{"key": "foo", "value": "bar"}],

      # nested list (item.children present) → list[dict]
      "entries": [
        {
          "_text": "Alice",
          "name": "Alice",
          "scores": [
            {"label": "math", "value": "90"},
            {"label": "english", "value": "85"},
          ],
        },
      ],

      # task_list → list[{text, checked}]
      "tasks": [
        {"text": "Do something", "checked": True},
        {"text": "Do another",   "checked": False},
      ],

      # named group → dict
      "api_details": {
        "example": {"language": "python", "content": "print('hello')\n"},
        "params": [{"col_name": "x", "col_count": "1"}],
        "note": "NOTE: important thing",
      },
    },
  ],
}
```
