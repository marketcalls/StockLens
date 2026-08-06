"""AST -> parameterised SQL.

Two rules make this safe:

1. Column identifiers only ever come from `Column.key`, which originates in the
   catalog. A name the parser could not resolve becomes a QueryError long before
   it reaches here, so no user text is ever interpolated as an identifier.
2. Every literal becomes a bound parameter.

NULL handling is the other half of the job. In SQL, `NULL > 15` is NULL rather
than false, which is what we want - a company with no reported return on equity
should be excluded from `ROE > 15` rather than silently treated as zero. But
`NOT (pledge > 0)` would then also exclude it, when the user almost certainly
means "companies without a pledge". NOT therefore treats an unknown as true.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.screener.parser import (
    BinaryNode,
    ColumnNode,
    CompareNode,
    InNode,
    LogicalNode,
    Node,
    NotNode,
    NumberNode,
    QueryError,
)

# Text columns that a bare `IN (...)` or `=` should match against.
TEXT_COLUMNS = {"sector", "industry", "macro_sector", "sub_industry", "name", "schema_kind"}

INDEX_PSEUDO_COLUMN = "index"


@dataclass
class Compiled:
    where: str
    params: dict[str, Any] = field(default_factory=dict)
    columns: set[str] = field(default_factory=set)


class Compiler:
    def __init__(self) -> None:
        self.params: dict[str, Any] = {}
        self.columns: set[str] = set()
        self._counter = 0

    def bind(self, value: Any) -> str:
        self._counter += 1
        name = f"p{self._counter}"
        self.params[name] = value
        return f":{name}"

    def compile(self, node: Node) -> Compiled:
        where = self.visit(node)
        return Compiled(where=where, params=self.params, columns=self.columns)

    def visit(self, node: Node) -> str:
        if isinstance(node, LogicalNode):
            return f"({self.visit(node.left)} {node.op} {self.visit(node.right)})"

        if isinstance(node, NotNode):
            inner = self.visit(node.operand)
            # Unknown stays unknown. This used to be COALESCE(inner, 0), on the
            # reasoning that "NOT (pledge > 0)" should include companies that
            # report no pledge - but a missing figure means the statements have
            # not been downloaded, not that the value is zero. With the coalesce,
            # "NOT (Price to Earning > 20)" returned 5,180 companies when only 54
            # are known to trade under 20 times earnings, because five thousand
            # companies with no P/E were counted as having a P/E of zero.
            #
            # Every other operator already drops unknowns - `pe <= 20` gives 54
            # and `pe > 20` gives 157, together exactly the 211 companies that
            # have a P/E - so NOT was the one place the rule did not hold.
            return f"(NOT {inner})"

        if isinstance(node, CompareNode):
            left = self.expr(node.left)
            right = self.expr(node.right)
            return f"({left} {node.op} {right})"

        if isinstance(node, InNode):
            return self.visit_in(node)

        raise QueryError("A condition was expected here")

    def visit_in(self, node: InNode) -> str:
        key = node.column.key
        self.columns.add(key)

        if key == INDEX_PSEUDO_COLUMN:
            placeholders = ", ".join(self.bind(v) for v in node.values)
            clause = (
                "EXISTS (SELECT 1 FROM snapshot_index_membership m "
                "WHERE m.symbol = company_snapshot.symbol "
                f"AND m.index_symbol IN ({placeholders}))"
            )
            return f"(NOT {clause})" if node.negated else f"({clause})"

        # Case-insensitive so `Sector IN ("banks")` matches "Banks".
        values = ", ".join(f"UPPER({self.bind(v)})" for v in node.values)
        clause = f"UPPER({key}) IN ({values})"
        # Same rule as NOT above: a company with no sector recorded does not
        # match `Sector NOT IN (...)`, because nothing is known about it.
        return f"(NOT {clause})" if node.negated else f"({clause})"

    def expr(self, node: Node) -> str:
        if isinstance(node, NumberNode):
            return self.bind(node.value)
        if isinstance(node, ColumnNode):
            key = node.column.key
            self.columns.add(key)
            # Identifier comes from the catalog, never from user text.
            return key
        if isinstance(node, BinaryNode):
            left = self.expr(node.left)
            right = self.expr(node.right)
            if node.op == "/":
                # Division by zero yields NULL in SQLite rather than an error,
                # but guard explicitly so intent is visible.
                return f"({left} / NULLIF({right}, 0))"
            return f"({left} {node.op} {right})"
        raise QueryError("Expected a value or an arithmetic expression")


def compile_query(node: Node) -> Compiled:
    return Compiler().compile(node)
