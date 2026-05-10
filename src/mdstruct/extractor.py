from __future__ import annotations

import json
import re
from typing import Any

from .md_parser import (
    AstNode, BlockquoteNode, CodeNode, DocumentNode, ListNode, SectionNode,
    TableNode, TextNode, ThematicBreakNode,
)
from .schema.models import (
    BlockquoteNode as SchBlockquote,
    CodeNode as SchCode,
    GroupNode as SchGroup,
    ListNode as SchList,
    NodeSchema,
    PatternField,
    PatternSpec,
    RootSchema,
    Schema,
    SectionNode as SchSection,
    TableNode as SchTable,
    TextNode as SchText,
    ThematicBreakNode as SchThematicBreak,
    TitleMatch,
    resolve_pattern,
)
from .validator import validate


class ExtractionError(Exception):
    pass


def extract(schema: Schema, doc: DocumentNode) -> dict:
    errors = validate(schema, doc)
    if errors:
        raise ExtractionError("Document does not conform to schema; run validate() first.")
    result: dict = {}
    _extract_root(schema.root, doc, result)
    return result


def _extract_root(root: RootSchema, doc: DocumentNode, out: dict) -> None:
    if root.frontmatter is not None and doc.frontmatter is not None:
        fm = root.frontmatter
        if fm.name:
            out[fm.name] = doc.frontmatter
        else:
            out.update(doc.frontmatter)
    _extract_children(root.children, doc.children, out, expected_level=1)


def _extract_children(
    schema_children: list[NodeSchema],
    ast_children: list,
    out: dict,
    expected_level: int,
) -> None:
    ai = 0
    for sn in schema_children:
        if sn.type == "group":
            if sn.name:
                group_out: dict = {}
                ai = _extract_group_named(sn, ast_children, ai, group_out, expected_level)
                repeat = sn.repeat
                if repeat is not None:
                    # already collected as list inside _extract_group_named
                    out[sn.name] = group_out.get(sn.name, [])
                else:
                    out[sn.name] = group_out
            else:
                ai = _extract_group_unnamed(sn, ast_children, ai, out, expected_level)
            continue

        repeat = getattr(sn, "repeat", None)
        if repeat is not None:
            items = []
            while ai < len(ast_children):
                ast_node = ast_children[ai]
                if not _node_type_matches(sn, ast_node):
                    break
                if sn.type == "section" and not _title_matches(sn.title, ast_node):
                    break
                val = _extract_one(sn, ast_node, expected_level)
                if val is not None and sn.name:
                    items.append(val)
                ai += 1
                if repeat.max is not None and len(items) >= repeat.max:
                    break
            if sn.name:
                out[sn.name] = items
        else:
            if ai >= len(ast_children):
                continue
            ast_node = ast_children[ai]
            if not _node_type_matches(sn, ast_node):
                continue
            val = _extract_one(sn, ast_node, expected_level)
            if sn.name is not None and val is not None:
                out[sn.name] = val
            elif sn.name is None and isinstance(val, dict):
                # unnamed node: merge children into parent scope
                out.update(val)
            ai += 1


def _extract_group_named(
    sn: SchGroup,
    ast_children: list,
    ai: int,
    out: dict,
    expected_level: int,
) -> int:
    repeat = sn.repeat
    if repeat is not None:
        items = []
        count = 0
        while ai < len(ast_children):
            group_out: dict = {}
            new_ai = _try_extract_group_children(sn, ast_children, ai, group_out, expected_level)
            if new_ai == ai:
                break
            items.append(group_out)
            ai = new_ai
            count += 1
            if repeat.max is not None and count >= repeat.max:
                break
        out[sn.name] = items
    else:
        group_out: dict = {}
        ai = _try_extract_group_children(sn, ast_children, ai, group_out, expected_level)
        out.update(group_out)
    return ai


def _try_extract_group_children(
    sn: SchGroup,
    ast_children: list,
    ai: int,
    out: dict,
    expected_level: int,
) -> int:
    inner_children = sn.children
    new_ai = ai
    for child in inner_children:
        if new_ai >= len(ast_children):
            break
        ast_node = ast_children[new_ai]
        if not _node_type_matches(child, ast_node):
            break
        val = _extract_one(child, ast_node, expected_level)
        if child.name is not None and val is not None:
            out[child.name] = val
        new_ai += 1
    return new_ai


