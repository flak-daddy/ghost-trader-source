"""The user manual: load MANUAL.md and render it to HTML (for the Help tab and the release PDF) or plain text.

A small Markdown renderer covering what the manual uses: headings, paragraphs, bullet and numbered lists,
pipe tables, block quotes, rules, fenced code, and inline bold / italic / code / links. Standard library only.
"""
from __future__ import annotations

import html
import re

from . import config

# The packaged copy is a symlink to the repo's MANUAL.md; wheels and sdists store the real file.
MANUAL_PATH = config.STATIC_DIR / "MANUAL.md"


def load() -> str:
    return MANUAL_PATH.read_text(encoding="utf-8")


def slug(text: str) -> str:
    t = re.sub(r"<[^>]+>", "", text).lower()
    t = re.sub(r"[^\w\s-]", "", t)
    return re.sub(r"\s+", "-", t.strip())


_CODE = re.compile(r"`([^`]+)`")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITAL = re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])")


def inline(text: str) -> str:
    """Escape, then apply inline markup. Code spans are protected from the other rules."""
    codes: list[str] = []

    def keep(m):
        codes.append(f"<code>{html.escape(m.group(1))}</code>")
        return f"\x00{len(codes) - 1}\x00"

    t = _CODE.sub(keep, text)
    t = html.escape(t, quote=False)

    def link(m):
        href = html.unescape(m.group(2))
        ext = href.startswith(("http://", "https://"))
        attrs = f' href="{html.escape(href)}"' + (' class="ext"' if ext else "")
        return f"<a{attrs}>{m.group(1)}</a>"

    t = _LINK.sub(link, t)
    t = _BOLD.sub(r"<strong>\1</strong>", t)
    t = _ITAL.sub(r"<em>\1</em>", t)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], t)


def _cells(row: str) -> list[str]:
    return [c.strip() for c in row.strip().strip("|").split("|")]


def render(md: str) -> tuple[str, list[dict]]:
    """Return (html, toc). toc lists level-2 and level-3 headings as {level, id, text}."""
    lines = md.splitlines()
    out: list[str] = []
    toc: list[dict] = []
    seen: dict[str, int] = {}
    i, n = 0, len(lines)

    def para_end(j):
        s = lines[j]
        return (not s.strip() or s.startswith(("#", ">", "|", "```", "- ")) or s.strip() == "---"
                or re.match(r"\d+\.\s", s))

    while i < n:
        s = lines[i]
        st = s.strip()
        if not st:
            i += 1
            continue
        if st.startswith("```"):
            j = i + 1
            buf = []
            while j < n and not lines[j].strip().startswith("```"):
                buf.append(lines[j])
                j += 1
            out.append(f"<pre><code>{html.escape(chr(10).join(buf))}</code></pre>")
            i = j + 1
            continue
        m = re.match(r"(#{1,4})\s+(.*)", s)
        if m:
            lvl, txt = len(m.group(1)), m.group(2).strip()
            hid = slug(txt)
            if hid in seen:
                seen[hid] += 1
                hid = f"{hid}-{seen[hid]}"
            else:
                seen[hid] = 0
            body = inline(txt)
            out.append(f'<h{lvl} id="{hid}">{body}</h{lvl}>')
            if lvl in (2, 3):
                toc.append({"level": lvl, "id": hid, "text": re.sub(r"<[^>]+>", "", body)})
            i += 1
            continue
        if st == "---":
            out.append("<hr>")
            i += 1
            continue
        if st.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip()[1:].strip())
                i += 1
            paras = "\n".join(buf).split("\n\n")
            out.append("<blockquote>" + "".join(f"<p>{inline(' '.join(p.split(chr(10))))}</p>" for p in paras if p.strip())
                       + "</blockquote>")
            continue
        if st.startswith("|") and i + 1 < n and re.match(r"^\|?\s*:?-{2,}", lines[i + 1].strip()):
            head = _cells(lines[i])
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(_cells(lines[i]))
                i += 1
            th = "".join(f"<th>{inline(c)}</th>" for c in head)
            tb = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows)
            out.append(f'<div class="tbl"><table><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table></div>')
            continue
        lm = re.match(r"(\s*)(- |\d+\.\s)", s)
        if lm:
            ordered = lm.group(2)[0].isdigit()
            base = len(lm.group(1))
            items: list[str] = []
            while i < n:
                cur = lines[i]
                im = re.match(r"(\s*)(- |\d+\.\s)(.*)", cur)
                if im and len(im.group(1)) <= base and (im.group(2)[0].isdigit()) == ordered:
                    items.append(im.group(3).strip())
                    i += 1
                elif cur.startswith(("  ", "\t")) and cur.strip() and items:
                    sub = re.match(r"\s+(- |\d+\.\s)(.*)", cur)
                    if sub:  # one nested level, kept as a sub-list inside the item
                        items[-1] += "\x01" + sub.group(2).strip()
                    else:
                        items[-1] += " " + cur.strip()
                    i += 1
                else:
                    break
            tag = "ol" if ordered else "ul"

            def li(t):
                parts = t.split("\x01")
                sub = "".join(f"<li>{inline(p)}</li>" for p in parts[1:])
                return f"<li>{inline(parts[0])}{f'<ul>{sub}</ul>' if sub else ''}</li>"

            out.append(f"<{tag}>" + "".join(li(t) for t in items) + f"</{tag}>")
            continue
        buf = [st]
        i += 1
        while i < n and not para_end(i):
            buf.append(lines[i].strip())
            i += 1
        out.append(f"<p>{inline(' '.join(buf))}</p>")
    return "\n".join(out), toc


def to_text(md: str) -> str:
    """Plain-text version: links become 'text (url)' (internal links just 'text'), emphasis markers dropped."""
    def link(m):
        return m.group(1) if m.group(2).startswith("#") else f"{m.group(1)} ({m.group(2)})"

    t = _LINK.sub(link, md)
    t = _BOLD.sub(r"\1", t)
    t = _ITAL.sub(r"\1", t)
    return t.replace("`", "")


def page(title: str, body_html: str, toc: list[dict], css: str = "") -> str:
    """A standalone HTML page (used for the PDF)."""
    return (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>{html.escape(title)}</title>'
            f"<style>{css}</style></head><body><article class=\"manual\">{body_html}</article></body></html>")
