from __future__ import annotations

import re

from markupsafe import Markup, escape

try:
    import bleach
    import markdown
except Exception:
    bleach = None
    markdown = None


def _apply_inline(markup_text: str) -> str:
    markup_text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", markup_text)
    markup_text = re.sub(r"`([^`]+)`", r"<code>\1</code>", markup_text)
    markup_text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", markup_text)
    markup_text = re.sub(r"__([^_]+)__", r"<strong>\1</strong>", markup_text)
    markup_text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", markup_text)
    markup_text = re.sub(r"_([^_]+)_", r"<em>\1</em>", markup_text)
    return markup_text


def _basic_markdown_to_html(raw_text: str) -> str:
    if not raw_text:
        return ""
    escaped_text = str(escape(raw_text))
    escaped_text = escaped_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = escaped_text.split("\n")
    html_parts = []
    paragraph = []
    in_ul = False
    in_ol = False
    in_code = False
    code_lines = []

    def flush_paragraph():
        nonlocal paragraph
        if paragraph:
            html_parts.append("<p>" + " ".join(paragraph) + "</p>")
            paragraph = []

    def close_lists():
        nonlocal in_ul, in_ol
        if in_ul:
            html_parts.append("</ul>")
            in_ul = False
        if in_ol:
            html_parts.append("</ol>")
            in_ol = False

    for line in lines:
        if line.strip().startswith("```"):
            if in_code:
                html_parts.append("<pre><code>" + "\n".join(code_lines) + "</code></pre>")
                code_lines = []
                in_code = False
            else:
                flush_paragraph()
                close_lists()
                in_code = True
            continue

        if in_code:
            code_lines.append(line)
            continue

        if not line.strip():
            flush_paragraph()
            close_lists()
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            flush_paragraph()
            close_lists()
            level = len(heading_match.group(1))
            content = _apply_inline(heading_match.group(2).strip())
            html_parts.append(f"<h{level}>{content}</h{level}>")
            continue

        ul_match = re.match(r"^\s*[-*+]\s+(.+)$", line)
        if ul_match:
            flush_paragraph()
            if in_ol:
                html_parts.append("</ol>")
                in_ol = False
            if not in_ul:
                html_parts.append("<ul>")
                in_ul = True
            html_parts.append("<li>" + _apply_inline(ul_match.group(1).strip()) + "</li>")
            continue

        ol_match = re.match(r"^\s*\d+[.)]\s+(.+)$", line)
        if ol_match:
            flush_paragraph()
            if in_ul:
                html_parts.append("</ul>")
                in_ul = False
            if not in_ol:
                html_parts.append("<ol>")
                in_ol = True
            html_parts.append("<li>" + _apply_inline(ol_match.group(1).strip()) + "</li>")
            continue

        close_lists()
        paragraph.append(_apply_inline(line.strip()))

    if in_code:
        html_parts.append("<pre><code>" + "\n".join(code_lines) + "</code></pre>")
    flush_paragraph()
    close_lists()

    return "".join(html_parts)


def render_legal_markdown(text: str) -> Markup:
    if not markdown or not bleach:
        return Markup(_basic_markdown_to_html(text or ""))

    html = markdown.markdown(
        text or "",
        extensions=["extra", "sane_lists", "tables"],
        output_format="html",
    )

    allowed_tags = [tag for tag in bleach.sanitizer.ALLOWED_TAGS if tag != "a"] + [
        "p",
        "pre",
        "span",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "table",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
        "code",
        "hr",
        "br",
        "ul",
        "ol",
        "li",
        "blockquote",
    ]
    allowed_attrs = {
        "code": ["class"],
    }

    cleaned = bleach.clean(
        html,
        tags=allowed_tags,
        attributes=allowed_attrs,
        strip=True,
    )
    return Markup(cleaned)
