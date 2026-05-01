"""
Fix for operator arity handling in op_dsl.py
核心思想：
- 不再使用单一 arity
- 改为 (min_arity, max_arity)
- 支持 optional 参数
"""

from dataclasses import dataclass
from typing import List, Dict, Any
import os
import json

# =========================
# Operator 定义
# =========================

@dataclass
class OperatorSpec:
    name: str
    min_arity: int
    max_arity: int
    description: str = ""


# =========================
# 手动修复表（关键！！）
# =========================

ARITY_FIXES: Dict[str, tuple] = {
    "rank": (1, 2),
    "subtract": (2, 3),
    "multiply": (2, 3),
    "add": (2, 3),
    "divide": (2, 2),
    "log": (1, 1),
    "abs": (1, 1),
    "inverse": (1, 1),
    "ts_delta": (2, 2),
    "ts_rank": (2, 2),
}


# =========================
# 加载 operator（示例）
# =========================

def load_operators() -> Dict[str, OperatorSpec]:
    """
    这里假设你原来是从 txt/csv 抓取 operator
    现在统一在这里修正 arity
    """

    raw_ops = [
        "abs", "rank", "subtract", "multiply", "add", "divide",
        "log", "inverse", "ts_delta", "ts_rank"
    ]

    ops = {}

    for name in raw_ops:
        if name in ARITY_FIXES:
            min_a, max_a = ARITY_FIXES[name]
        else:
            # fallback（避免崩溃）
            min_a, max_a = (1, 1)

        ops[name] = OperatorSpec(
            name=name,
            min_arity=min_a,
            max_arity=max_a
        )

    return ops


# =========================
# AST 节点
# =========================

class Node:
    def __init__(self, op: str, args: List['Node']):
        self.op = op
        self.args = args


# =========================
# 验证函数（核心修改）
# =========================

# =========================
# 终端节点（fields & constants）
# =========================

FIELDS = {"open", "close", "high", "low", "volume", "vwap", "returns"}


def is_number(x: str) -> bool:
    try:
        float(x)
        return True
    except ValueError:
        return False


# =========================
# 验证函数（核心修改）
# =========================

def validate(node: Node, ops: Dict[str, OperatorSpec]):
    """
    递归验证表达式是否合法
    """

    # ---- 1. 叶子节点：field / numeric constant ----
    if len(node.args) == 0:
        if node.op in FIELDS or is_number(node.op):
            return
        raise ValueError(f"Unknown terminal: {node.op}")

    # ---- 2. operator 节点 ----
    if node.op not in ops:
        raise ValueError(f"Unknown operator: {node.op}")

    spec = ops[node.op]
    argc = len(node.args)

    if not (spec.min_arity <= argc <= spec.max_arity):
        raise ValueError(
            f"Operator {node.op} expects [{spec.min_arity}, {spec.max_arity}], got {argc}"
        )

    # ---- 3. 递归检查子节点 ----
    for arg in node.args:
        validate(arg, ops)


# =========================
# DSL Parser：字符串 -> AST
# =========================

class Parser:
    """
    一个极简 recursive descent parser。

    支持格式：
        rank(divide(subtract(close, open), open))
        rank(log(add(volume, 1)))

    语法：
        expr := NAME | NUMBER | NAME '(' expr (',' expr)* ')'

    解释：
        - NAME(...) 是 operator node
        - NAME 单独出现是 field terminal
        - NUMBER 单独出现是 constant terminal
    """

    def __init__(self, text: str):
        self.text = text
        self.i = 0

    def parse(self) -> Node:
        node = self.parse_expr()
        self.skip_spaces()
        if self.i != len(self.text):
            raise ValueError(f"Unexpected trailing text at position {self.i}: {self.text[self.i:]}")
        return node

    def parse_expr(self) -> Node:
        self.skip_spaces()
        name = self.parse_name_or_number()
        self.skip_spaces()

        # operator call: name(...)
        if self.peek() == "(":
            self.i += 1
            args = []
            self.skip_spaces()

            # support empty argument list, though validator may reject it
            if self.peek() == ")":
                self.i += 1
                return Node(name, args)

            while True:
                args.append(self.parse_expr())
                self.skip_spaces()

                ch = self.peek()
                if ch == ",":
                    self.i += 1
                    continue
                elif ch == ")":
                    self.i += 1
                    break
                else:
                    raise ValueError(
                        f"Expected ',' or ')' at position {self.i}, got {repr(ch)}"
                    )

            return Node(name, args)

        # terminal: field or constant
        return Node(name, [])

    def parse_name_or_number(self) -> str:
        self.skip_spaces()
        start = self.i

        while self.i < len(self.text):
            ch = self.text[self.i]
            if ch.isalnum() or ch == "_" or ch == "." or ch == "-":
                self.i += 1
            else:
                break

        if start == self.i:
            raise ValueError(f"Expected name or number at position {self.i}")

        return self.text[start:self.i]

    def skip_spaces(self):
        while self.i < len(self.text) and self.text[self.i].isspace():
            self.i += 1

    def peek(self) -> str:
        if self.i >= len(self.text):
            return ""
        return self.text[self.i]


def parse_alpha(text: str) -> Node:
    """
    外部调用接口：
        node = parse_alpha("rank(log(volume))")
    """
    return Parser(text).parse()


def to_dsl(node: Node) -> str:
    """
    AST -> DSL string。
    用于把结构化表达式重新输出成 Brain 可提交字符串。
    """
    if len(node.args) == 0:
        return node.op
    return f"{node.op}(" + ", ".join(to_dsl(arg) for arg in node.args) + ")"


# =========================
# Random Alpha Generator：自动生成合法 alpha
# =========================

import random
import csv
from pathlib import Path

DEFAULT_FIELDS = ["open", "close", "high", "low", "volume", "vwap", "returns"]
DEFAULT_CONSTANTS = ["1", "2", "5", "10", "20", "60", "0.5", "-1"]

# 不同 operator 的经验参数偏好
WINDOW_OPS = {"ts_delta", "ts_rank", "kth_element", "days_from_last_change", "last_diff_value"}
GROUP_OPS = {"group_mean", "group_neutralize", "group_rank", "group_scale", "group_zscore", "group_backfill"}
LOGICAL_OPS = {"and", "if_else"}


def random_terminal() -> Node:
    """
    随机生成叶子节点：field 或 numeric constant。
    大部分时候选择 field，少部分时候选择常数。
    """
    if random.random() < 0.8:
        return Node(random.choice(DEFAULT_FIELDS), [])
    return Node(random.choice(DEFAULT_CONSTANTS), [])


def choose_operator(ops: Dict[str, OperatorSpec]) -> OperatorSpec:
    """
    从已加载 operator 中随机选择一个。
    这里暂时过滤掉 group / logical 类 operator，
    因为它们往往需要 group label 或 boolean condition，
    后面可以单独做高级生成规则。
    """
    candidates = []
    for name, spec in ops.items():
        if name in GROUP_OPS:
            continue
        if name in LOGICAL_OPS:
            continue
        candidates.append(spec)

    if not candidates:
        raise ValueError("No usable operators for random generation")

    return random.choice(candidates)


