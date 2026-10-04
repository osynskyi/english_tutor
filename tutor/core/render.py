"""Render grammar theory blocks for the website (HTML) and Telegram (its HTML subset).

Theory is stored as a list of blocks:
    {"type": "h", "text": ...}       heading
    {"type": "p", "text": ...}       paragraph
    {"type": "rule", "text": ...}    highlighted formula / rule
    {"type": "note", "text": ...}    tip
    {"type": "list", "items": [...]}
    {"type": "table", "rows": [[...], ...]}   first row is the header
Inline markup: **bold**, __italic__, `code`.
"""

from __future__ import annotations

import html
import re
from typing import Any

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"__(.+?)__")
_CODE = re.compile(r"`(.+?)`")


def inline(text: str) -> str:
    """Escape HTML and convert the inline markup. Output is valid for web and Telegram."""
    out = html.escape(text, quote=False)
    out = _BOLD.sub(r"<b>\1</b>", out)
    out = _ITALIC.sub(r"<i>\1</i>", out)
    out = _CODE.sub(r"<code>\1</code>", out)
    return out


def plain(text: str) -> str:
    """Strip the inline markup."""
    return _CODE.sub(r"\1", _ITALIC.sub(r"\1", _BOLD.sub(r"\1", text)))


def theory_to_html(blocks: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for block in blocks:
        kind = block["type"]
        if kind == "h":
            parts.append(f"<h3>{inline(block['text'])}</h3>")
        elif kind == "p":
            parts.append(f"<p>{inline(block['text'])}</p>")
        elif kind == "rule":
            parts.append(f'<div class="rule">{inline(block["text"])}</div>')
        elif kind == "note":
            parts.append(f'<div class="note">💡 {inline(block["text"])}</div>')
        elif kind == "list":
            items = "".join(f"<li>{inline(i)}</li>" for i in block["items"])
            parts.append(f"<ul>{items}</ul>")
        elif kind == "table":
            head, *rows = block["rows"]
            thead = "".join(f"<th>{inline(c)}</th>" for c in head)
            tbody = "".join(
                "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>" for row in rows
            )
            parts.append(f'<div class="table-wrap"><table><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table></div>')
        else:
            raise ValueError(f"Unknown theory block type: {kind}")
    return "\n".join(parts)


def theory_to_telegram(blocks: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for block in blocks:
        kind = block["type"]
        if kind == "h":
            parts.append(f"<b>{inline(block['text'])}</b>")
        elif kind == "p":
            parts.append(inline(block["text"]))
        elif kind == "rule":
            parts.append(f"<blockquote>{inline(block['text'])}</blockquote>")
        elif kind == "note":
            parts.append(f"💡 <i>{inline(block['text'])}</i>")
        elif kind == "list":
            parts.append("\n".join(f"• {inline(i)}" for i in block["items"]))
        elif kind == "table":
            head, *rows = block["rows"]
            lines = [" | ".join(f"<b>{inline(c)}</b>" for c in head)]
            lines += [" — ".join(inline(c) for c in row) for row in rows]
            parts.append("\n".join(lines))
        else:
            raise ValueError(f"Unknown theory block type: {kind}")
    return "\n\n".join(parts)


def split_message(text: str, limit: int = 4000) -> list[str]:
    """Split a long Telegram message on paragraph boundaries."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for para in text.split("\n\n"):
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        while len(para) > limit:
            chunks.append(para[:limit])
            para = para[limit:]
        current = para
    if current:
        chunks.append(current)
    return chunks