def _extract_group_unnamed(
    sn: SchGroup,
    ast_children: list,
    ai: int,
    out: dict,
    expected_level: int,
) -> int:
    for child in sn.children:
        if child.type == "group":
            if child.name:
                child_out: dict = {}
                ai = _extract_group_named(child, ast_children, ai, child_out, expected_level)
                out.update(child_out)
            else:
                ai = _extract_group_unnamed(child, ast_children, ai, out, expected_level)
            continue
        repeat = getattr(child, "repeat", None)
        if repeat is not None:
            items = []
            while ai < len(ast_children):
                ast_node = ast_children[ai]
                if not _node_type_matches(child, ast_node):
                    break
                val = _extract_one(child, ast_node, expected_level)
                if val is not None:
                    items.append(val)
                ai += 1
                if repeat.max is not None and len(items) >= repeat.max:
                    break
            if child.name:
                out[child.name] = items
        else:
            if ai < len(ast_children):
                ast_node = ast_children[ai]
                if _node_type_matches(child, ast_node):
                    val = _extract_one(child, ast_node, expected_level)
                    if child.name is not None and val is not None:
                        out[child.name] = val
                    ai += 1
    return ai


def _node_type_matches(schema_node: NodeSchema, ast_node: AstNode) -> bool:
    t = schema_node.type
    if t == "section":
        return isinstance(ast_node, SectionNode)
    if t == "text":
        return isinstance(ast_node, TextNode)
    if t == "list":
        return isinstance(ast_node, ListNode)
    if t == "table":
        return isinstance(ast_node, TableNode)
    if t == "code":
        return isinstance(ast_node, CodeNode)
    if t == "blockquote":
        return isinstance(ast_node, BlockquoteNode)
    if t == "thematic_break":
        return isinstance(ast_node, ThematicBreakNode)
    if t == "group":
        return True
    return False


def _title_matches(title_spec: str | TitleMatch, ast_node: AstNode) -> bool:
    if not isinstance(ast_node, SectionNode):
        return False
    if isinstance(title_spec, str):
        return ast_node.title == title_spec
    spec = resolve_pattern(title_spec.pattern)
    if spec is not None and spec.regex is not None:
        return bool(re.fullmatch(spec.regex, ast_node.title))
    return True



def _extract_one(schema_node: NodeSchema, ast_node: AstNode, expected_level: int) -> Any:
    t = schema_node.type
    if t == "section":
        return _extract_section(schema_node, ast_node, expected_level)
    if t == "text":
        return _extract_text(schema_node, ast_node)
    if t == "list":
        return _extract_list(schema_node, ast_node)
    if t == "table":
        return _extract_table(schema_node, ast_node)
    if t == "code":
        return _extract_code(schema_node, ast_node)
    if t == "blockquote":
        return _extract_blockquote(schema_node, ast_node)
    if t == "thematic_break":
        return _extract_thematic_break(schema_node, ast_node)
    return None


def _extract_section(schema: SchSection, ast_node: AstNode, expected_level: int) -> dict:
    assert isinstance(ast_node, SectionNode)
    out: dict = {}
    # title capture
    if isinstance(schema.title, TitleMatch) and schema.title.capture:
        cap = schema.title.capture
        spec = resolve_pattern(schema.title.pattern)
        out[cap] = _extract_title_capture(spec, ast_node.title, schema.title.capture)
    _extract_children(schema.children, ast_node.children, out, expected_level + 1)
    return out


def _extract_title_capture(spec: PatternSpec | None, title: str, cap_name: str) -> Any:
    if spec is None or spec.regex is None:
        return title
    m = re.fullmatch(spec.regex, title)
    if not m:
        return title
    named = m.groupdict()
    unnamed = m.groups()
    if named:
        val = {k: v for k, v in named.items()}
        if spec.types and isinstance(spec.types, dict):
            val = {k: _coerce(v, spec.types.get(k, "str")) for k, v in val.items()}
        return val
    if unnamed:
        val_list = list(unnamed)
        if spec.types and isinstance(spec.types, list):
            val_list = [_coerce(v, t) for v, t in zip(val_list, spec.types)]
        elif spec.types and isinstance(spec.types, str):
            val_list = [_coerce(v, spec.types) for v in val_list]
        return tuple(val_list)
    full = m.group(0)
    if spec.types and isinstance(spec.types, str):
        return _coerce(full, spec.types)
    return full


