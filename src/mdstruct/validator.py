from __future__ import annotations

import json
import re
from dataclasses import dataclass

import jsonschema

from .md_parser import (
    BlockquoteNode, CodeNode, DocumentNode, ListNode, SectionNode,
    TableNode, TextNode, ThematicBreakNode,
)
from .schema.models import (
    BlockquoteNode as SchBlockquote,
    CodeNode as SchCode,
    FrontmatterSchema,
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
)

AstNode = SectionNode | TextNode | ListNode | TableNode | CodeNode | BlockquoteNode | ThematicBreakNode


@dataclass
class ValidationError:
    path: str
    error_type: str
    message: str
    line: int | None


def validate(schema: Schema, doc: DocumentNode) -> list[ValidationError]:
    errors: list[ValidationError] = []
    _validate_root(schema.root, doc, "root", errors)
    return errors


def _validate_root(root: RootSchema, doc: DocumentNode, path: str, errors: list[ValidationError]) -> None:
    if root.frontmatter is not None:
        _validate_frontmatter(root.frontmatter, doc, path, errors)
    _match_group_children(
        root.children, doc.children, path, errors,
        ordered=True, allow_extra=False, expected_level=1,
    )


def _validate_frontmatter(
    schema: FrontmatterSchema,
    doc: DocumentNode,
    path: str,
    errors: list[ValidationError],
) -> None:
    if doc.frontmatter is None:
        if schema.required:
            errors.append(ValidationError(
                path=path,
                error_type="missing_element",
                message="missing required frontmatter",
                line=None,
            ))
        return
    if schema.schema_ is not None:
        try:
            jsonschema.validate(doc.frontmatter, schema.schema_)
        except jsonschema.ValidationError as e:
            errors.append(ValidationError(
                path=f"{path} > frontmatter",
                error_type="missing_field",
                message=str(e.message),
                line=None,
            ))


def _resolve_pattern(pattern: PatternField | None) -> PatternSpec | None:
    if pattern is None:
        return None
    if isinstance(pattern, str):
        return PatternSpec(regex=pattern)
    return pattern


def _check_pattern(spec: PatternSpec | None, text: str, path: str, line: int | None, errors: list[ValidationError]) -> bool:
    if spec is None:
        return True
    if spec.regex is not None:
        m = re.fullmatch(spec.regex, text)
        if not m:
            errors.append(ValidationError(
                path=path,
                error_type="pattern_mismatch",
                message=f"pattern '{spec.regex}' not matched: '{text}'",
                line=line,
            ))
            return False
    return True


def _node_matches_schema(ast_node: AstNode, schema_node: NodeSchema) -> bool:
    """Return True if the ast_node *could* match schema_node (type-level check)."""
    if schema_node.type == "section":
        return isinstance(ast_node, SectionNode)
    if schema_node.type == "text":
        return isinstance(ast_node, TextNode)
    if schema_node.type == "list":
        return isinstance(ast_node, ListNode)
    if schema_node.type == "table":
        return isinstance(ast_node, TableNode)
    if schema_node.type == "code":
        return isinstance(ast_node, CodeNode)
    if schema_node.type == "blockquote":
        return isinstance(ast_node, BlockquoteNode)
    if schema_node.type == "thematic_break":
        return isinstance(ast_node, ThematicBreakNode)
    if schema_node.type == "group":
        return True  # groups match any node via their children
    return False


def _ast_type_name(node: AstNode) -> str:
    return type(node).__name__.replace("Node", "").lower()


def _validate_node(
    schema_node: NodeSchema,
    ast_node: AstNode,
    path: str,
    errors: list[ValidationError],
    expected_level: int,
) -> None:
    t = schema_node.type

    if t == "section":
        _validate_section(schema_node, ast_node, path, errors, expected_level)
    elif t == "text":
        _validate_text(schema_node, ast_node, path, errors)
    elif t == "list":
        _validate_list(schema_node, ast_node, path, errors)
    elif t == "table":
        _validate_table(schema_node, ast_node, path, errors)
    elif t == "code":
        _validate_code(schema_node, ast_node, path, errors)
    elif t == "blockquote":
        _validate_blockquote(schema_node, ast_node, path, errors)
    elif t == "thematic_break":
        _validate_thematic_break(schema_node, ast_node, path, errors)
    elif t == "group":
        _validate_group_node(schema_node, ast_node, path, errors, expected_level)


