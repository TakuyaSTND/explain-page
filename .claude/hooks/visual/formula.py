from __future__ import annotations

import html

# 単純記号（引数を取らない）＝ \コマンド名 -> 出力する1文字
_SIMPLE_SYMBOLS = {
    "times": "×",
    "cdot": "⋅",
    "div": "÷",
    "pm": "±",
    "le": "≤",
    "ge": "≥",
    "ne": "≠",
    "approx": "≈",
    "infty": "∞",
    "to": "→",
    "leftarrow": "←",
    "rightarrow": "→",
}

# 大型演算子＝上下（sub/sup）が付くと munder/mover/munderover になる
_BIG_OPERATORS = {
    "sum": "∑",
    "prod": "∏",
    "int": "∫",
}

_GREEK_LOWER = (
    ("alpha", "α"),
    ("beta", "β"),
    ("gamma", "γ"),
    ("delta", "δ"),
    ("epsilon", "ε"),
    ("zeta", "ζ"),
    ("eta", "η"),
    ("theta", "θ"),
    ("iota", "ι"),
    ("kappa", "κ"),
    ("lambda", "λ"),
    ("mu", "μ"),
    ("nu", "ν"),
    ("xi", "ξ"),
    ("omicron", "ο"),
    ("pi", "π"),
    ("rho", "ρ"),
    ("sigma", "σ"),
    ("tau", "τ"),
    ("upsilon", "υ"),
    ("phi", "φ"),
    ("chi", "χ"),
    ("psi", "ψ"),
    ("omega", "ω"),
)

_GREEK_UPPER = (
    ("Alpha", "Α"),
    ("Beta", "Β"),
    ("Gamma", "Γ"),
    ("Delta", "Δ"),
    ("Epsilon", "Ε"),
    ("Zeta", "Ζ"),
    ("Eta", "Η"),
    ("Theta", "Θ"),
    ("Iota", "Ι"),
    ("Kappa", "Κ"),
    ("Lambda", "Λ"),
    ("Mu", "Μ"),
    ("Nu", "Ν"),
    ("Xi", "Ξ"),
    ("Omicron", "Ο"),
    ("Pi", "Π"),
    ("Rho", "Ρ"),
    ("Sigma", "Σ"),
    ("Tau", "Τ"),
    ("Upsilon", "Υ"),
    ("Phi", "Φ"),
    ("Chi", "Χ"),
    ("Psi", "Ψ"),
    ("Omega", "Ω"),
)

_GREEK = dict(_GREEK_LOWER + _GREEK_UPPER)

_ASCII_LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
_ASCII_DIGITS = "0123456789"
_LITERAL_CHARS = "+-=<>()[],."
_LEFT_RIGHT_DELIMS = "()[]"


class _ParseError(Exception):
    """内部用＝対応外の記法・閉じ忘れを示す（外へは None として伝える）。"""


def _esc(text: str) -> str:
    return html.escape(text, quote=True)


