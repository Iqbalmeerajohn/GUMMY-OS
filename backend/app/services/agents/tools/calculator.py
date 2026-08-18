"""Green tool: evaluate an arithmetic expression, safely.

``eval`` is never used, and that is the whole point of this module. The very
first probe of a local model with tools attached produced this call:

    calculator(expression="print('Hello')")

The model was asked to say hello and reached for the calculator anyway, passing
Python. Any implementation built on ``eval`` would have executed it. Small models
emit confidently wrong tool arguments, so a tool's safety cannot rest on the
model's good behaviour — it has to be a property of the tool.

So the expression is parsed with ``ast.parse`` in ``eval`` mode and walked over
an allowlist of node types. Names, calls, attributes, subscripts, comprehensions
and imports are not in that allowlist, which makes ``print('Hello')``,
``__import__('os').system(...)`` and every other code-execution shape a parse-
level rejection rather than something the sandbox has to out-think.
"""

from __future__ import annotations

import ast
import operator
from typing import Any

from app.services.agents.tools.context import ToolContext

# Binary/unary operators that are pure arithmetic. Anything absent here (matrix
# multiply, bitwise ops on huge ints, etc.) is rejected rather than approximated.
_BIN_OPS: dict[type[ast.operator], Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS: dict[type[ast.unaryop], Any] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

# Bounds on exponentiation. ``9**9**9`` is syntactically tiny and computationally
# unbounded, so it would hang the executor's thread rather than time out cleanly.
_MAX_EXPONENT = 128
_MAX_EXPRESSION_CHARS = 200


class CalculatorError(ValueError):
    """The expression is not safe, well-formed arithmetic."""


def _evaluate(node: ast.AST) -> float | int:
    """Recursively evaluate an allowlisted arithmetic node."""
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, int | float):
            raise CalculatorError("only numeric literals are allowed")
        return node.value
    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPS.get(type(node.op))
        if op is None:
            raise CalculatorError(
                f"unsupported unary operator {type(node.op).__name__}"
            )
        return op(_evaluate(node.operand))
    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise CalculatorError(f"unsupported operator {type(node.op).__name__}")
        left, right = _evaluate(node.left), _evaluate(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > _MAX_EXPONENT:
            raise CalculatorError(f"exponent above {_MAX_EXPONENT} is not allowed")
        try:
            return op(left, right)
        except ZeroDivisionError as exc:
            raise CalculatorError("division by zero") from exc
    raise CalculatorError(
        f"{type(node).__name__} is not allowed — arithmetic expressions only"
    )


def calculate(expression: str) -> float | int:
    """Evaluate ``expression`` as pure arithmetic, or raise ``CalculatorError``."""
    cleaned = expression.strip()
    if not cleaned:
        raise CalculatorError("expression must not be empty")
    if len(cleaned) > _MAX_EXPRESSION_CHARS:
        raise CalculatorError(
            f"expression must be at most {_MAX_EXPRESSION_CHARS} characters"
        )
    try:
        tree = ast.parse(cleaned, mode="eval")
    except SyntaxError as exc:
        raise CalculatorError(f"could not parse {cleaned!r} as arithmetic") from exc
    return _evaluate(tree)


async def execute(context: ToolContext, args: dict) -> dict:
    """Evaluate ``args['expression']``."""
    expression = str(args.get("expression", ""))
    result = calculate(expression)
    return {"expression": expression.strip(), "result": result}