def _validate_section(
    schema: SchSection,
    ast_node: AstNode,
    path: str,
    errors: list[ValidationError],
    expected_level: int,
) -> None:
    if not isinstance(ast_node, SectionNode):
        errors.append(ValidationError(path=path, error_type="wrong_type",
            message=f"expected section, got {_ast_type_name(ast_node)}", line=getattr(ast_node, "line", None)))
        return

    node_path = f"{path} > section[{ast_node.title}]"

    if ast_node.level != expected_level:
        errors.append(ValidationError(
            path=node_path, error_type="level_mismatch",
            message=f"expected heading level {expected_level}, got {ast_node.level}",
            line=ast_node.line,
        ))

    _check_title(schema.title, ast_node, node_path, errors)
    _match_group_children(
        schema.children, ast_node.children, node_path, errors,
        ordered=schema.ordered, allow_extra=schema.allow_extra,
        expected_level=expected_level + 1,
    )


def _check_title(
    title_spec: str | TitleMatch,
    ast_node: SectionNode,
    path: str,
    errors: list[ValidationError],
) -> None:
    if isinstance(title_spec, str):
        if ast_node.title != title_spec:
            errors.append(ValidationError(
                path=path, error_type="title_mismatch",
                message=f"expected title '{title_spec}', got '{ast_node.title}'",
                line=ast_node.line,
            ))
    else:
        spec = _resolve_pattern(title_spec.pattern)
        if spec is not None and spec.regex is not None:
            m = re.fullmatch(spec.regex, ast_node.title)
            if not m:
                errors.append(ValidationError(
                    path=path, error_type="title_mismatch",
                    message=f"title '{ast_node.title}' did not match pattern '{spec.regex}'",
                    line=ast_node.line,
                ))


def _validate_text(schema: SchText, ast_node: AstNode, path: str, errors: list[ValidationError]) -> None:
    if not isinstance(ast_node, TextNode):
        errors.append(ValidationError(path=path, error_type="wrong_type",
            message=f"expected text, got {_ast_type_name(ast_node)}", line=getattr(ast_node, "line", None)))
        return
    node_path = f"{path} > text[{schema.name or ''}]"
    spec = _resolve_pattern(schema.pattern)
    _check_pattern(spec, ast_node.text, node_path, ast_node.line, errors)


def _validate_list(schema: SchList, ast_node: AstNode, path: str, errors: list[ValidationError]) -> None:
    if not isinstance(ast_node, ListNode):
        errors.append(ValidationError(path=path, error_type="wrong_type",
            message=f"expected list, got {_ast_type_name(ast_node)}", line=getattr(ast_node, "line", None)))
        return
    node_path = f"{path} > list[{schema.name or ''}]"
    if schema.numbered is not None and ast_node.ordered != schema.numbered:
        expected = "numbered" if schema.numbered else "bullet"
        actual = "numbered" if ast_node.ordered else "bullet"
        errors.append(ValidationError(path=node_path, error_type="wrong_type",
            message=f"expected {expected} list, got {actual}", line=ast_node.line))
        return
    spec = _resolve_pattern(schema.item.pattern)
    for i, item in enumerate(ast_node.items):
        item_path = f"{node_path} > item {i + 1}"
        _check_pattern(spec, item.text, item_path, item.line, errors)
        if schema.item.children:
            nested_list = item.children[0] if item.children else None
            for child_schema in schema.item.children:
                if nested_list is not None:
                    _validate_node(child_schema, nested_list, item_path, errors, expected_level=0)
                elif getattr(child_schema, "required", True):
                    errors.append(ValidationError(
                        path=item_path, error_type="missing_element",
                        message=f"missing required {child_schema.type}", line=item.line,
                    ))