class _Parser:
    def __init__(self, source: str) -> None:
        self.s = source
        self.i = 0
        self.n = len(source)

    def _peek(self) -> str:
        return self.s[self.i] if self.i < self.n else ""

    def _skip_ws(self) -> None:
        while self.i < self.n and self.s[self.i].isspace():
            self.i += 1

    def _error(self) -> None:
        raise _ParseError()

    def _expect_char(self, ch: str) -> None:
        self._skip_ws()
        if self.i >= self.n or self.s[self.i] != ch:
            self._error()
        self.i += 1

    def parse_top_level(self) -> str:
        body = self.parse_expression(in_group=False)
        self._skip_ws()
        if self.i != self.n:
            self._error()
        return body

    def parse_expression(self, in_group: bool) -> str:
        items: list[str] = []
        while True:
            self._skip_ws()
            if self.i >= self.n:
                break
            if in_group and self.s[self.i] == "}":
                break
            items.append(self.parse_item_with_modifiers())
        if not items:
            self._error()
        if len(items) == 1:
            return items[0]
        return "<mrow>" + "".join(items) + "</mrow>"

    def parse_group(self) -> str:
        self._expect_char("{")
        content = self.parse_expression(in_group=True)
        self._expect_char("}")
        return content

    def parse_item_with_modifiers(self) -> str:
        base, is_big_op = self.parse_atom()
        sup: str | None = None
        sub: str | None = None
        while True:
            self._skip_ws()
            c = self._peek()
            if c == "^":
                if sup is not None:
                    self._error()
                self.i += 1
                sup = self.parse_sup_sub_arg()
            elif c == "_":
                if sub is not None:
                    self._error()
                self.i += 1
                sub = self.parse_sup_sub_arg()
            else:
                break
        if is_big_op:
            if sub is not None and sup is not None:
                return f"<munderover>{base}{sub}{sup}</munderover>"
            if sub is not None:
                return f"<munder>{base}{sub}</munder>"
            if sup is not None:
                return f"<mover>{base}{sup}</mover>"
            return base
        if sub is not None and sup is not None:
            return f"<msubsup>{base}{sub}{sup}</msubsup>"
        if sub is not None:
            return f"<msub>{base}{sub}</msub>"
        if sup is not None:
            return f"<msup>{base}{sup}</msup>"
        return base

    def parse_sup_sub_arg(self) -> str:
        self._skip_ws()
        if self._peek() == "{":
            return self.parse_group()
        node, _ = self.parse_atom()
        return node

    def parse_atom(self) -> tuple[str, bool]:
        self._skip_ws()
        if self.i >= self.n:
            self._error()
        c = self.s[self.i]
        if c == "\\":
            return self.parse_command()
        if c == "{":
            return self.parse_group(), False
        if c in _ASCII_DIGITS:
            return self.parse_number(), False
        if c in _ASCII_LETTERS:
            self.i += 1
            return f"<mi>{_esc(c)}</mi>", False
        if c in _LITERAL_CHARS:
            self.i += 1
            return f"<mo>{_esc(c)}</mo>", False
        self._error()
        raise AssertionError("unreachable")

    def parse_number(self) -> str:
        start = self.i
        while self.i < self.n:
            c = self.s[self.i]
            if c in _ASCII_DIGITS:
                self.i += 1
                continue
            if c in ".," and self.i + 1 < self.n and self.s[self.i + 1] in _ASCII_DIGITS:
                self.i += 1
                continue
            break
        text = self.s[start:self.i]
        return f"<mn>{_esc(text)}</mn>"

    def parse_command(self) -> tuple[str, bool]:
        # self.s[self.i] == "\\"
        self.i += 1
        if self.i >= self.n:
            self._error()
        if self.s[self.i] == "%":
            self.i += 1
            return "<mo>%</mo>", False
        if self.s[self.i] not in _ASCII_LETTERS:
            self._error()
        start = self.i
        while self.i < self.n and self.s[self.i] in _ASCII_LETTERS:
            self.i += 1
        name = self.s[start:self.i]
        return self._dispatch_command(name)

    def _dispatch_command(self, name: str) -> tuple[str, bool]:
        if name in _SIMPLE_SYMBOLS:
            return f"<mo>{_SIMPLE_SYMBOLS[name]}</mo>", False
        if name in _GREEK:
            return f"<mi>{_GREEK[name]}</mi>", False
        if name in _BIG_OPERATORS:
            return f"<mo>{_BIG_OPERATORS[name]}</mo>", True
        if name == "quad":
            return '<mspace width="1em"/>', False
        if name == "frac":
            a = self.parse_group()
            b = self.parse_group()
            return f"<mfrac>{a}{b}</mfrac>", False
        if name == "sqrt":
            a = self.parse_group()
            return f"<msqrt>{a}</msqrt>", False
        if name == "text":
            return self.parse_text_group(), False
        if name in ("left", "right"):
            return self.parse_delimiter(), False
        self._error()
        raise AssertionError("unreachable")

    def parse_delimiter(self) -> str:
        self._skip_ws()
        if self.i >= self.n:
            self._error()
        c = self.s[self.i]
        if c in _LEFT_RIGHT_DELIMS:
            self.i += 1
            return f"<mo>{_esc(c)}</mo>"
        self._error()
        raise AssertionError("unreachable")

    def parse_text_group(self) -> str:
        self._skip_ws()
        if self.i >= self.n or self.s[self.i] != "{":
            self._error()
        self.i += 1
        depth = 1
        start = self.i
        while self.i < self.n:
            ch = self.s[self.i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            self.i += 1
        if depth != 0:
            self._error()
        content = self.s[start:self.i]
        self.i += 1  # 閉じの "}" を読み飛ばす
        return f"<mtext>{_esc(content)}</mtext>"


def tex_to_mathml(tex: str) -> str | None:
    """LaTeXの部分集合をMathMLへ変換する。対応外・閉じ忘れは None。

    出力に生の入力文字を埋めることはしない＝要素は自分で組み、
    テキスト由来の内容はすべて html.escape 済み。
    """
    if not isinstance(tex, str):
        return None
    try:
        parser = _Parser(tex)
        body = parser.parse_top_level()
    except _ParseError:
        return None
    except Exception:
        # 未知の失敗はここで打ち切り、対応外として None を返す（呼び出し側で原文表示）。
        return None
    return (
        '<math display="block">'
        + body
        + "</math>"
    )