def random_alpha_tree(ops: Dict[str, OperatorSpec], max_depth: int = 3) -> Node:
    """
    随机生成一棵 alpha AST。

    规则：
    - depth 到 0 时生成 terminal
    - 否则随机选 operator
    - 参数个数在 [min_arity, max_arity] 中随机选
    - 对 ts_* window operator，最后一个参数通常是时间窗口常数
    - 对 rank(x, rate) 这种 optional 参数，第二个参数必须是数字
    """

    if max_depth <= 0:
        return random_terminal()

    # 一定概率提前终止，避免表达式过深
    if random.random() < 0.25:
        return random_terminal()

    spec = choose_operator(ops)
    argc = random.randint(spec.min_arity, spec.max_arity)

    args = []
    for j in range(argc):
        # ts/window operator 的最后一个参数通常是 window
        if spec.name in WINDOW_OPS and j == argc - 1:
            args.append(Node(random.choice(["5", "10", "20", "60"]), []))

        # rank(x, rate): 第二个参数是 numeric rate，而不是 field/expression
        elif spec.name == "rank" and j == 1:
            args.append(Node(random.choice(["1", "2", "3", "5"]), []))

        # add/subtract/multiply(x, y, filter): 第三个参数通常是 filter flag
        elif spec.name in {"add", "subtract", "multiply"} and j == 2:
            args.append(Node(random.choice(["0", "1"]), []))

        else:
            args.append(random_alpha_tree(ops, max_depth=max_depth - 1))

    return Node(spec.name, args)


def count_ops(node: Node) -> int:
    if len(node.args) == 0:
        return 0
    return 1 + sum(count_ops(a) for a in node.args)


def is_safe_log(node: Node) -> bool:
    """禁止 log(负常数) 这类明显非法的情况"""
    if node.op == "log" and len(node.args) == 1:
        arg = node.args[0]
        if len(arg.args) == 0 and is_number(arg.op):
            try:
                return float(arg.op) > 0
            except Exception:
                return False
    return True


def has_bad_divide_constant(node: Node) -> bool:
    """
    过滤 divide(-1, close), divide(1, x) 这类结构。

    直觉：
    - divide(-1, close) 本质接近 inverse(close) 的变体，容易放大异常值；
    - 常数 / field 通常不是有意义 alpha，而是尺度变换。
    """
    if node.op == "divide" and len(node.args) == 2:
        left, right = node.args
        if len(left.args) == 0 and is_number(left.op):
            if len(right.args) == 0 and right.op in FIELDS:
                return True
    return any(has_bad_divide_constant(arg) for arg in node.args)


def has_unsafe_inverse(node: Node) -> bool:
    """
    过滤 inverse(field) 或 inverse(常数) 这种过于尖锐的结构。
    """
    if node.op == "inverse" and len(node.args) == 1:
        arg = node.args[0]
        if len(arg.args) == 0:
            return True
    return any(has_unsafe_inverse(arg) for arg in node.args)


def is_semantically_valid(node: Node) -> bool:
    """简单语义过滤：复杂度 + 安全规则"""
    # 至少包含 2 个 operator
    if count_ops(node) < 2:
        return False

    # 递归检查 log 安全性
    stack = [node]
    while stack:
        cur = stack.pop()
        if not is_safe_log(cur):
            return False
        stack.extend(cur.args)

    # 过滤不稳定/低信息结构
    if has_bad_divide_constant(node):
        return False
    if has_unsafe_inverse(node):
        return False

    return True


PREFERRED_ROOTS = {"rank", "ts_rank", "ts_delta", "divide"}


def random_root_tree(ops: Dict[str, OperatorSpec], max_depth: int = 3) -> Node:
    """优先从更有意义的 root operator 开始生成"""
    roots = [ops[n] for n in ops if n in PREFERRED_ROOTS]
    if not roots:
        return random_alpha_tree(ops, max_depth)

    spec = random.choice(roots)
    argc = random.randint(spec.min_arity, spec.max_arity)
    args = []
    for j in range(argc):
        if spec.name in WINDOW_OPS and j == argc - 1:
            args.append(Node(random.choice(["5", "10", "20", "60"]), []))
        elif spec.name == "rank" and j == 1:
            args.append(Node(random.choice(["1", "2", "3", "5"]), []))
        else:
            args.append(random_alpha_tree(ops, max_depth=max_depth - 1))
    return Node(spec.name, args)


def generate_valid_alpha(ops: Dict[str, OperatorSpec], max_depth: int = 3, max_tries: int = 200) -> str:
    """
    反复生成随机 AST，直到通过 validate + 语义过滤。
    """
    last_error = None

    for _ in range(max_tries):
        node = random_root_tree(ops, max_depth=max_depth)
        try:
            validate(node, ops)
            if not is_semantically_valid(node):
                continue
            return to_dsl(node)
        except Exception as e:
            last_error = e

    raise RuntimeError(f"Failed to generate valid alpha after {max_tries} tries: {last_error}")


def generate_many_alphas(ops: Dict[str, OperatorSpec], n: int = 10, max_depth: int = 3) -> List[str]:
    """
    批量生成 alpha，并去重。
    """
    alphas = []
    seen = set()

    while len(alphas) < n:
        alpha = generate_valid_alpha(ops, max_depth=max_depth)
        if alpha not in seen:
            seen.add(alpha)
            alphas.append(alpha)

    return alphas


# =========================
# LLM -> Alpha：结构化生成层
# =========================

IDEA_TEMPLATES = {
    "momentum": [
        "rank(ts_delta(close, 5))",
        "rank(ts_delta(close, 20))",
        "ts_rank(ts_delta(close, 5), 20)",
        "rank(divide(subtract(close, open), open))",
    ],
    "reversal": [
        "rank(inverse(ts_delta(close, 5)))",
        "rank(subtract(open, close))",
        "ts_rank(inverse(ts_delta(close, 5)), 20)",
    ],
    "volume": [
        "rank(log(add(volume, 1)))",
        "ts_rank(volume, 20)",
        "rank(divide(volume, ts_rank(volume, 20)))",
    ],
    "volatility": [
        "rank(subtract(high, low))",
        "ts_rank(subtract(high, low), 20)",
        "rank(divide(subtract(high, low), close))",
    ],
    "price_volume": [
        "rank(multiply(ts_delta(close, 5), log(add(volume, 1))))",
        "rank(divide(ts_delta(close, 5), log(add(volume, 1))))",
        "ts_rank(multiply(close, volume), 20)",
    ],
    "intraday": [
        "rank(divide(subtract(close, open), open))",
        "rank(divide(subtract(high, low), open))",
        "rank(divide(subtract(close, low), subtract(high, low)))",
    ],
}