def _validate_table(schema: SchTable, ast_node: AstNode, path: str, errors: list[ValidationError]) -> None:
    if not isinstance(ast_node, TableNode):
        errors.append(ValidationError(path=path, error_type="wrong_type",
            message=f"expected table, got {_ast_type_name(ast_node)}", line=getattr(ast_node, "line", None)))
        return
    node_path = f"{path} > table[{schema.name or ''}]"
    header_index: dict[str, int] = {}
    for col in schema.columns:
        if col.header not in ast_node.headers:
            errors.append(ValidationError(path=node_path, error_type="missing_column",
                message=f"column '{col.header}' not found", line=ast_node.line))
        else:
            header_index[col.header] = ast_node.headers.index(col.header)

    for row_i, row in enumerate(ast_node.rows):
        for col in schema.columns:
            if col.header not in header_index:
                continue
            idx = header_index[col.header]
            cell = row[idx] if idx < len(row) else ""
            col_path = f"{node_path} > row {row_i + 1} > {col.name}"
            spec = _resolve_pattern(col.pattern)
            _check_pattern(spec, cell, col_path, ast_node.line, errors)


def _validate_code(schema: SchCode, ast_node: AstNode, path: str, errors: list[ValidationError]) -> None:
    if not isinstance(ast_node, CodeNode):
        errors.append(ValidationError(path=path, error_type="wrong_type",
            message=f"expected code, got {_ast_type_name(ast_node)}", line=getattr(ast_node, "line", None)))
        return
    node_path = f"{path} > code[{schema.name or ''}]"
    if schema.language is not None and ast_node.language != schema.language:
        errors.append(ValidationError(path=node_path, error_type="wrong_language",
            message=f"expected language '{schema.language}', got '{ast_node.language}'",
            line=ast_node.line))


def _validate_blockquote(schema: SchBlockquote, ast_node: AstNode, path: str, errors: list[ValidationError]) -> None:
    if not isinstance(ast_node, BlockquoteNode):
        errors.append(ValidationError(path=path, error_type="wrong_type",
            message=f"expected blockquote, got {_ast_type_name(ast_node)}", line=getattr(ast_node, "line", None)))
        return
    node_path = f"{path} > blockquote[{schema.name or ''}]"
    spec = _resolve_pattern(schema.pattern)
    _check_pattern(spec, ast_node.text, node_path, ast_node.line, errors)


def _validate_thematic_break(schema: SchThematicBreak, ast_node: AstNode, path: str, errors: list[ValidationError]) -> None:
    if not isinstance(ast_node, ThematicBreakNode):
        errors.append(ValidationError(path=path, error_type="wrong_type",
            message=f"expected thematic_break, got {_ast_type_name(ast_node)}", line=getattr(ast_node, "line", None)))


def _validate_group_node(
    schema: SchGroup,
    ast_node: AstNode,
    path: str,
    errors: list[ValidationError],
    expected_level: int,
) -> None:
    node_path = f"{path} > group[{schema.name or ''}]"
    # group has no direct AST counterpart; validate children against the same ast children list
    # This is only called when a group is directly matched to a single node — not the primary path.
    # The primary path is _match_group_children called with the group's children.
    pass


def _match_group_children(
    schema_children: list[NodeSchema],
    ast_children: list,
    path: str,
    errors: list[ValidationError],
    *,
    ordered: bool,
    allow_extra: bool,
    expected_level: int,
) -> None:
    # Expand group nodes (unnamed groups are flattened, named groups create a new scope)
    flat_schema = _expand_groups(schema_children, path, errors, expected_level)
    _do_match(flat_schema, ast_children, path, errors, ordered, allow_extra, expected_level)


def _expand_groups(
    schema_children: list[NodeSchema],
    path: str,
    errors: list[ValidationError],
    expected_level: int,
) -> list[tuple[NodeSchema, str, int]]:
    """Return list of (schema_node, path, expected_level) with groups flattened."""
    result = []
    for node in schema_children:
        if node.type == "group":
            if node.name:
                result.append((node, path, expected_level))
            else:
                inner = _expand_groups(node.children, path, errors, expected_level)
                result.extend(inner)
        else:
            result.append((node, path, expected_level))
    return result


