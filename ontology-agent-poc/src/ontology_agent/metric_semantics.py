from __future__ import annotations

import re
from decimal import Decimal
from typing import Mapping

from .models import FormulaNode, Metric, Property


_UNIT_ALIASES = {
    "%": "PERCENT",
    "PCT": "PERCENT",
    "PERCENTAGE": "PERCENT",
    "PERCENT": "PERCENT",
    "FRACTION": "RATIO",
    "RATIO": "RATIO",
    "MS": "MILLISECOND",
    "MILLISECONDS": "MILLISECOND",
    "MILLISECOND": "MILLISECOND",
    "SHARES": "SHARE",
    "SHARE": "SHARE",
    "COUNTS": "COUNT",
    "COUNT": "COUNT",
    "ORDERS": "ORDER",
    "ORDER": "ORDER",
    "TRADES": "TRADE",
    "TRADE": "TRADE",
}
_CURRENCY_UNIT = re.compile(r"^(?P<currency>[A-Z]{3})(?:_(?P<scale>MN|M|MILLION))?$")


def canonical_unit(value: str | None) -> str | None:
    """Normalize only mechanically equivalent unit spellings.

    This is intentionally a small vocabulary.  It may prove that ``USD`` is not
    ``HKD_MN``; it must not invent an FX conversion or decide a business unit.
    """

    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if stripped == "%":
        return "PERCENT"
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", stripped).strip("_").upper()
    aliased = _UNIT_ALIASES.get(normalized, normalized)
    currency = _CURRENCY_UNIT.fullmatch(aliased)
    if currency and currency.group("scale"):
        return f"{currency.group('currency')}_MN"
    return aliased


def units_compatible(left: str | None, right: str | None) -> bool:
    left_unit = canonical_unit(left)
    right_unit = canonical_unit(right)
    if left_unit is None or right_unit is None:
        return True
    if left_unit == right_unit:
        return True
    return is_count_like(left_unit) and is_count_like(right_unit)


def is_count_like(value: str | None) -> bool:
    unit = canonical_unit(value)
    return bool(
        unit
        and (
            unit in {"COUNT", "ORDER", "TRADE", "TRADE_SIDE", "SHARE"}
            or unit.endswith("_COUNT")
        )
    )


def formula_operations(node: FormulaNode) -> set[str]:
    operations = {node.op}
    for child in node.args:
        operations.update(formula_operations(child))
    return operations


def formula_literals(node: FormulaNode) -> tuple[Decimal, ...]:
    values: list[Decimal] = []
    if node.op == "literal" and node.value is not None:
        values.append(node.value)
    for child in node.args:
        values.extend(formula_literals(child))
    return tuple(values)


def infer_formula_unit(
    node: FormulaNode,
    *,
    metrics: Mapping[str, Metric],
    properties: Mapping[str, Property],
) -> str | None:
    """Infer a unit only where the formula proves one mechanically.

    Unknown compound-unit algebra returns ``None`` and stays a review concern.
    Strong contradictions such as directly relabelling USD as HKD remain
    deterministic validation failures.
    """

    if node.op == "field_ref":
        prop = properties.get(node.ref or "")
        return canonical_unit(prop.unit if prop else None)
    if node.op == "metric_ref":
        metric = metrics.get(node.ref or "")
        return canonical_unit(metric.unit if metric else None)
    if node.op == "literal":
        return "SCALAR"
    if node.op == "count_distinct":
        return "COUNT"
    if node.op == "duration_ms":
        return "MILLISECOND"
    if node.op == "sum":
        return infer_formula_unit(node.args[0], metrics=metrics, properties=properties)

    left = infer_formula_unit(node.args[0], metrics=metrics, properties=properties)
    right = infer_formula_unit(node.args[1], metrics=metrics, properties=properties)
    if node.op in {"add", "subtract"}:
        return left if units_compatible(left, right) else None
    if node.op == "multiply":
        if left == "SCALAR":
            other = right
            literal = node.args[0].value
        elif right == "SCALAR":
            other = left
            literal = node.args[1].value
        else:
            return None
        if other == "RATIO" and literal == Decimal("100"):
            return "PERCENT"
        return other
    if node.op == "divide":
        if right == "SCALAR":
            literal = node.args[1].value
            currency = _CURRENCY_UNIT.fullmatch(left or "")
            if currency and not currency.group("scale") and literal == Decimal("1000000"):
                return f"{currency.group('currency')}_MN"
            return left
        if left == right and left is not None:
            return "RATIO"
        if is_count_like(left) and is_count_like(right):
            return "RATIO"
    return None


def expanded_formula_facts(
    metric: Metric,
    *,
    metrics: Mapping[str, Metric],
) -> tuple[set[str], tuple[Decimal, ...], set[str]]:
    """Return recursive operations, literals and referenced metric units."""

    operations: set[str] = set()
    literals: list[Decimal] = []
    referenced_units: set[str] = set()
    visited: set[str] = set()

    def visit(node: FormulaNode) -> None:
        operations.add(node.op)
        if node.op == "literal" and node.value is not None:
            literals.append(node.value)
        if node.op == "metric_ref" and node.ref in metrics:
            referenced = metrics[node.ref]
            unit = canonical_unit(referenced.unit)
            if unit:
                referenced_units.add(unit)
            if referenced.id not in visited:
                visited.add(referenced.id)
                visit(referenced.formula)
        for child in node.args:
            visit(child)

    visited.add(metric.id)
    visit(metric.formula)
    return operations, tuple(literals), referenced_units
