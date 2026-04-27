from __future__ import annotations

"""
Preface: Sheaf-Theoretic View of Alpha Construction
=================================================

We interpret the WorldQuant operator system through a sheaf-theoretic lens:

    Field        -> section (data over instruments × time)
    Operator     -> local morphism (acts on sections locally)
    Expression   -> composition of morphisms
    Alpha        -> global section (a signal defined over the universe)

Implications:
    - Local-to-global: valid alphas are those compositions that are well-defined
      and stable under restriction (sub-universes / time windows).
    - Compatibility: operator compositions should respect domain constraints
      (e.g., positivity for log, non-zero denominators for divide).
    - Regularization: constraints can be viewed as gluing/consistency conditions.

This module implements a minimal DSL that lifts scraped operator docs into
composable objects (Expr trees) with validation, rendering, and random generation.

"""

"""
Operator DSL Layer for WorldQuant Brain-style Alpha Expressions
===============================================================

Input:
    operators_full.csv

Goal:
    1. Load operator metadata as an OperatorRegistry.
    2. Represent alpha expressions as expression trees.
    3. Render expression trees back to WQ Brain-style strings.
    4. Provide a minimal random alpha generator.

This is the next layer after scraping operators.
"""



import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

import pandas as pd


# ============================================================
# 1. Operator metadata
# ============================================================


@dataclass
class OperatorSpec:
    """Metadata for one WorldQuant-style operator."""

    name: str
    signature: str
    level: str = ""
    short_desc: str = ""
    long_desc: str = ""
    examples: str = ""
    arity: Optional[int] = None

    @staticmethod
    def from_row(row: pd.Series) -> "OperatorSpec":
        signature = str(row.get("operator", "")).strip()
        name = extract_operator_name(signature)
        arity = infer_arity(signature)

        return OperatorSpec(
            name=name,
            signature=signature,
            level=str(row.get("level", "")).strip(),
            short_desc=str(row.get("short_desc", "")).strip(),
            long_desc=str(row.get("long_desc", "")).strip(),
            examples=str(row.get("examples", "")).strip(),
            arity=arity,
        )


class OperatorRegistry:
    """A searchable registry of available operators."""

    def __init__(self, specs: Sequence[OperatorSpec]):
        self.specs: Dict[str, OperatorSpec] = {spec.name: spec for spec in specs if spec.name}

    @classmethod
    def from_csv(cls, path: Union[str, Path]) -> "OperatorRegistry":
        df = pd.read_csv(path)
        specs = [OperatorSpec.from_row(row) for _, row in df.iterrows()]
        return cls(specs)

    def get(self, name: str) -> OperatorSpec:
        if name not in self.specs:
            raise KeyError(f"Unknown operator: {name}")
        return self.specs[name]

    def has(self, name: str) -> bool:
        return name in self.specs

    def search(self, keyword: str) -> List[OperatorSpec]:
        keyword = keyword.lower()
        out = []
        for spec in self.specs.values():
            haystack = " ".join([
                spec.name,
                spec.signature,
                spec.short_desc,
                spec.long_desc,
                spec.examples,
            ]).lower()
            if keyword in haystack:
                out.append(spec)
        return out

    def names(self) -> List[str]:
        return sorted(self.specs.keys())


# ============================================================
# 2. Expression tree
# ============================================================


class Expr:
    """Base class for alpha expressions."""

    def render(self) -> str:
        raise NotImplementedError

    def depth(self) -> int:
        raise NotImplementedError


@dataclass
class Field(Expr):
    """A raw data field, e.g. close, volume, open."""

    name: str

    def render(self) -> str:
        return self.name

    def depth(self) -> int:
        return 0


@dataclass
class Const(Expr):
    """A scalar constant."""

    value: Union[int, float, str]

    def render(self) -> str:
        return str(self.value)

    def depth(self) -> int:
        return 0


@dataclass
class Op(Expr):
    """Operator node, e.g. log(close), add(open, close)."""

    name: str
    args: List[Expr] = field(default_factory=list)
    kwargs: Dict[str, Union[str, int, float, bool]] = field(default_factory=dict)

    def render(self) -> str:
        rendered_args = [arg.render() for arg in self.args]
        rendered_kwargs = [f"{k}={format_value(v)}" for k, v in self.kwargs.items()]
        inside = ", ".join(rendered_args + rendered_kwargs)
        return f"{self.name}({inside})"

    def depth(self) -> int:
        if not self.args:
            return 1
        return 1 + max(arg.depth() for arg in self.args)


# ============================================================
# 3. Helper functions
# ============================================================


def extract_operator_name(signature: str) -> str:
    """Extract name from signature like 'add(x, y), x + y' -> 'add'."""
    match = re.match(r"\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", signature)
    if match:
        return match.group(1)
    return ""


def infer_arity(signature: str) -> Optional[int]:
    name = extract_operator_name(signature)

    ARITY_OVERRIDES = {
        "abs": 1,
        "log": 1,
        "rank": 1,
        "inverse": 1,

        "add": 2,
        "subtract": 2,
        "multiply": 2,
        "divide": 2,

        "ts_mean": 2,
        "ts_std_dev": 2,
        "ts_rank": 2,
        "ts_delta": 2,
    }

    if name in ARITY_OVERRIDES:
        return ARITY_OVERRIDES[name]
    """Infer rough arity from signature.

    Required positional arguments are counted.
    Optional keyword arguments like filter=false or rate=2 are ignored.
    """
    match = re.match(r"\s*[a-zA-Z_][a-zA-Z0-9_]*\s*\(([^)]*)\)", signature)
    if not match:
        return None

    inside = match.group(1).strip()

    if ".." in inside or "..." in inside:
        return None

    if not inside:
        return 0

    parts = [p.strip() for p in inside.split(",")]

    required = []
    for p in parts:
        # normalize spaces around =
        p_clean = re.sub(r"\s+", "", p)

        # optional keyword-like parameter, e.g. filter=false, rate=2
        if "=" in p_clean:
            continue

        required.append(p)

    return len(required)