def _is_repeat_node(schema_node: NodeSchema) -> bool:
    return getattr(schema_node, "repeat", None) is not None


def _schema_node_required(schema_node: NodeSchema) -> bool:
    repeat = getattr(schema_node, "repeat", None)
    if repeat is not None:
        return repeat.min > 0
    return getattr(schema_node, "required", True)


def _do_match(
    flat_schema: list[tuple[NodeSchema, str, int]],
    ast_children: list,
    path: str,
    errors: list[ValidationError],
    ordered: bool,
    allow_extra: bool,
    expected_level: int,
) -> None:
    if ordered and not allow_extra:
        _match_strict_sequential(flat_schema, ast_children, path, errors, expected_level)
    elif ordered and allow_extra:
        _match_ordered_skip(flat_schema, ast_children, path, errors, expected_level)
    elif not ordered and not allow_extra:
        _match_any_order_strict(flat_schema, ast_children, path, errors, expected_level)
    else:
        _match_any_order_skip(flat_schema, ast_children, path, errors, expected_level)


def _get_section_display(ast_node: AstNode) -> str:
    if isinstance(ast_node, SectionNode):
        return f"section[{ast_node.title}]"
    return _ast_type_name(ast_node)


def _try_match_one(
    schema_node: NodeSchema,
    ast_node: AstNode,
    path: str,
    errors: list[ValidationError],
    expected_level: int,
) -> bool:
    """Check if ast_node matches schema_node type (and for sections, title). Validate if matches."""
    if schema_node.type == "group":
        # Named group: validate group's children against ast subtree's children
        # This would be a section or similar container. For simplicity we skip.
        return False

    if not _node_matches_schema(ast_node, schema_node):
        return False

    # For sections, also check title
    if schema_node.type == "section":
        assert isinstance(ast_node, SectionNode)
        title_spec = schema_node.title
        if isinstance(title_spec, str):
            if ast_node.title != title_spec:
                return False
        else:
            spec = _resolve_pattern(title_spec.pattern)
            if spec is not None and spec.regex is not None:
                if not re.fullmatch(spec.regex, ast_node.title):
                    return False

    label = _get_section_display(ast_node)
    node_path = f"{path} > {label}"
    _validate_node(schema_node, ast_node, path, errors, expected_level)
    return True


def _schema_label(schema_node: NodeSchema) -> str:
    name = getattr(schema_node, "name", None)
    t = schema_node.type
    if schema_node.type == "section":
        title = schema_node.title if isinstance(schema_node.title, str) else getattr(schema_node.title, "pattern", "")
        if isinstance(title, str):
            return f"section[{title}]"
        return f"section[{getattr(title, 'regex', '')}]"
    return f"{t}[{name or ''}]"


