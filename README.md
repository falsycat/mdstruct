# mdstruct

Define the structure of a Markdown document as a YAML schema, then **validate** existing documents against it and **extract** structured data from them.

## Features

- **Schema-driven validation** — describe expected headings, paragraphs, tables, lists, code blocks, and more in YAML; get a precise list of violations with line numbers.
- **Structured extraction** — pull data out of Markdown into Python dicts, lists, tuples, or JSON/YAML; no bespoke parsing code required.
- **Flexible matching** — control whether children must appear in order, whether extra elements are allowed, and whether sections may repeat.
- **Regex patterns with capture groups** — validate content with regular expressions and extract named or positional capture groups directly into the output.
- **Nested lists** — describe arbitrarily deep list structures in the schema.
- **All common Markdown elements** — sections, paragraphs, bullet and numbered lists, tables, code blocks, block quotes, horizontal rules, and YAML front matter.
- **Python library + CLI** — use programmatically or from the terminal.

## Installation

```bash
pip install git+https://github.com/falsycat/mdstruct
```

Requires Python 3.11+.

## Quick start

### 1. Write a schema

```yaml
# schema.yaml
version: "1.0"
root:
  frontmatter:
    required: false
    schema:
      type: object
      properties:
        author:
          type: string
      required: [author]
  children:
    - type: section
      title: "Overview"
      required: true
      children:
        - type: text
          name: overview

    - type: section
      title:
        pattern: 'Chapter (?P<num>\d+)'
        capture: chapter_title
      name: chapters
      required: false
      repeat:
        min: 1
        max: null
      children:
        - type: text
          name: body
          required: false
        - type: table
          name: data
          required: false
          columns:
            - header: "Name"
              name: item_name
            - header: "Value"
              name: item_value
              pattern: '\d+'
```

### 2. Write a document

```markdown
---
author: Jane Doe
---

## Overview

This is the overview.

## Chapter 1

This chapter covers the basics.

| Name  | Value |
|-------|-------|
| Alpha | 42    |
```

### 3. Validate a document

```bash
mdstruct validate schema.yaml document.md
```

```
ERROR  root > section[Overview] (line 3): missing required element
Total: 1 error(s)
```

Exit code is `0` on success, `1` when errors are found.

### 4. Extract data

```bash
mdstruct extract schema.yaml document.md
```

```yaml
overview: This is the overview.
chapters:
  - chapter_title:
      num: "1"
    body: This chapter covers the basics.
    data:
      - item_name: Alpha
        item_value: "42"
```

Use `--format json` for JSON output.

## CLI reference

```
mdstruct validate <schema> <document> [--format text|json]
mdstruct extract  <schema> <document> [--format yaml|json]
```

| Command    | Option     | Default | Description      |
|------------|------------|---------|------------------|
| `validate` | `--format` | `text`  | `text` or `json` |
| `extract`  | `--format` | `yaml`  | `yaml` or `json` |

**Exit codes:** `validate` returns `0` on success, `1` when errors are found. `extract` returns `0` on success, `1` if the document does not conform to the schema — no detail is shown; run `validate` first to see errors.

## Python API

```python
from mdstruct.schema.loader import load_schema
from mdstruct.md_parser import parse_markdown
from mdstruct.validator import validate
from mdstruct.extractor import extract

schema = load_schema("schema.yaml")

with open("document.md") as f:
    doc = parse_markdown(f.read())

# Validation
errors = validate(schema, doc)
for err in errors:
    print(f"{err.path} (line {err.line}): {err.message}")

# Always validate before extracting; extract() raises ExtractionError on invalid documents
if not errors:
    data = extract(schema, doc)
    print(data["overview"])
    print(data["chapters"][0]["data"])
```

## Documentation

- [Schema syntax reference](doc/syntax.md) — all node types, parameters, pattern/type coercion, and extraction output format
- [Architecture](doc/arch.md) — internal design, AST, validation algorithm, and module structure

## Development

```bash
git clone https://github.com/falsycat/mdstruct
cd mdstruct
pip install -e ".[dev]"
pytest tests/
```