def _extract_text(schema: SchText, ast_node: AstNode) -> Any:
    assert isinstance(ast_node, TextNode)
    return _extract_by_pattern(schema.pattern, ast_node.text)


def _extract_blockquote(schema: SchBlockquote, ast_node: AstNode) -> Any:
    assert isinstance(ast_node, BlockquoteNode)
    return _extract_by_pattern(schema.pattern, ast_node.text)


def _extract_by_pattern(pattern: PatternField | None, text: str) -> Any:
    spec = resolve_pattern(pattern)
    if spec is None:
        return text
    if spec.regex is None:
        # type coercion only
        if spec.types and isinstance(spec.types, str):
            return _coerce(text, spec.types)
        return text

    m = re.fullmatch(spec.regex, text)
    if not m:
        return text

    named = m.groupdict()
    unnamed = m.groups()

    if named:
        val = {k: v for k, v in named.items()}
        if spec.types and isinstance(spec.types, dict):
            val = {k: _coerce(v, spec.types.get(k, "str")) for k, v in val.items()}
        return val

    if unnamed:
        val_list = list(unnamed)
        if spec.types and isinstance(spec.types, list):
            val_list = [_coerce(v, t) for v, t in zip(val_list, spec.types)]
        return tuple(val_list)

    full = m.group(0)
    if spec.types and isinstance(spec.types, str):
        return _coerce(full, spec.types)
    return full


def _extract_list(schema: SchList, ast_node: AstNode) -> list:
    assert isinstance(ast_node, ListNode)
    result = []
    for item in ast_node.items:
        if schema.item.children:
            item_out: dict = {}
            # pattern capture merged in
            if schema.item.pattern:
                val = _extract_by_pattern(schema.item.pattern, item.text)
                if isinstance(val, dict):
                    item_out.update(val)
                elif isinstance(val, tuple):
                    item_out["_groups"] = val
                else:
                    item_out["_text"] = val
            # nested list children
            nested_ast = item.children[0] if item.children else None
            for child_schema in schema.item.children:
                if nested_ast is not None and _node_type_matches(child_schema, nested_ast):
                    val = _extract_one(child_schema, nested_ast, 0)
                    if child_schema.name is not None:
                        item_out[child_schema.name] = val
            result.append(item_out)
        else:
            result.append(_extract_by_pattern(schema.item.pattern, item.text))
    return result


def _extract_table(schema: SchTable, ast_node: AstNode) -> list[dict]:
    assert isinstance(ast_node, TableNode)
    if not schema.columns:
        return [{h: cell for h, cell in zip(ast_node.headers, row)} for row in ast_node.rows]

    header_index = {col.header: ast_node.headers.index(col.header)
                    for col in schema.columns if col.header in ast_node.headers}
    rows = []
    for row in ast_node.rows:
        row_dict: dict = {}
        for col in schema.columns:
            if col.header not in header_index:
                continue
            idx = header_index[col.header]
            cell = row[idx] if idx < len(row) else ""
            row_dict[col.name] = _extract_by_pattern(col.pattern, cell)
        rows.append(row_dict)
    return rows


def _extract_code(schema: SchCode, ast_node: AstNode) -> dict:
    assert isinstance(ast_node, CodeNode)
    return {"language": ast_node.language, "content": ast_node.content}


def _extract_thematic_break(schema: SchThematicBreak, ast_node: AstNode) -> str | None:
    assert isinstance(ast_node, ThematicBreakNode)
    if schema.name:
        return ast_node.raw
    return None


def _coerce(value: str, type_name: str) -> Any:
    if type_name == "str":
        return value
    if type_name == "int":
        return int(value)
    if type_name == "float":
        return float(value)
    if type_name == "bool":
        low = value.lower()
        if low in ("true", "yes", "y", "t", "1"):
            return True
        if low in ("false", "no", "n", "f", "0"):
            return False
        raise ValueError(f"Cannot coerce {value!r} to bool")
    if type_name == "json":
        return json.loads(value)
    return value