def _match_strict_sequential(
    flat_schema: list[tuple[NodeSchema, str, int]],
    ast_children: list,
    path: str,
    errors: list[ValidationError],
    expected_level: int,
) -> None:
    si = 0
    ai = 0
    while si < len(flat_schema) and ai < len(ast_children):
        sn, sp, slevel = flat_schema[si]

        if sn.type == "group" and sn.name:
            # Named group — consume from ast_children for group's children
            inner = _expand_groups(sn.children, f"{path} > group[{sn.name}]", errors, slevel)
            repeat = getattr(sn, "repeat", None)
            if repeat is not None:
                count, ai = _consume_repeat_group(inner, ast_children, ai, f"{path} > group[{sn.name}]", errors, slevel, repeat.min, repeat.max, ordered=sn.ordered, allow_extra=sn.allow_extra)
            else:
                _do_match(inner, ast_children[ai:ai + len(inner)], f"{path} > group[{sn.name}]", errors, sn.ordered, sn.allow_extra, slevel)
                ai += len(inner)
            si += 1
            continue

        repeat = getattr(sn, "repeat", None)
        if repeat is not None:
            count = 0
            while ai < len(ast_children):
                ast_node = ast_children[ai]
                probe_errors: list[ValidationError] = []
                matched = _try_match_one(sn, ast_node, path, probe_errors, slevel)
                if not matched:
                    break
                errors.extend(probe_errors)
                ai += 1
                count += 1
                if repeat.max is not None and count >= repeat.max:
                    break
            if count < repeat.min:
                errors.append(ValidationError(
                    path=path, error_type="repeat_underflow",
                    message=f"{_schema_label(sn)}: expected at least {repeat.min} occurrences, got {count}",
                    line=None,
                ))
            si += 1
            continue

        ast_node = ast_children[ai]
        probe_errors: list[ValidationError] = []
        matched = _try_match_one(sn, ast_node, path, probe_errors, slevel)
        if matched:
            errors.extend(probe_errors)
            ai += 1
        else:
            if getattr(sn, "required", True):
                line = getattr(ast_node, "line", None)
                errors.append(ValidationError(
                    path=f"{path} > {_schema_label(sn)}",
                    error_type="missing_element",
                    message="missing required element",
                    line=line,
                ))
            else:
                # optional, skip schema node
                pass
        si += 1

    # Remaining required schema nodes
    while si < len(flat_schema):
        sn, sp, slevel = flat_schema[si]
        repeat = getattr(sn, "repeat", None)
        if repeat is not None:
            if repeat.min > 0:
                errors.append(ValidationError(
                    path=path, error_type="repeat_underflow",
                    message=f"{_schema_label(sn)}: expected at least {repeat.min} occurrences, got 0",
                    line=None,
                ))
        elif getattr(sn, "required", True):
            errors.append(ValidationError(
                path=f"{path} > {_schema_label(sn)}",
                error_type="missing_element",
                message="missing required element",
                line=None,
            ))
        si += 1

    # Remaining extra AST nodes
    while ai < len(ast_children):
        ast_node = ast_children[ai]
        errors.append(ValidationError(
            path=f"{path} > {_get_section_display(ast_node)}",
            error_type="unexpected_element",
            message=f"unexpected {_ast_type_name(ast_node)}",
            line=getattr(ast_node, "line", None),
        ))
        ai += 1


def _consume_repeat_group(
    inner: list[tuple[NodeSchema, str, int]],
    ast_children: list,
    ai: int,
    path: str,
    errors: list[ValidationError],
    expected_level: int,
    min_: int,
    max_: int | None,
    ordered: bool,
    allow_extra: bool,
) -> tuple[int, int]:
    count = 0
    while ai < len(ast_children):
        group_size = len(inner)
        if ai + group_size > len(ast_children):
            break
        probe_errors: list[ValidationError] = []
        _do_match(inner, ast_children[ai:ai + group_size], path, probe_errors, ordered, allow_extra, expected_level)
        if any(e.error_type in ("missing_element", "wrong_type", "title_mismatch") for e in probe_errors):
            break
        errors.extend(probe_errors)
        ai += group_size
        count += 1
        if max_ is not None and count >= max_:
            break
    if count < min_:
        errors.append(ValidationError(path=path, error_type="repeat_underflow",
            message=f"expected at least {min_} occurrences, got {count}", line=None))
    return count, ai


