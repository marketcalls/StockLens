"""Screener query parser.

Turns text like

    Market Capitalization > 500 AND Return on equity > 15

into an abstract syntax tree. The compiler turns that tree into SQL.

Column names are multi-word and unquoted ("Return on equity"), so the tokeniser
cannot split on whitespace. It instead reads a run of word characters and then
asks the catalog for the longest prefix that resolves to a real column. Anything
that does not resolve is a parse error, never a SQL identifier - see compiler.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.screener.catalog import Column, resolve

TokenKind = Literal[
    "column", "number", "string", "op", "and", "or", "not", "in", "lparen", "rparen", "comma", "end"
]

COMPARISONS = (">=", "<=", "!=", "<>", ">", "<", "=", "==")
ARITHMETIC = ("+", "-", "*", "/")

_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_%/&.\- ]*")
_STRING = re.compile(r'"([^"]*)"|\'([^\']*)\'')

KEYWORDS = {"and", "or", "not", "in"}

# How many words a column name may span. "Average return on capital employed
# 3Years" is six; the ceiling stops a runaway scan on malformed input.
MAX_COLUMN_WORDS = 8


class QueryError(ValueError):
    """The query could not be parsed. The message is shown to the user."""

    def __init__(self, message: str, position: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.position = position


@dataclass(frozen=True)
class Token:
    kind: TokenKind
    value: object
    position: int


@dataclass(frozen=True)
class NumberNode:
    value: float


@dataclass(frozen=True)
class ColumnNode:
    column: Column


@dataclass(frozen=True)
class BinaryNode:
    op: str
    left: Node
    right: Node


@dataclass(frozen=True)
class CompareNode:
    op: str
    left: Node
    right: Node


@dataclass(frozen=True)
class LogicalNode:
    op: Literal["AND", "OR"]
    left: Node
    right: Node


@dataclass(frozen=True)
class NotNode:
    operand: Node


@dataclass(frozen=True)
class InNode:
    column: Column
    values: tuple[str, ...]
    negated: bool = False


Node = NumberNode | ColumnNode | BinaryNode | CompareNode | LogicalNode | NotNode | InNode


def tokenise(text: str) -> list[Token]:
    tokens: list[Token] = []
    i = 0
    n = len(text)

    while i < n:
        char = text[i]

        if char.isspace():
            i += 1
            continue

        if char == "(":
            tokens.append(Token("lparen", "(", i))
            i += 1
            continue
        if char == ")":
            tokens.append(Token("rparen", ")", i))
            i += 1
            continue
        if char == ",":
            tokens.append(Token("comma", ",", i))
            i += 1
            continue

        string_match = _STRING.match(text, i)
        if string_match:
            value = string_match.group(1)
            if value is None:
                value = string_match.group(2)
            tokens.append(Token("string", value, i))
            i = string_match.end()
            continue

        matched_comparison = next((c for c in COMPARISONS if text.startswith(c, i)), None)
        if matched_comparison:
            tokens.append(Token("op", matched_comparison, i))
            i += len(matched_comparison)
            continue

        if char in ARITHMETIC:
            tokens.append(Token("op", char, i))
            i += 1
            continue

        number_match = _NUMBER.match(text, i)
        if number_match:
            tokens.append(Token("number", float(number_match.group()), i))
            i = number_match.end()
            continue

        word_match = _WORD.match(text, i)
        if word_match:
            raw = word_match.group()
            lowered_first = raw.split(" ", 1)[0].lower()
            if lowered_first in KEYWORDS:
                tokens.append(Token(lowered_first, lowered_first, i))  # type: ignore[arg-type]
                i += len(lowered_first)
                continue

            column, consumed = _longest_column(raw)
            if column is None:
                word = raw.split(" ", 1)[0]
                raise QueryError(f'Unknown column: "{word.strip()}"', i)
            tokens.append(Token("column", column, i))
            i += consumed
            continue

        raise QueryError(f'Unexpected character: "{char}"', i)

    tokens.append(Token("end", None, n))
    return tokens


def _longest_column(raw: str) -> tuple[Column | None, int]:
    """Greedily match the longest run of words that names a column.

    "Return on equity > 15" must resolve "Return on equity" rather than stopping
    at "Return". Words are consumed until a keyword or the ceiling is hit, then
    prefixes are tried longest first.
    """
    words = raw.split(" ")
    limit = len(words)
    for index, word in enumerate(words):
        if word.lower() in KEYWORDS:
            limit = index
            break
    limit = min(limit, MAX_COLUMN_WORDS)

    for count in range(limit, 0, -1):
        candidate = " ".join(words[:count]).strip()
        if not candidate:
            continue
        column = resolve(candidate)
        if column is not None:
            # Consume exactly the matched text, including its internal spaces.
            return column, len(" ".join(words[:count]))
    return None, 0


class Parser:
    """Recursive descent over the token stream."""

    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    @property
    def current(self) -> Token:
        return self.tokens[self.pos]

    def advance(self) -> Token:
        token = self.tokens[self.pos]
        self.pos += 1
        return token

    def expect(self, kind: TokenKind) -> Token:
        if self.current.kind != kind:
            raise QueryError(
                f"Expected {kind} but found {self.current.kind}", self.current.position
            )
        return self.advance()

    def parse(self) -> Node:
        if self.current.kind == "end":
            raise QueryError("The query is empty")
        node = self.parse_or()
        if self.current.kind != "end":
            raise QueryError(
                f"Unexpected trailing input at position {self.current.position}",
                self.current.position,
            )
        return node

    def parse_or(self) -> Node:
        node = self.parse_and()
        while self.current.kind == "or":
            self.advance()
            node = LogicalNode("OR", node, self.parse_and())
        return node

    def parse_and(self) -> Node:
        node = self.parse_not()
        while self.current.kind == "and":
            self.advance()
            node = LogicalNode("AND", node, self.parse_not())
        return node

    def parse_not(self) -> Node:
        if self.current.kind == "not":
            self.advance()
            return NotNode(self.parse_not())
        return self.parse_condition()

    def parse_condition(self) -> Node:
        if self.current.kind == "lparen":
            self.advance()
            node = self.parse_or()
            self.expect("rparen")
            return node

        left = self.parse_arithmetic()

        if self.current.kind == "in":
            self.advance()
            if not isinstance(left, ColumnNode):
                raise QueryError("IN needs a column on its left", self.current.position)
            return self.parse_in(left.column)

        if self.current.kind != "op" or self.current.value not in COMPARISONS:
            raise QueryError("Expected a comparison such as > or <", self.current.position)
        op = str(self.advance().value)
        op = {"==": "=", "<>": "!="}.get(op, op)

        if self.current.kind == "string":
            value = str(self.advance().value)
            if not isinstance(left, ColumnNode):
                raise QueryError("A text comparison needs a column on its left")
            return InNode(left.column, (value,), negated=op == "!=")

        right = self.parse_arithmetic()
        return CompareNode(op, left, right)

    def parse_in(self, column: Column) -> Node:
        self.expect("lparen")
        values: list[str] = []
        while True:
            token = self.current
            if token.kind == "string":
                values.append(str(self.advance().value))
            elif token.kind == "column":
                # A bare word inside IN(...) is a value, not a column reference.
                values.append(str(self.advance().value.label))  # type: ignore[union-attr]
            elif token.kind == "number":
                values.append(str(self.advance().value))
            else:
                raise QueryError("Expected a value inside IN(...)", token.position)
            if self.current.kind == "comma":
                self.advance()
                continue
            break
        self.expect("rparen")
        if not values:
            raise QueryError("IN(...) needs at least one value")
        return InNode(column, tuple(values))

    def parse_arithmetic(self) -> Node:
        node = self.parse_term()
        while self.current.kind == "op" and self.current.value in ("+", "-"):
            op = str(self.advance().value)
            node = BinaryNode(op, node, self.parse_term())
        return node

    def parse_term(self) -> Node:
        node = self.parse_factor()
        while self.current.kind == "op" and self.current.value in ("*", "/"):
            op = str(self.advance().value)
            node = BinaryNode(op, node, self.parse_factor())
        return node

    def parse_factor(self) -> Node:
        token = self.current
        if token.kind == "op" and token.value == "-":
            self.advance()
            return BinaryNode("-", NumberNode(0.0), self.parse_factor())
        if token.kind == "number":
            self.advance()
            return NumberNode(float(token.value))  # type: ignore[arg-type]
        if token.kind == "column":
            self.advance()
            return ColumnNode(token.value)  # type: ignore[arg-type]
        if token.kind == "lparen":
            self.advance()
            node = self.parse_arithmetic()
            self.expect("rparen")
            return node
        raise QueryError("Expected a column, a number or a bracket", token.position)


def count_nodes(node: Node) -> int:
    if isinstance(node, LogicalNode):
        return 1 + count_nodes(node.left) + count_nodes(node.right)
    if isinstance(node, NotNode):
        return 1 + count_nodes(node.operand)
    if isinstance(node, BinaryNode | CompareNode):
        return 1 + count_nodes(node.left) + count_nodes(node.right)
    return 1


MAX_NODES = 120


def parse(text: str) -> Node:
    """Parse a query, or raise QueryError with a message fit to show a user."""
    if not text or not text.strip():
        raise QueryError("The query is empty")
    node = Parser(tokenise(text)).parse()
    if count_nodes(node) > MAX_NODES:
        raise QueryError("The query is too complex; try splitting it up")
    return node


def columns_used(node: Node) -> set[str]:
    if isinstance(node, ColumnNode):
        return {node.column.key}
    if isinstance(node, InNode):
        return {node.column.key}
    if isinstance(node, LogicalNode | BinaryNode | CompareNode):
        return columns_used(node.left) | columns_used(node.right)
    if isinstance(node, NotNode):
        return columns_used(node.operand)
    return set()