def format_value(v: Union[str, int, float, bool]) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def validate_expr(expr: Expr, registry: OperatorRegistry) -> None:
    """Basic operator-existence and arity validation."""
    if isinstance(expr, (Field, Const)):
        return

    if isinstance(expr, Op):
        if not registry.has(expr.name):
            raise ValueError(f"Unknown operator: {expr.name}")

        spec = registry.get(expr.name)
        if spec.arity is not None and len(expr.args) != spec.arity:
            raise ValueError(
                f"Operator {expr.name} expects arity {spec.arity}, got {len(expr.args)}"
            )

        for arg in expr.args:
            validate_expr(arg, registry)
        return

    raise TypeError(f"Unknown expression type: {type(expr)}")


# ============================================================
# 4. Manual alpha construction examples
# ============================================================


def example_alpha_1() -> Expr:
    """A simple momentum alpha: rank(subtract(close, open))."""
    return Op(
        "rank",
        [
            Op("subtract", [Field("close"), Field("open")])
        ],
    )


def example_alpha_2() -> Expr:
    """A volume-price nonlinear signal: rank(log(multiply(volume, close)))."""
    return Op(
        "rank",
        [
            Op(
                "log",
                [
                    Op("multiply", [Field("volume"), Field("close")]),
                ],
            )
        ],
    )


# ============================================================
# 5. Random alpha generator
# ============================================================


DEFAULT_FIELDS = [
    "open",
    "close",
    "high",
    "low",
    "volume",
    "returns",
    "vwap",
]

UNARY_OPS = [
    "abs",
    "log",
    "rank",
    "inverse",
]

BINARY_OPS = [
    "add",
    "subtract",
    "multiply",
    "divide",
]

TIME_SERIES_OPS = [
    "ts_mean",
    "ts_std_dev",
    "ts_rank",
    "ts_delta",
]

WINDOWS = [5, 10, 20, 60]


def random_leaf(fields: Sequence[str] = DEFAULT_FIELDS) -> Expr:
    return Field(random.choice(list(fields)))


def random_expr(
    registry: OperatorRegistry,
    max_depth: int = 3,
    fields: Sequence[str] = DEFAULT_FIELDS,
) -> Expr:
    """Generate a random alpha expression tree.

    This is intentionally conservative: it only uses common operators if they exist
    in the scraped registry.
    """
    if max_depth <= 0:
        return random_leaf(fields)

    candidates = []

    candidates += [op for op in UNARY_OPS if registry.has(op)]
    candidates += [op for op in BINARY_OPS if registry.has(op)]
    candidates += [op for op in TIME_SERIES_OPS if registry.has(op)]

    if not candidates:
        return random_leaf(fields)

    op = random.choice(candidates)

    if op in UNARY_OPS:
        return Op(op, [random_expr(registry, max_depth - 1, fields)])

    if op in BINARY_OPS:
        return Op(
            op,
            [
                random_expr(registry, max_depth - 1, fields),
                random_expr(registry, max_depth - 1, fields),
            ],
        )

    if op in TIME_SERIES_OPS:
        # WQ-style time-series operators usually look like ts_mean(x, d)
        return Op(
            op,
            [
                random_expr(registry, max_depth - 1, fields),
                Const(random.choice(WINDOWS)),
            ],
        )

    return random_leaf(fields)


# ============================================================
# 6. Sheaf interpretation layer, minimal version
# ============================================================


@dataclass
class SheafAlphaLayer:
    """Minimal conceptual wrapper.

    Interpretation:
        - Fields are sections over an instrument-time universe.
        - Operators are local morphisms of sections.
        - Alpha expressions are compositional morphisms.
    """

    registry: OperatorRegistry

    def compile(self, expr: Expr) -> str:
        validate_expr(expr, self.registry)
        return expr.render()

    def random_alpha(self, max_depth: int = 3) -> str:
        expr = random_expr(self.registry, max_depth=max_depth)
        return self.compile(expr)


# ============================================================
# 7. Demo
# ============================================================


def main():
    registry_path = Path("operators_full.csv")

    if not registry_path.exists():
        raise FileNotFoundError(
            "operators_full.csv not found. First parse operators_page_text.txt into operators_full.csv."
        )

    registry = OperatorRegistry.from_csv(registry_path)
    layer = SheafAlphaLayer(registry)

    print("Loaded operators:", len(registry.names()))
    print("First 20 operators:", registry.names()[:20])

    print("\nManual alpha examples:")
    for expr in [example_alpha_1(), example_alpha_2()]:
        try:
            print("  ", layer.compile(expr))
        except Exception as e:
            print("  validation failed:", e)
            print("  raw:", expr.render())

    print("\nRandom alpha examples:")
    for _ in range(10):
        try:
            print("  ", layer.random_alpha(max_depth=3))
        except Exception as e:
            print("  failed:", e)


if __name__ == "__main__":
    main()