def _match_ordered_skip(
    flat_schema: list[tuple[NodeSchema, str, int]],
    ast_children: list,
    path: str,
    errors: list[ValidationError],
    expected_level: int,
) -> None:
    si = 0
    ai = 0
    while si < len(flat_schema):
        sn, sp, slevel = flat_schema[si]
        repeat = getattr(sn, "repeat", None)
        found = False
        if repeat is not None:
            count = 0
            while ai < len(ast_children):
                probe: list[ValidationError] = []
                if _try_match_one(sn, ast_children[ai], path, probe, slevel):
                    errors.extend(probe)
                    ai += 1
                    count += 1
                    if repeat.max is not None and count >= repeat.max:
                        break
                else:
                    if count > 0:
                        break
                    ai += 1  # skip unknown
            if count < repeat.min:
                errors.append(ValidationError(path=path, error_type="repeat_underflow",
                    message=f"{_schema_label(sn)}: expected at least {repeat.min}, got {count}", line=None))
        else:
            while ai < len(ast_children):
                probe: list[ValidationError] = []
                if _try_match_one(sn, ast_children[ai], path, probe, slevel):
                    errors.extend(probe)
                    ai += 1
                    found = True
                    break
                ai += 1
            if not found and getattr(sn, "required", True):
                errors.append(ValidationError(
                    path=f"{path} > {_schema_label(sn)}",
                    error_type="missing_element",
                    message="missing required element",
                    line=None,
                ))
        si += 1


def _match_any_order_strict(
    flat_schema: list[tuple[NodeSchema, str, int]],
    ast_children: list,
    path: str,
    errors: list[ValidationError],
    expected_level: int,
) -> None:
    used_ast = [False] * len(ast_children)
    for sn, sp, slevel in flat_schema:
        repeat = getattr(sn, "repeat", None)
        if repeat is not None:
            count = 0
            for ai, ast_node in enumerate(ast_children):
                if used_ast[ai]:
                    continue
                probe: list[ValidationError] = []
                if _try_match_one(sn, ast_node, path, probe, slevel):
                    errors.extend(probe)
                    used_ast[ai] = True
                    count += 1
                    if repeat.max is not None and count >= repeat.max:
                        break
            if count < repeat.min:
                errors.append(ValidationError(path=path, error_type="repeat_underflow",
                    message=f"{_schema_label(sn)}: expected at least {repeat.min}, got {count}", line=None))
        else:
            found = False
            for ai, ast_node in enumerate(ast_children):
                if used_ast[ai]:
                    continue
                probe: list[ValidationError] = []
                if _try_match_one(sn, ast_node, path, probe, slevel):
                    errors.extend(probe)
                    used_ast[ai] = True
                    found = True
                    break
            if not found and getattr(sn, "required", True):
                errors.append(ValidationError(
                    path=f"{path} > {_schema_label(sn)}",
                    error_type="missing_element",
                    message="missing required element",
                    line=None,
                ))

    for ai, ast_node in enumerate(ast_children):
        if not used_ast[ai]:
            errors.append(ValidationError(
                path=f"{path} > {_get_section_display(ast_node)}",
                error_type="unexpected_element",
                message=f"unexpected {_ast_type_name(ast_node)}",
                line=getattr(ast_node, "line", None),
            ))


def _match_any_order_skip(
    flat_schema: list[tuple[NodeSchema, str, int]],
    ast_children: list,
    path: str,
    errors: list[ValidationError],
    expected_level: int,
) -> None:
    used_ast = [False] * len(ast_children)
    for sn, sp, slevel in flat_schema:
        repeat = getattr(sn, "repeat", None)
        if repeat is not None:
            count = 0
            for ai, ast_node in enumerate(ast_children):
                if used_ast[ai]:
                    continue
                probe: list[ValidationError] = []
                if _try_match_one(sn, ast_node, path, probe, slevel):
                    errors.extend(probe)
                    used_ast[ai] = True
                    count += 1
                    if repeat.max is not None and count >= repeat.max:
                        break
            if count < repeat.min:
                errors.append(ValidationError(path=path, error_type="repeat_underflow",
                    message=f"{_schema_label(sn)}: expected at least {repeat.min}, got {count}", line=None))
        else:
            found = False
            for ai, ast_node in enumerate(ast_children):
                if used_ast[ai]:
                    continue
                probe: list[ValidationError] = []
                if _try_match_one(sn, ast_node, path, probe, slevel):
                    errors.extend(probe)
                    used_ast[ai] = True
                    found = True
                    break
            if not found and getattr(sn, "required", True):
                errors.append(ValidationError(
                    path=f"{path} > {_schema_label(sn)}",
                    error_type="missing_element",
                    message="missing required element",
                    line=None,
                ))