def classify_idea(text: str) -> List[str]:
    """
    将自然语言 idea 粗略映射到 alpha factor families。

    这是一个本地 rule-based LLM placeholder。
    后面真正接 OpenAI API 时，可以让 LLM 输出：
        {"families": [...], "constraints": {...}}
    """
    t = text.lower()
    families = []

    if any(w in t for w in ["momentum", "trend", "uptrend", "price increase", "涨", "趋势", "动量"]):
        families.append("momentum")

    if any(w in t for w in ["reversal", "mean reversion", "反转", "均值回归"]):
        families.append("reversal")

    if any(w in t for w in ["volume", "liquidity", "turnover", "成交量", "流动性"]):
        families.append("volume")

    if any(w in t for w in ["volatility", "range", "spread", "波动", "振幅"]):
        families.append("volatility")

    if any(w in t for w in ["price volume", "volume confirms", "量价", "放量"]):
        families.append("price_volume")

    if any(w in t for w in ["intraday", "open close", "日内", "开盘", "收盘"]):
        families.append("intraday")

    # fallback：没有识别时，从 momentum + volume 开始
    if not families:
        families = ["momentum", "volume"]

    return families


def idea_to_candidate_alphas(idea: str) -> List[str]:
    """
    idea -> candidate alpha strings。
    先由 family templates 生成候选，再交给 parser/validator。
    """
    families = classify_idea(idea)
    candidates = []

    for fam in families:
        candidates.extend(IDEA_TEMPLATES.get(fam, []))

    # 去重但保持顺序
    seen = set()
    out = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def call_openai_for_alpha_candidates(idea: str, n: int = 8, model: str = "gpt-5.5") -> List[str]:
    """
    使用 OpenAI API 从自然语言 idea 生成 alpha DSL 候选。

    使用前：
        pip install openai
        $env:OPENAI_API_KEY="你的 key"     # PowerShell

    设计原则：
        - LLM 只负责提出候选表达式；
        - 本地 parser / validator / scorer 负责最终把关；
        - 没有 API key 或调用失败时，自动 fallback 到本地模板。
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return []

    try:
        from openai import OpenAI
    except ImportError:
        print("OpenAI package not installed. Run: pip install openai")
        return []

    client = OpenAI(api_key=api_key)

    schema = {
        "name": "alpha_candidates",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "alphas": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": n,
                    "items": {"type": "string"},
                }
            },
            "required": ["alphas"],
        },
        "strict": True,
    }

    system_prompt = """
You generate candidate WorldQuant Brain / Fast Expression Language alpha expressions.
Return only JSON matching the schema.
Use only these fields:
open, close, high, low, volume, vwap, returns.
Use only these operators:
abs, rank, subtract, multiply, add, divide, log, inverse, ts_delta, ts_rank.
Prefer interpretable alphas with rank, ts_rank, ts_delta, log(add(volume, 1)).
Avoid unsafe expressions such as log(-1), divide(-1, close), inverse(close).
Do not explain. Do not include markdown.
""".strip()

    user_prompt = f"""
