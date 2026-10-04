from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

_RESET = "\x1b[0m"
_BOLD = "\x1b[1m"
_DIM = "\x1b[2m"
_RED = "\x1b[31m"
_GREEN = "\x1b[32m"
_YELLOW = "\x1b[33m"
_CYAN = "\x1b[36m"

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

_UNICODE_SYMBOLS = {"passed": "✔", "failed": "✘", "pending": "•"}
_ASCII_SYMBOLS = {"passed": "OK", "failed": "KO", "pending": ".."}


def supports_unicode(encoding: str | None) -> bool:
    """Solo se usa Unicode si la codificacion del flujo es UTF-*; ante la duda, ASCII."""
    return encoding is not None and encoding.lower().startswith("utf")


def visible_len(text: str) -> int:
    """Largo visible: ignora las secuencias de color ANSI."""
    return len(_ANSI_RE.sub("", text))


@dataclass(frozen=True, slots=True)
class Ui:
    """Primitivas visuales: color, simbolos, cajas y barra de progreso."""

    unicode: bool
    color: bool

    def _paint(self, text: str, code: str) -> str:
        return f"{code}{text}{_RESET}" if self.color else text

    def bold(self, text: str) -> str:
        return self._paint(text, _BOLD)

    def dim(self, text: str) -> str:
        return self._paint(text, _DIM)

    def red(self, text: str) -> str:
        return self._paint(text, _RED)

    def green(self, text: str) -> str:
        return self._paint(text, _GREEN)

    def yellow(self, text: str) -> str:
        return self._paint(text, _YELLOW)

    def cyan(self, text: str) -> str:
        return self._paint(text, _CYAN)

    def symbol(self, kind: str) -> str:
        table = _UNICODE_SYMBOLS if self.unicode else _ASCII_SYMBOLS
        return table[kind]

    def painted_symbol(self, kind: str) -> str:
        symbol = self.symbol(kind)
        if kind == "passed":
            return self.green(symbol)
        if kind == "failed":
            return self.red(symbol)
        return self.yellow(symbol)

    def box(self, lines: Sequence[str], width: int, title: str = "") -> str:
        """Dibuja una caja de ancho total `width`; las lineas pueden traer ANSI."""
        if self.unicode:
            tl, tr, bl, br, h, v = "╭", "╮", "╰", "╯", "─", "│"
        else:
            tl = tr = bl = br = "+"
            h, v = "-", "|"
        inner = width - 2
        head = f" {title} " if title else ""
        top = tl + head + h * (inner - len(head)) + tr
        body = [
            f"{v} {line}{' ' * (inner - 2 - visible_len(line))} {v}" for line in lines
        ]
        return "\n".join([top, *body, bl + h * inner + br])

    def progress_bar(self, done: int, total: int, width: int = 20) -> str:
        filled = width * done // total if total > 0 else 0
        full, empty = ("█", "░") if self.unicode else ("#", "-")
        return "[" + full * filled + empty * (width - filled) + "]"
