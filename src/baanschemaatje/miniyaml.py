"""Minimale YAML-lezer voor clubprofielen.

Gebruikt PyYAML als dat geïnstalleerd is. Anders valt hij terug op een kleine
parser voor de subset die clubprofielen nodig hebben, zodat Baanschemaatje geen
extra dependency aan het bestaande project toevoegt:

- geneste mappings via inspringen (spaties)
- blok-lijsten met scalaire items (``- 1``)
- inline lijsten, ook genest (``[1, 2]``, ``[[1, 2], [3, 4]]``)
- scalars: int, float, true/false, null/~, "strings" en 'strings'
- ``#``-commentaar
"""

from __future__ import annotations

from typing import Any


class MiniYamlError(ValueError):
    pass


def loads(text: str) -> Any:
    try:  # pragma: no cover - afhankelijk van de omgeving
        import yaml  # type: ignore

        return yaml.safe_load(text)
    except ImportError:
        return _parse(text)


def _strip_comment(line: str) -> str:
    out, quote = [], None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        out.append(ch)
    return "".join(out).rstrip()


def _scalar(tok: str) -> Any:
    t = tok.strip()
    if t == "":
        return None
    if t[0] == "[":
        return _inline_list(t)
    if t[0] in "\"'" and t[-1] == t[0] and len(t) >= 2:
        return t[1:-1]
    low = t.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if low in ("null", "~"):
        return None
    try:
        return int(t)
    except ValueError:
        pass
    try:
        return float(t)
    except ValueError:
        return t


def _inline_list(t: str) -> list:
    if not (t.startswith("[") and t.endswith("]")):
        raise MiniYamlError(f"ongeldige inline lijst: {t!r}")
    inner = t[1:-1].strip()
    if not inner:
        return []
    items, depth, cur, quote = [], 0, [], None
    for ch in inner:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        elif ch == "," and depth == 0:
            items.append("".join(cur))
            cur = []
            continue
        cur.append(ch)
    items.append("".join(cur))
    return [_scalar(i) for i in items]


def _parse(text: str) -> Any:
    lines = []
    for raw in text.splitlines():
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise MiniYamlError("tabs voor inspringen zijn niet toegestaan")
        line = _strip_comment(raw)
        if line.strip():
            lines.append((len(line) - len(line.lstrip(" ")), line.strip()))
    if not lines:
        return None
    value, idx = _block(lines, 0, lines[0][0])
    if idx != len(lines):
        raise MiniYamlError(f"onverwachte inspringing bij: {lines[idx][1]!r}")
    return value


def _block(lines, idx, indent):
    if lines[idx][1].startswith("- ") or lines[idx][1] == "-":
        out = []
        while idx < len(lines) and lines[idx][0] == indent and lines[idx][1].startswith("-"):
            item = lines[idx][1][1:].strip()
            if not item:
                raise MiniYamlError("geneste blokken in lijsten worden niet ondersteund")
            out.append(_scalar(item))
            idx += 1
        return out, idx
    out: dict = {}
    while idx < len(lines) and lines[idx][0] == indent:
        content = lines[idx][1]
        if ":" not in content:
            raise MiniYamlError(f"verwacht 'sleutel: waarde', kreeg {content!r}")
        key, _, rest = content.partition(":")
        key = key.strip().strip("\"'")
        rest = rest.strip()
        idx += 1
        if rest:
            out[key] = _scalar(rest)
        elif idx < len(lines) and lines[idx][0] > indent:
            out[key], idx = _block(lines, idx, lines[idx][0])
        else:
            out[key] = None
    if idx < len(lines) and lines[idx][0] > indent:
        raise MiniYamlError(f"onverwachte inspringing bij: {lines[idx][1]!r}")
    return out, idx