Idea: {idea}
Generate {n} candidate alpha expressions.
Examples of valid syntax:
rank(ts_delta(close, 5))
rank(divide(subtract(close, open), open))
ts_rank(ts_delta(close, 5), 20)
rank(log(add(volume, 1)))
""".strip()

    try:
        response = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": schema["name"],
                    "schema": schema["schema"],
                    "strict": True,
                }
            },
        )

        data = json.loads(response.output_text)
        return data.get("alphas", [])

    except Exception as e:
        print("OpenAI API alpha generation failed; falling back to local templates.")
        print("Reason:", e)
        return []


def structured_alpha_from_idea(idea: str, ops: Dict[str, OperatorSpec], n: int = 5, use_api: bool = True) -> List[str]:
    """
    自然语言 idea -> 合法 alpha DSL。

    Pipeline:
        idea
        -> classify factor family
        -> template candidates
        -> parse_alpha
        -> validate
        -> semantic filter
        -> alpha string
    """
    results = []

    raw_candidates = []

    # 1. API candidates first
    if use_api:
        raw_candidates.extend(call_openai_for_alpha_candidates(idea, n=max(n, 8)))

    # 2. Local template fallback / augmentation
    raw_candidates.extend(idea_to_candidate_alphas(idea))

    for raw in raw_candidates:
        try:
            node = parse_alpha(raw)
            validate(node, ops)
            if is_semantically_valid(node):
                results.append(to_dsl(node))
        except Exception:
            continue

        if len(results) >= n:
            break

    # 如果模板不够，就用 random generator 补足
    while len(results) < n:
        alpha = generate_valid_alpha(ops, max_depth=3)
        if alpha not in results:
            results.append(alpha)

    return results


def explain_alpha(alpha: str) -> str:
    """
    给 alpha 一个简单解释。
    这也是 LLM 接口层以后可以替换/增强的位置。
    """
    if "ts_delta(close" in alpha:
        return "momentum-like: measures recent price change."
    if "inverse(ts_delta" in alpha:
        return "reversal-like: bets against recent price movement."
    if "volume" in alpha:
        return "volume/liquidity-like: uses trading activity as signal."
    if "high" in alpha and "low" in alpha:
        return "volatility/range-like: uses intraday price range."
    if "subtract(close, open)" in alpha:
        return "intraday return-like: compares close against open."
    return "generic transformed price/volume signal."


# =========================
# Data Connector：yfinance / 平台数据入口
# =========================

def load_market_data_csv(path: str = "market_data.csv") -> "pd.DataFrame":
    """
    从本地 CSV 读取市场数据。

    Required columns:
        open, close, high, low, volume

    Optional columns:
        vwap, returns, date/datetime/timestamp/time
    """
    _require_pandas_numpy()

    data = pd.read_csv(path)

    for time_col in ["date", "datetime", "timestamp", "time"]:
        if time_col in data.columns:
            data[time_col] = pd.to_datetime(data[time_col])
            data = data.sort_values(time_col).set_index(time_col)
            break

    data.columns = [c.lower() for c in data.columns]

    if "vwap" not in data.columns:
        data["vwap"] = (data["high"] + data["low"] + data["close"]) / 3.0

    if "returns" not in data.columns:
        data["returns"] = data["close"].pct_change()

    return data


def download_yfinance_data(
    ticker: str = "AAPL",
    period: str = "1y",
    interval: str = "1d",
    out_path: str = "market_data.csv",
) -> "pd.DataFrame":
    """
    使用 yfinance 下载单资产 OHLCV 数据，并保存为 market_data.csv。

    安装：
        pip install yfinance pandas numpy

    示例：
        data = download_yfinance_data("AAPL", period="2y", interval="1d")
        data = download_yfinance_data("NVDA", period="60d", interval="5m")

    注意：
        - yfinance 的分钟级数据历史长度有限；
        - interval 可选：1m, 2m, 5m, 15m, 30m, 60m, 1d 等。
        - 新版 yfinance 有时返回 MultiIndex columns，本函数已兼容。
    """
    _require_pandas_numpy()

    try:
        import yfinance as yf
    except ImportError:
        raise ImportError("yfinance not installed. Run: pip install yfinance")

    raw = yf.download(
        tickers=ticker,
        period=period,
        interval=interval,
        auto_adjust=False,
        progress=False,
        group_by="column",
    )

    if raw.empty:
        raise ValueError(f"No data downloaded for ticker={ticker}, period={period}, interval={interval}")

    # yfinance 有时返回 MultiIndex columns，例如 ('High', 'AAPL')
    if isinstance(raw.columns, pd.MultiIndex):
        # 单 ticker 情况下，取 price level
        raw.columns = [str(col[0]).lower().replace(" ", "_") for col in raw.columns]
    else:
        raw.columns = [str(c).lower().replace(" ", "_") for c in raw.columns]

    raw = raw.reset_index()
    raw.columns = [str(c).lower().replace(" ", "_") for c in raw.columns]

    # Normalize datetime column name
    if "date" in raw.columns:
        raw = raw.rename(columns={"date": "datetime"})
    elif raw.columns[0] not in {"open", "high", "low", "close"}:
        raw = raw.rename(columns={raw.columns[0]: "datetime"})

    required = ["open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in raw.columns]
    if missing:
        raise ValueError(
            f"Downloaded data missing columns {missing}. Actual columns: {list(raw.columns)}"
        )

    keep_cols = ["datetime"] + required if "datetime" in raw.columns else required
    data = raw[keep_cols].copy()

    data["vwap"] = (data["high"] + data["low"] + data["close"]) / 3.0
    data["returns"] = data["close"].pct_change()
    data["ticker"] = ticker

    data.to_csv(out_path, index=False)
    return load_market_data_csv(out_path)


def load_platform_data(path: str = "platform_data.csv", out_path: str = "market_data.csv") -> "pd.DataFrame":
    """
    平台数据适配器占位函数。

    你以后如果从 WorldQuant / Brain / 自己爬取的平台导出数据，
    只需要把列名统一成：
        datetime, open, high, low, close, volume, vwap, returns

    然后保存成 market_data.csv，后面的 backtest scorer 不需要改。
    """
    _require_pandas_numpy()

    data = load_market_data_csv(path)
    data.reset_index().to_csv(out_path, index=False)
    return data


def download_yfinance_multi_data(
    tickers: List[str],
    period: str = "1y",
    interval: str = "1d",
    out_path: str = "multi_market_data.csv",
) -> "pd.DataFrame":
    """
    下载多资产 OHLCV 数据，并整理成长表格式：
        datetime, ticker, open, high, low, close, volume, vwap, returns

    这是横截面回测需要的数据格式。
    """
    _require_pandas_numpy()

    try:
        import yfinance as yf
    except ImportError:
        raise ImportError("yfinance not installed. Run: pip install yfinance")

    raw = yf.download(
        tickers=tickers,
        period=period,
        interval=interval,
        auto_adjust=False,
        progress=False,
        group_by="ticker",
    )

    if raw.empty:
        raise ValueError(f"No data downloaded for tickers={tickers}")

    frames = []

    # 多 ticker 通常是 MultiIndex columns: (ticker, field)
    if isinstance(raw.columns, pd.MultiIndex):
        for ticker in tickers:
            if ticker not in raw.columns.get_level_values(0):
                continue
            df = raw[ticker].copy().reset_index()
            df.columns = [str(c).lower().replace(" ", "_") for c in df.columns]
            if "date" in df.columns:
                df = df.rename(columns={"date": "datetime"})
            elif df.columns[0] not in {"open", "high", "low", "close"}:
                df = df.rename(columns={df.columns[0]: "datetime"})
            df["ticker"] = ticker
            frames.append(df)
    else:
        # 单 ticker fallback
        df = raw.copy().reset_index()
        df.columns = [str(c).lower().replace(" ", "_") for c in df.columns]
        if "date" in df.columns:
            df = df.rename(columns={"date": "datetime"})
        elif df.columns[0] not in {"open", "high", "low", "close"}:
            df = df.rename(columns={df.columns[0]: "datetime"})
        df["ticker"] = tickers[0]
        frames.append(df)

    data = pd.concat(frames, ignore_index=True)
    data.columns = [c.lower() for c in data.columns]

    required = ["datetime", "ticker", "open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in data.columns]
    if missing:
        raise ValueError(f"Multi data missing columns {missing}. Actual columns: {list(data.columns)}")

    data = data[required].copy()
    data["vwap"] = (data["high"] + data["low"] + data["close"]) / 3.0
    data = data.sort_values(["ticker", "datetime"])
    data["returns"] = data.groupby("ticker")["close"].pct_change()

    data.to_csv(out_path, index=False)
    return data


def load_multi_market_data_csv(path: str = "multi_market_data.csv") -> "pd.DataFrame":
    """
    读取横截面回测数据。
    Required columns:
        datetime, ticker, open, high, low, close, volume
    Optional:
        vwap, returns
    """
    _require_pandas_numpy()
    data = pd.read_csv(path)
    data.columns = [c.lower() for c in data.columns]
    data["datetime"] = pd.to_datetime(data["datetime"])

    if "vwap" not in data.columns:
        data["vwap"] = (data["high"] + data["low"] + data["close"]) / 3.0

    data = data.sort_values(["ticker", "datetime"])

    if "returns" not in data.columns:
        data["returns"] = data.groupby("ticker")["close"].pct_change()

    return data


# =========================
# Backtest Scorer：真实数据回测评分器
# =========================

try:
    import pandas as pd
    import numpy as np
except ImportError:
    pd = None
    np = None


@dataclass
class BacktestScore:
    alpha: str
    sharpe: float
    turnover: float
    max_drawdown: float
    ic: float
    rank_ic: float
    mean_return: float
    volatility: float
    n_obs: int


def _require_pandas_numpy():
    if pd is None or np is None:
        raise ImportError("Backtest requires pandas and numpy. Run: pip install pandas numpy")


def eval_node_series(node: Node, data: "pd.DataFrame") -> "pd.Series":
    """
    在单资产时间序列 DataFrame 上计算 alpha 表达式。

    data columns 至少包含：
        open, close, high, low, volume, vwap, returns

    注意：这是 local research evaluator，和 WorldQuant Brain 的实现可能不完全一致。
    """
    _require_pandas_numpy()

    if len(node.args) == 0:
        if node.op in data.columns:
            return data[node.op].astype(float)
        if is_number(node.op):
            return pd.Series(float(node.op), index=data.index)
        raise ValueError(f"Unknown terminal in evaluator: {node.op}")

    op = node.op
    args = [eval_node_series(arg, data) for arg in node.args]

    if op == "abs":
        return args[0].abs()

    if op == "log":
        return np.log(args[0].where(args[0] > 0))

    if op == "inverse":
        return 1.0 / args[0].replace(0, np.nan)

    if op == "add":
        out = args[0] + args[1]
        return out

    if op == "subtract":
        out = args[0] - args[1]
        return out

    if op == "multiply":
        out = args[0] * args[1]
        return out

    if op == "divide":
        return args[0] / args[1].replace(0, np.nan)

    if op == "rank":
        # 单资产时间序列里没有 cross-sectional rank；这里退化为 rolling percentile rank
        window = int(float(node.args[1].op)) if len(node.args) >= 2 and len(node.args[1].args) == 0 and is_number(node.args[1].op) else 20
        return args[0].rolling(window).rank(pct=True)

    if op == "ts_delta":
        window = int(float(node.args[1].op))
        return args[0].diff(window)

    if op == "ts_rank":
        window = int(float(node.args[1].op))
        return args[0].rolling(window).rank(pct=True)

    raise ValueError(f"Evaluator does not support operator: {op}")


def compute_returns(data: "pd.DataFrame") -> "pd.Series":
    """
    计算下一期收益，用于检验 alpha 的预测力。
    """
    _require_pandas_numpy()
    if "returns" in data.columns:
        return data["returns"].astype(float).shift(-1)
    return data["close"].astype(float).pct_change().shift(-1)


def max_drawdown(equity: "pd.Series") -> float:
    _require_pandas_numpy()
    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    return float(drawdown.min())


def backtest_alpha(alpha: str, data: "pd.DataFrame") -> BacktestScore:
    """
    对单个 alpha 做一个 minimal long/short backtest。

    简化规则：
        signal = alpha expression
        position = zscore(signal).clip(-1, 1)
        strategy_return = position.shift(1) * next_return

    输出：
        Sharpe, turnover, max_drawdown, IC, rank IC 等。
    """
    _require_pandas_numpy()

    node = parse_alpha(alpha)
    signal = eval_node_series(node, data)
    fwd_ret = compute_returns(data)

    # z-score 标准化 signal
    mu = signal.rolling(60, min_periods=20).mean()
    sigma = signal.rolling(60, min_periods=20).std()
    z = ((signal - mu) / sigma.replace(0, np.nan)).clip(-1, 1)

    strat_ret = z.shift(1) * fwd_ret
    strat_ret = strat_ret.replace([np.inf, -np.inf], np.nan).dropna()

    aligned_signal = signal.loc[strat_ret.index].replace([np.inf, -np.inf], np.nan)
    aligned_ret = fwd_ret.loc[strat_ret.index].replace([np.inf, -np.inf], np.nan)
    valid = aligned_signal.notna() & aligned_ret.notna()

    if len(strat_ret) < 20 or valid.sum() < 20:
        return BacktestScore(alpha, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, int(len(strat_ret)))

    mean_ret = float(strat_ret.mean())
    vol = float(strat_ret.std())
    sharpe = float(np.sqrt(252) * mean_ret / vol) if vol > 0 else 0.0

    pos = z.loc[strat_ret.index].fillna(0)
    turnover = float(pos.diff().abs().mean())

    equity = (1.0 + strat_ret).cumprod()
    mdd = max_drawdown(equity)

    ic = float(aligned_signal[valid].corr(aligned_ret[valid]))
    rank_ic = float(aligned_signal[valid].rank().corr(aligned_ret[valid].rank()))

    return BacktestScore(
        alpha=alpha,
        sharpe=round(sharpe, 4),
        turnover=round(turnover, 4),
        max_drawdown=round(mdd, 4),
        ic=round(ic, 4) if not np.isnan(ic) else 0.0,
        rank_ic=round(rank_ic, 4) if not np.isnan(rank_ic) else 0.0,
        mean_return=round(mean_ret, 6),
        volatility=round(vol, 6),
        n_obs=int(len(strat_ret)),
    )


def backtest_many_alphas(alphas: List[str], data: "pd.DataFrame") -> List[BacktestScore]:
    """
    批量回测并按 Sharpe + RankIC 排序。
    """
    scores = []
    for alpha in alphas:
        try:
            scores.append(backtest_alpha(alpha, data))
        except Exception as e:
            print("Backtest failed:", alpha)
            print("Reason:", e)

    return sorted(scores, key=lambda s: (s.sharpe, s.rank_ic), reverse=True)


def export_backtest_scores_csv(scores: List[BacktestScore], path: str = "alpha_backtest_scores.csv", top_k: int = 50) -> str:
    _require_pandas_numpy()
    out_path = Path(path)
    rows = []
    for i, s in enumerate(scores[:top_k], start=1):
        rows.append({
            "rank": i,
            "alpha": s.alpha,
            "sharpe": s.sharpe,
            "turnover": s.turnover,
            "max_drawdown": s.max_drawdown,
            "ic": s.ic,
            "rank_ic": s.rank_ic,
            "mean_return": s.mean_return,
            "volatility": s.volatility,
            "n_obs": s.n_obs,
        })
    pd.DataFrame(rows).to_csv(out_path, index=False)
    return str(out_path.resolve())


def print_backtest_scores(scores: List[BacktestScore], top_k: int = 10):
    for s in scores[:top_k]:
        print(f"  sharpe={s.sharpe:.4f} rank_ic={s.rank_ic:.4f} ic={s.ic:.4f} turnover={s.turnover:.4f} mdd={s.max_drawdown:.4f}")
        print(f"    alpha: {s.alpha}")


def _field_matrix(data: "pd.DataFrame", field: str) -> "pd.DataFrame":
    """long data -> date x ticker matrix"""
    return data.pivot(index="datetime", columns="ticker", values=field).sort_index()


def eval_node_cross_sectional(node: Node, matrices: Dict[str, "pd.DataFrame"]) -> "pd.DataFrame":
    """
    横截面 evaluator。

    语义：
    - field: 返回 date x ticker matrix
    - rank(x): 每个日期横截面 rank
    - ts_delta(x, d): 每个 ticker 时间方向 diff(d)
    - ts_rank(x, d): 每个 ticker rolling rank
    """
    _require_pandas_numpy()

    if len(node.args) == 0:
        if node.op in matrices:
            return matrices[node.op]
        if is_number(node.op):
            template = next(iter(matrices.values()))
            return pd.DataFrame(float(node.op), index=template.index, columns=template.columns)
        raise ValueError(f"Unknown terminal in cross-sectional evaluator: {node.op}")

    op = node.op
    args = [eval_node_cross_sectional(arg, matrices) for arg in node.args]

    if op == "abs":
        return args[0].abs()
    if op == "log":
        return np.log(args[0].where(args[0] > 0))
    if op == "inverse":
        return 1.0 / args[0].replace(0, np.nan)
    if op == "add":
        return args[0] + args[1]
    if op == "subtract":
        return args[0] - args[1]
    if op == "multiply":
        return args[0] * args[1]
    if op == "divide":
        return args[0] / args[1].replace(0, np.nan)
    if op == "rank":
        return args[0].rank(axis=1, pct=True)
    if op == "ts_delta":
        window = int(float(node.args[1].op))
        return args[0].diff(window)
    if op == "ts_rank":
        window = int(float(node.args[1].op))
        return args[0].rolling(window).rank(pct=True)

    raise ValueError(f"Cross-sectional evaluator does not support operator: {op}")


def backtest_alpha_cross_sectional(alpha: str, data: "pd.DataFrame") -> BacktestScore:
    """
    多资产横截面 long-short 回测。

    每日：
    - 计算 alpha(date, ticker)
    - 横截面 demean
    - gross exposure 标准化到 1
    - 下一期收益加权求组合收益
    """
    _require_pandas_numpy()

    node = parse_alpha(alpha)

    fields = ["open", "high", "low", "close", "volume", "vwap", "returns"]
    matrices = {f: _field_matrix(data, f) for f in fields if f in data.columns}

    signal = eval_node_cross_sectional(node, matrices).replace([np.inf, -np.inf], np.nan)
    fwd_ret = matrices["returns"].shift(-1)

    # 横截面标准化：demean + gross exposure normalize
    signal = signal.sub(signal.mean(axis=1), axis=0)
    gross = signal.abs().sum(axis=1).replace(0, np.nan)
    weights = signal.div(gross, axis=0)

    pnl = (weights.shift(1) * fwd_ret).sum(axis=1).replace([np.inf, -np.inf], np.nan).dropna()

    if len(pnl) < 20:
        return BacktestScore(alpha, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, int(len(pnl)))

    mean_ret = float(pnl.mean())
    vol = float(pnl.std())
    sharpe = float(np.sqrt(252) * mean_ret / vol) if vol > 0 else 0.0

    turnover = float(weights.diff().abs().sum(axis=1).mean())
    equity = (1.0 + pnl).cumprod()
    mdd = max_drawdown(equity)

    # IC / RankIC: 每日横截面 corr，然后取均值
    common_idx = signal.index.intersection(fwd_ret.index)
    daily_ic = []
    daily_rank_ic = []
    for dt in common_idx:
        x = signal.loc[dt]
        y = fwd_ret.loc[dt]
        valid = x.notna() & y.notna()
        if valid.sum() >= 3:
            daily_ic.append(x[valid].corr(y[valid]))
            daily_rank_ic.append(x[valid].rank().corr(y[valid].rank()))

    ic = float(pd.Series(daily_ic).mean()) if daily_ic else 0.0
    rank_ic = float(pd.Series(daily_rank_ic).mean()) if daily_rank_ic else 0.0

    return BacktestScore(
        alpha=alpha,
        sharpe=round(sharpe, 4),
        turnover=round(turnover, 4),
        max_drawdown=round(mdd, 4),
        ic=round(ic, 4) if not np.isnan(ic) else 0.0,
        rank_ic=round(rank_ic, 4) if not np.isnan(rank_ic) else 0.0,
        mean_return=round(mean_ret, 6),
        volatility=round(vol, 6),
        n_obs=int(len(pnl)),
    )


def backtest_many_alphas_cross_sectional(alphas: List[str], data: "pd.DataFrame") -> List[BacktestScore]:
    scores = []
    for alpha in alphas:
        try:
            scores.append(backtest_alpha_cross_sectional(alpha, data))
        except Exception as e:
            print("Cross-sectional backtest failed:", alpha)
            print("Reason:", e)
    return sorted(scores, key=lambda s: (s.sharpe, s.rank_ic), reverse=True)


@dataclass
class ValidationScore:
    alpha: str
    train_sharpe: float
    test_sharpe: float
    train_rank_ic: float
    test_rank_ic: float
    train_ic: float
    test_ic: float
    test_turnover: float
    test_max_drawdown: float
    stability: float
    passed: bool


def split_train_test_by_date(data: "pd.DataFrame", train_frac: float = 0.7):
    """
    按日期切分 train/test，避免未来信息泄露。
    """
    _require_pandas_numpy()
    dates = sorted(data["datetime"].dropna().unique())
    if len(dates) < 60:
        raise ValueError("Not enough dates for train/test split")

    cut = int(len(dates) * train_frac)
    train_dates = set(dates[:cut])
    test_dates = set(dates[cut:])

    train = data[data["datetime"].isin(train_dates)].copy()
    test = data[data["datetime"].isin(test_dates)].copy()
    return train, test


def validate_alpha_train_test(alpha: str, data: "pd.DataFrame", train_frac: float = 0.7) -> ValidationScore:
    """
    固定 train/test 验证。

    目标：检查 alpha 是否只在样本内有效。
    """
    train, test = split_train_test_by_date(data, train_frac=train_frac)
    train_score = backtest_alpha_cross_sectional(alpha, train)
    test_score = backtest_alpha_cross_sectional(alpha, test)

    stability = 0.0
    if abs(train_score.sharpe) > 1e-8:
        stability = test_score.sharpe / abs(train_score.sharpe)

    passed = (
        test_score.sharpe > 0
        and test_score.rank_ic > 0
        and stability > 0.25
    )

    return ValidationScore(
        alpha=alpha,
        train_sharpe=train_score.sharpe,
        test_sharpe=test_score.sharpe,
        train_rank_ic=train_score.rank_ic,
        test_rank_ic=test_score.rank_ic,
        train_ic=train_score.ic,
        test_ic=test_score.ic,
        test_turnover=test_score.turnover,
        test_max_drawdown=test_score.max_drawdown,
        stability=round(stability, 4),
        passed=passed,
    )


def validate_many_train_test(alphas: List[str], data: "pd.DataFrame", train_frac: float = 0.7) -> List[ValidationScore]:
    out = []
    for alpha in alphas:
        try:
            out.append(validate_alpha_train_test(alpha, data, train_frac=train_frac))
        except Exception as e:
            print("Train/test validation failed:", alpha)
            print("Reason:", e)
    return sorted(out, key=lambda s: (s.passed, s.test_sharpe, s.test_rank_ic), reverse=True)


def print_validation_scores(scores: List[ValidationScore], top_k: int = 10):
    for s in scores[:top_k]:
        flag = "PASS" if s.passed else "FAIL"
        print(
            f"  {flag} train_sharpe={s.train_sharpe:.4f} test_sharpe={s.test_sharpe:.4f} "
            f"train_rank_ic={s.train_rank_ic:.4f} test_rank_ic={s.test_rank_ic:.4f} stability={s.stability:.4f}"
        )
        print(f"    alpha: {s.alpha}")


def export_validation_scores_csv(scores: List[ValidationScore], path: str = "alpha_train_test_validation.csv", top_k: int = 50) -> str:
    _require_pandas_numpy()
    out_path = Path(path)
    rows = []
    for i, s in enumerate(scores[:top_k], start=1):
        rows.append({
            "rank": i,
            "alpha": s.alpha,
            "passed": s.passed,
            "train_sharpe": s.train_sharpe,
            "test_sharpe": s.test_sharpe,
            "train_rank_ic": s.train_rank_ic,
            "test_rank_ic": s.test_rank_ic,
            "train_ic": s.train_ic,
            "test_ic": s.test_ic,
            "test_turnover": s.test_turnover,
            "test_max_drawdown": s.test_max_drawdown,
            "stability": s.stability,
        })
    pd.DataFrame(rows).to_csv(out_path, index=False)
    return str(out_path.resolve())


@dataclass
class WalkForwardScore:
    alpha: str
    mean_test_sharpe: float
    median_test_sharpe: float
    mean_test_rank_ic: float
    positive_sharpe_rate: float
    positive_rank_ic_rate: float
    n_windows: int
    passed: bool


def walk_forward_validate_alpha(
    alpha: str,
    data: "pd.DataFrame",
    train_window: int = 126,
    test_window: int = 21,
    step: int = 21,
) -> WalkForwardScore:
    """
    Walk-forward validation。

    每个窗口：
        train period 用于模拟研究/选择期；
        test period 用于 out-of-sample 检验。

    这里 alpha 本身不重新拟合参数，但仍然可以检验时间稳定性。
    """
    _require_pandas_numpy()
    dates = sorted(data["datetime"].dropna().unique())
    test_scores = []

    start = 0
    while start + train_window + test_window <= len(dates):
        train_dates = set(dates[start:start + train_window])
        test_dates = set(dates[start + train_window:start + train_window + test_window])

        # train_data 暂时不用于拟合，但保留结构，方便以后做参数选择
        _ = data[data["datetime"].isin(train_dates)].copy()
        test_data = data[data["datetime"].isin(test_dates)].copy()

        try:
            s = backtest_alpha_cross_sectional(alpha, test_data)
            if s.n_obs > 5:
                test_scores.append(s)
        except Exception:
            pass

        start += step

    if not test_scores:
        return WalkForwardScore(alpha, 0.0, 0.0, 0.0, 0.0, 0.0, 0, False)

    sharpes = pd.Series([s.sharpe for s in test_scores])
    rank_ics = pd.Series([s.rank_ic for s in test_scores])

    positive_sharpe_rate = float((sharpes > 0).mean())
    positive_rank_ic_rate = float((rank_ics > 0).mean())
    mean_test_sharpe = float(sharpes.mean())
    median_test_sharpe = float(sharpes.median())
    mean_test_rank_ic = float(rank_ics.mean())

    passed = (
        mean_test_sharpe > 0
        and mean_test_rank_ic > 0
        and positive_sharpe_rate >= 0.55
        and positive_rank_ic_rate >= 0.55
    )

    return WalkForwardScore(
        alpha=alpha,
        mean_test_sharpe=round(mean_test_sharpe, 4),
        median_test_sharpe=round(median_test_sharpe, 4),
        mean_test_rank_ic=round(mean_test_rank_ic, 4),
        positive_sharpe_rate=round(positive_sharpe_rate, 4),
        positive_rank_ic_rate=round(positive_rank_ic_rate, 4),
        n_windows=len(test_scores),
        passed=passed,
    )


def walk_forward_validate_many(
    alphas: List[str],
    data: "pd.DataFrame",
    train_window: int = 126,
    test_window: int = 21,
    step: int = 21,
) -> List[WalkForwardScore]:
    out = []
    for alpha in alphas:
        try:
            out.append(walk_forward_validate_alpha(alpha, data, train_window, test_window, step))
        except Exception as e:
            print("Walk-forward validation failed:", alpha)
            print("Reason:", e)
    return sorted(out, key=lambda s: (s.passed, s.mean_test_sharpe, s.mean_test_rank_ic), reverse=True)


def print_walk_forward_scores(scores: List[WalkForwardScore], top_k: int = 10):
    for s in scores[:top_k]:
        flag = "PASS" if s.passed else "FAIL"
        print(
            f"  {flag} mean_sharpe={s.mean_test_sharpe:.4f} median_sharpe={s.median_test_sharpe:.4f} "
            f"mean_rank_ic={s.mean_test_rank_ic:.4f} pos_sharpe_rate={s.positive_sharpe_rate:.2f} "
            f"pos_rank_ic_rate={s.positive_rank_ic_rate:.2f} windows={s.n_windows}"
        )
        print(f"    alpha: {s.alpha}")


def export_walk_forward_scores_csv(scores: List[WalkForwardScore], path: str = "alpha_walk_forward_validation.csv", top_k: int = 50) -> str:
    _require_pandas_numpy()
    out_path = Path(path)
    rows = []
    for i, s in enumerate(scores[:top_k], start=1):
        rows.append({
            "rank": i,
            "alpha": s.alpha,
            "passed": s.passed,
            "mean_test_sharpe": s.mean_test_sharpe,
            "median_test_sharpe": s.median_test_sharpe,
            "mean_test_rank_ic": s.mean_test_rank_ic,
            "positive_sharpe_rate": s.positive_sharpe_rate,
            "positive_rank_ic_rate": s.positive_rank_ic_rate,
            "n_windows": s.n_windows,
        })
    pd.DataFrame(rows).to_csv(out_path, index=False)
    return str(out_path.resolve())


# =========================
# Alpha Scorer：结构评分器
# =========================

@dataclass
class AlphaScore:
    alpha: str
    complexity: int
    interpretability: float
    risk: float
    readiness: float
    total: float
    notes: str = ""


RISKY_PATTERNS = [
    "divide(",      # 除法可能带来分母接近 0 风险
    "inverse(",     # 反函数可能放大异常值
    "log(",         # log 需要正输入
]

GOOD_PATTERNS = [
    "rank(",
    "ts_rank(",
    "ts_delta(",
    "log(add(volume, 1))",
]


def score_alpha(alpha: str, ops: Dict[str, OperatorSpec]) -> AlphaScore:
    """
    对 alpha 做静态结构评分。

    注意：这是 expression-level scorer，不使用真实市场数据。
    后面可以接 backtest scorer：Sharpe, turnover, drawdown, fitness 等。
    """
    node = parse_alpha(alpha)
    validate(node, ops)

    complexity = count_ops(node)

    # complexity score: 太简单不好，太复杂也不好
    if complexity < 2:
        complexity_score = 0.2
    elif 2 <= complexity <= 5:
        complexity_score = 1.0
    elif 6 <= complexity <= 8:
        complexity_score = 0.7
    else:
        complexity_score = 0.4

    # interpretability: 简单、含 rank/ts_rank/ts_delta 的表达式更容易解释
    good_hits = sum(1 for p in GOOD_PATTERNS if p in alpha)
    interpretability = min(1.0, 0.4 + 0.2 * good_hits + 0.1 * max(0, 5 - complexity))

    # risk: divide / inverse / unsafe log 会增加结构风险
    risky_hits = sum(alpha.count(p) for p in RISKY_PATTERNS)
    risk = min(1.0, 0.15 * risky_hits)

    # semantic safety
    if not is_semantically_valid(node):
        risk = min(1.0, risk + 0.5)

    # readiness: 越稳定、越可解释、复杂度适中越高
    readiness = max(0.0, min(1.0, 0.5 * complexity_score + 0.4 * interpretability - 0.3 * risk))

    # total: 综合分
    total = max(0.0, min(1.0, 0.45 * readiness + 0.35 * interpretability + 0.20 * complexity_score - 0.25 * risk))

    notes = []
    if complexity < 2:
        notes.append("too simple")
    if complexity > 8:
        notes.append("too complex")
    if "divide(" in alpha:
        notes.append("check denominator stability")
    if "inverse(" in alpha:
        notes.append("may amplify outliers")
    if "log(" in alpha:
        notes.append("check log input positivity")
    if not notes:
        notes.append("structurally clean")

    return AlphaScore(
        alpha=alpha,
        complexity=complexity,
        interpretability=round(interpretability, 3),
        risk=round(risk, 3),
        readiness=round(readiness, 3),
        total=round(total, 3),
        notes="; ".join(notes),
    )


def rank_alphas(alphas: List[str], ops: Dict[str, OperatorSpec], min_score: float = 0.0) -> List[AlphaScore]:
    """
    给一组 alpha 打分并按 total 从高到低排序。
    min_score 可用于过滤低质量 alpha。
    """
    scored = []
    seen = set()

    for alpha in alphas:
        if alpha in seen:
            continue
        seen.add(alpha)

        try:
            s = score_alpha(alpha, ops)
            if s.total >= min_score:
                scored.append(s)
        except Exception:
            continue

    return sorted(scored, key=lambda x: x.total, reverse=True)


def export_alpha_scores_csv(scores: List[AlphaScore], path: str = "alpha_candidates.csv", top_k: int = 20) -> str:
    """
    将 top alpha 候选保存为 CSV，方便上传/记录实验。
    """
    out_path = Path(path)

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "rank",
            "alpha",
            "total",
            "readiness",
            "risk",
            "complexity",
            "interpretability",
            "notes",
        ])

        for i, s in enumerate(scores[:top_k], start=1):
            writer.writerow([
                i,
                s.alpha,
                s.total,
                s.readiness,
                s.risk,
                s.complexity,
                s.interpretability,
                s.notes,
            ])

    return str(out_path.resolve())


def print_alpha_scores(scores: List[AlphaScore], top_k: int = 10):
    """
    简单打印评分结果。
    """
    for s in scores[:top_k]:
        print(f"  score={s.total:.3f} readiness={s.readiness:.3f} risk={s.risk:.3f} complexity={s.complexity}")
        print(f"    alpha: {s.alpha}")
        print(f"    notes: {s.notes}")


# =========================
# 示例：构造 alpha
# =========================

# rank((close - open) / open)
def example_alpha_1():
    return Node("rank", [
        Node("divide", [
            Node("subtract", [
                Node("close", []),
                Node("open", [])
            ]),
            Node("open", [])
        ])
    ])


# rank(log(volume + 1))
def example_alpha_2():
    return Node("rank", [
        Node("log", [
            Node("add", [
                Node("volume", []),
                Node("1", [])
            ])
        ])
    ])


# =========================
# 主程序测试
# =========================

if __name__ == "__main__":
    ops = load_operators()

    print(f"Loaded operators: {len(ops)}")

    alpha_strings = [
        "rank(divide(subtract(close, open), open))",
        "rank(log(add(volume, 1)))",
        "ts_rank(log(abs(low)), 60)",
    ]

    print()
    print("String alpha examples:")
    print("DEBUG alpha count:", len(alpha_strings))

    for raw in alpha_strings:
        try:
            node = parse_alpha(raw)
            validate(node, ops)
            rebuilt = to_dsl(node)
            print("  VALID:", rebuilt)
        except Exception as e:
            print("  FAILED:", raw)
            print("    reason:", e)

    print("\nRandom generated alpha examples:")

    random.seed(42)
    generated = generate_many_alphas(ops, n=10, max_depth=3)

    for alpha in generated:
        print("  ", alpha)

    print()
    print("LLM-style idea -> structured alpha examples:")

    idea = "momentum with volume confirmation"
    print("Idea:", idea)

    idea_alphas = structured_alpha_from_idea(idea, ops, n=5, use_api=True)

    for alpha in idea_alphas:
        print("  ", alpha)
        print("     explanation:", explain_alpha(alpha))

    print()
    print("Scored alpha candidates:")

    all_candidates = idea_alphas + generated
    scores = rank_alphas(all_candidates, ops, min_score=0.80)
    print_alpha_scores(scores, top_k=10)

    csv_path = export_alpha_scores_csv(scores, path="alpha_candidates.csv", top_k=20)
    print()
    print("Exported CSV:", csv_path)

    # =========================
    # Optional: real-data backtest
    # =========================
    market_data_path = Path("market_data.csv")

    # 如果没有 market_data.csv，自动尝试用 yfinance 下载一个默认样例
    if pd is not None and not market_data_path.exists():
        try:
            print()
            print("market_data.csv not found. Trying to download sample data from yfinance: AAPL, 1y, 1d")
            download_yfinance_data(ticker="AAPL", period="1y", interval="1d", out_path="market_data.csv")
            market_data_path = Path("market_data.csv")
        except Exception as e:
            print()
            print("Could not download yfinance data automatically.")
            print("Reason:", e)

    if pd is not None and market_data_path.exists():
        print()
        print("Real-data backtest:")

        data = load_market_data_csv(str(market_data_path))

        backtest_alphas = [s.alpha for s in scores[:20]]
        bt_scores = backtest_many_alphas(backtest_alphas, data)
        print_backtest_scores(bt_scores, top_k=10)

        bt_csv = export_backtest_scores_csv(bt_scores, path="alpha_backtest_scores.csv", top_k=20)
        print()
        print("Exported backtest CSV:", bt_csv)
    else:
        print()
        print("Backtest skipped: put a market_data.csv file in this folder to enable real-data scoring.")
        print("Required columns: open, close, high, low, volume, vwap. Optional: returns, date/datetime/timestamp/time.")

    # =========================
    # Optional: multi-asset cross-sectional backtest
    # =========================
    multi_data_path = Path("multi_market_data.csv")

    if pd is not None and not multi_data_path.exists():
        try:
            print()
            print("multi_market_data.csv not found. Trying to download multi-asset sample data from yfinance.")
            sample_tickers = ["AAPL", "MSFT", "NVDA", "TSLA", "GOOGL", "AMZN", "META", "JPM", "XOM", "UNH"]
            download_yfinance_multi_data(sample_tickers, period="1y", interval="1d", out_path="multi_market_data.csv")
            multi_data_path = Path("multi_market_data.csv")
        except Exception as e:
            print()
            print("Could not download multi-asset yfinance data automatically.")
            print("Reason:", e)

    if pd is not None and multi_data_path.exists():
        print()
        print("Multi-asset cross-sectional backtest:")

        multi_data = load_multi_market_data_csv(str(multi_data_path))
        cs_alphas = [s.alpha for s in scores[:20]]
        cs_scores = backtest_many_alphas_cross_sectional(cs_alphas, multi_data)
        print_backtest_scores(cs_scores, top_k=10)

        cs_csv = export_backtest_scores_csv(cs_scores, path="multi_alpha_backtest_scores.csv", top_k=20)
        print()
        print("Exported multi-asset backtest CSV:", cs_csv)

        print()
        print("Train/test validation:")
        validation_alphas = [s.alpha for s in cs_scores[:20]]
        val_scores = validate_many_train_test(validation_alphas, multi_data, train_frac=0.7)
        print_validation_scores(val_scores, top_k=10)
        val_csv = export_validation_scores_csv(val_scores, path="alpha_train_test_validation.csv", top_k=20)
        print()
        print("Exported train/test validation CSV:", val_csv)

        print()
        print("Walk-forward validation:")
        wf_scores = walk_forward_validate_many(
            validation_alphas,
            multi_data,
            train_window=126,
            test_window=21,
            step=21,
        )
        print_walk_forward_scores(wf_scores, top_k=10)
        wf_csv = export_walk_forward_scores_csv(wf_scores, path="alpha_walk_forward_validation.csv", top_k=20)
        print()
        print("Exported walk-forward validation CSV:", wf_csv)
    else:
        print()
        print("Multi-asset backtest skipped: put multi_market_data.csv in this folder to enable cross-sectional scoring.")
        print("Required columns: datetime, ticker, open, high, low, close, volume. Optional: vwap, returns.")


"""
下一步（你真正要做的🔥）：

1. 把 scrape 出来的 operator 自动解析为：
   - min_arity
   - max_arity
   （而不是写死）

2. 加 DSL parser（字符串 -> AST） ✅ 已完成

3. 加 random alpha generator（但要 respect arity）

4. 最终目标：
   直觉 -> AST -> DSL -> Brain 可提交 alpha
"""
