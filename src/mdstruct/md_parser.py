from __future__ import annotations

import re
from dataclasses import dataclass, field

import mistletoe
import mistletoe.block_token as bt
import mistletoe.span_token as st
import yaml


@dataclass
class TextNode:
    text: str
    line: int


@dataclass
class ListItemNode:
    text: str
    children: list[ListNode]
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
    text: str
    line: int


@dataclass
class ThematicBreakNode:
    raw: str
    line: int


ContentNode = TextNode | ListNode | TableNode | CodeNode | BlockquoteNode | ThematicBreakNode


@dataclass
class SectionNode:
    level: int
    title: str
    line: int
    children: list[SectionNode | ContentNode] = field(default_factory=list)


@dataclass
class DocumentNode:
    frontmatter: dict | None
    children: list[SectionNode | ContentNode] = field(default_factory=list)


_FRONTMATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
_THEMATIC_RAW_RE = re.compile(r"^[-*_]{3,}\s*$")


def _render_spans(token) -> str:
    """Recursively extract plain text from a span token."""
    if hasattr(token, "children") and token.children:
        return "".join(_render_spans(c) for c in token.children)
    if hasattr(token, "content"):
        return token.content
    return ""


def _token_line(token) -> int:
    if hasattr(token, "line_number") and token.line_number:
        return token.line_number
    return 0


def _parse_list_items(list_token, base_line: int) -> list[ListItemNode]:
    items = []
    for item in list_token.children:
        line = _token_line(item) or base_line
        text_parts = []
        nested: list[ListNode] = []
        for child in (item.children or []):
            if isinstance(child, bt.List):
                nested.append(_parse_list_node(child))
            elif hasattr(child, "children"):
                text_parts.append("".join(_render_spans(s) for s in (child.children or [])))
            else:
                text_parts.append(_render_spans(child))
        items.append(ListItemNode(
            text=" ".join(t for t in text_parts if t).strip(),
            children=nested,
            line=line,
        ))
    return items


def _parse_list_node(token) -> ListNode:
    ordered = getattr(token, "start", None) is not None
    line = _token_line(token)
    items = _parse_list_items(token, line)
    return ListNode(ordered=ordered, items=items, line=line)


def _parse_table_node(token) -> TableNode:
    line = _token_line(token)
    headers = []
    if token.header:
        for cell in token.header.children:
            headers.append("".join(_render_spans(s) for s in (cell.children or [])).strip())
    rows = []
    for row in (token.children or []):
        cells = []
        for cell in row.children:
            cells.append("".join(_render_spans(s) for s in (cell.children or [])).strip())
        rows.append(cells)
    return TableNode(headers=headers, rows=rows, line=line)


def _parse_content(token) -> ContentNode | None:
    if isinstance(token, bt.Paragraph):
        text = "".join(_render_spans(s) for s in (token.children or [])).strip()
        return TextNode(text=text, line=_token_line(token))

    if isinstance(token, bt.List):
        return _parse_list_node(token)

    if isinstance(token, bt.Table):
        return _parse_table_node(token)

    if isinstance(token, (bt.BlockCode, bt.CodeFence)):
        lang = (getattr(token, "language", None) or "").strip() or None
        content = token.children[0].content if token.children else ""
        return CodeNode(language=lang, content=content, line=_token_line(token))

    if isinstance(token, bt.Quote):
        parts = []
        for child in (token.children or []):
            if isinstance(child, bt.Paragraph):
                parts.append("".join(_render_spans(s) for s in (child.children or [])).strip())
        return BlockquoteNode(text=" ".join(parts), line=_token_line(token))

    if isinstance(token, bt.ThematicBreak):
        raw = getattr(token, "raw", "---") or "---"
        raw = raw.strip()
        if not _THEMATIC_RAW_RE.match(raw):
            raw = "---"
        return ThematicBreakNode(raw=raw, line=_token_line(token))

    return None


def _build_section_tree(
    tokens: list,
    expected_level: int,
    pos: int,
) -> tuple[list[SectionNode | ContentNode], int]:
    result: list[SectionNode | ContentNode] = []
    while pos < len(tokens):
        token = tokens[pos]
        if isinstance(token, bt.Heading):
            lvl = token.level
            if lvl < expected_level:
                break
            if lvl == expected_level:
                title = "".join(_render_spans(s) for s in (token.children or [])).strip()
                sec = SectionNode(level=lvl, title=title, line=_token_line(token))
                pos += 1
                sec.children, pos = _build_section_tree(tokens, expected_level + 1, pos)
                result.append(sec)
            else:
                # deeper heading without a parent at this level → treat as content-less section
                title = "".join(_render_spans(s) for s in (token.children or [])).strip()
                sec = SectionNode(level=lvl, title=title, line=_token_line(token))
                pos += 1
                sec.children, pos = _build_section_tree(tokens, lvl + 1, pos)
                result.append(sec)
        else:
            node = _parse_content(token)
            if node is not None:
                result.append(node)
            pos += 1
    return result, pos


def parse_markdown(text: str) -> DocumentNode:
    frontmatter: dict | None = None
    m = _FRONTMATTER_RE.match(text)
    if m:
        frontmatter = yaml.safe_load(m.group(1)) or {}
        text = text[m.end():]

    doc = mistletoe.Document(text)
    tokens = list(doc.children or [])

    children, _ = _build_section_tree(tokens, expected_level=1, pos=0)
    return DocumentNode(frontmatter=frontmatter, children=children)
