"""Pure parsing and aggregation of agent run output for the evaluation set.
It extracts the tool rounds, calls, tool time and token counts that Aider prints, and aggregates per-task results
into success rate and averages, so runs of different models or prompts can be compared by numbers.
Missing values stay None instead of zero, so a run that printed nothing is not mistaken for a cheap one.
"""

import re
from dataclasses import asdict, dataclass
from typing import Any, Optional

TOOLS_LINE = re.compile(r"Native tools: (\d+) round\(s\), (\d+) call\(s\), ([\d.]+)s")
TOKENS_LINE = re.compile(r"Tokens: ([\d.]+)(k?) sent, ([\d.]+)(k?) received")
TOOL_ERROR = re.compile(r"^  -> Error: ", re.MULTILINE)
THOUSAND = 1000
THOUSAND_SUFFIX = "k"


@dataclass(frozen=True)
class RunMetrics:
    rounds: Optional[int]
    calls: Optional[int]
    tool_seconds: Optional[float]
    tokens_sent: Optional[int]
    tokens_received: Optional[int]
    tool_errors: int


@dataclass(frozen=True)
class TaskResult:
    task: str
    passed: bool
    seconds: float
    metrics: RunMetrics

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def token_count(number: str, suffix: str) -> int:
    return round(float(number) * (THOUSAND if suffix == THOUSAND_SUFFIX else 1))


def parse_metrics(output: str) -> RunMetrics:
    """Totals over every 'Native tools' line; tokens from the last 'Tokens' line (Aider prints running totals)."""
    tools = TOOLS_LINE.findall(output)
    tokens = TOKENS_LINE.findall(output)
    sent = received = None
    if tokens:
        number_sent, sent_suffix, number_received, received_suffix = tokens[-1]
        sent, received = token_count(number_sent, sent_suffix), token_count(number_received, received_suffix)
    return RunMetrics(
        rounds=sum(int(t[0]) for t in tools) if tools else None,
        calls=sum(int(t[1]) for t in tools) if tools else None,
        tool_seconds=sum(float(t[2]) for t in tools) if tools else None,
        tokens_sent=sent,
        tokens_received=received,
        tool_errors=len(TOOL_ERROR.findall(output)),
    )


def mean(values: list[Optional[float]]) -> Optional[float]:
    known = [v for v in values if v is not None]
    return sum(known) / len(known) if known else None


def summarize(results: list[TaskResult]) -> dict[str, Any]:
    """Success rate and per-run averages over `results`."""
    return {
        "tasks": len(results),
        "passed": sum(r.passed for r in results),
        "success_rate": (sum(r.passed for r in results) / len(results)) if results else None,
        "mean_seconds": mean([r.seconds for r in results]),
        "mean_rounds": mean([r.metrics.rounds for r in results]),
        "mean_calls": mean([r.metrics.calls for r in results]),
        "mean_tokens_sent": mean([r.metrics.tokens_sent for r in results]),
        "tool_errors": sum(r.metrics.tool_errors for r in results),
    }
