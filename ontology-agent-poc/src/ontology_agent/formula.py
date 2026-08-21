from __future__ import annotations

from decimal import Decimal

from .models import FormulaNode


class FormulaEvaluationError(ValueError):
    pass


def evaluate_scalar_formula(
    node: FormulaNode,
    metric_values: dict[str, Decimal],
    *,
    zero_denominator_policy: str = "refuse",
) -> Decimal:
    if node.op == "metric_ref":
        if not node.ref or node.ref not in metric_values:
            raise FormulaEvaluationError(f"Missing metric value for {node.ref}")
        return metric_values[node.ref]
    if node.op == "literal":
        if node.value is None:
            raise FormulaEvaluationError("Literal has no value")
        return node.value
    if node.op in {"field_ref", "sum", "count_distinct"}:
        raise FormulaEvaluationError(f"Aggregate operation {node.op} cannot run in the scalar evaluator")
    left = evaluate_scalar_formula(
        node.args[0], metric_values, zero_denominator_policy=zero_denominator_policy
    )
    right = evaluate_scalar_formula(
        node.args[1], metric_values, zero_denominator_policy=zero_denominator_policy
    )
    if node.op == "add":
        return left + right
    if node.op == "subtract":
        return left - right
    if node.op == "multiply":
        return left * right
    if node.op == "divide":
        if right == 0:
            if zero_denominator_policy == "zero":
                return Decimal("0")
            if zero_denominator_policy == "null":
                raise FormulaEvaluationError("Null scalar results are not supported by this runtime")
            raise FormulaEvaluationError("Formula denominator is zero")
        return left / right
    raise FormulaEvaluationError(f"Unsupported scalar operation {node.op}")
