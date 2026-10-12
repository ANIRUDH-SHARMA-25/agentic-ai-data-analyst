"""Conservative Plotly recommendations from actual result labels and values."""

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html import escape
from typing import Any, Literal

import plotly.graph_objects as go


@dataclass
class ChartRecommendation:
    kind: Literal["bar", "line"] | None = None
    figure: go.Figure | None = None
    reason: str = ""
    excluded_rows: int = 0


def _numeric(value: Any) -> tuple[bool, int | float | None]:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return True, None
    if isinstance(value, bool):
        return False, None
    if isinstance(value, int):
        return (True, value) if abs(value) <= 2**53 - 1 else (False, None)
    if isinstance(value, float):
        return True, value
    if isinstance(value, str) and re.fullmatch(r"[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", value):
        try:
            exact = Decimal(value)
            number = float(exact)
            # Refuse decimals that would visibly lose source precision in JS.
            if math.isfinite(number) and Decimal(str(number)) == exact and abs(number) <= 2**53 - 1:
                return True, number
        except (InvalidOperation, OverflowError):
            pass
    return False, None


def _date(value: str) -> datetime | None:
    if not re.fullmatch(r"\d{4}-\d{2}(?:-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?)?)?", value):
        return None
    try:
        parsed = datetime.fromisoformat(value + "-01" if len(value) == 7 else value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def build_chart(columns: list[str], rows: list[list[Any]]) -> ChartRecommendation:
    """Chart exactly two unambiguous dimensions; never aggregate or invent data."""
    if not rows:
        return ChartRecommendation(reason="No rows were returned to visualize.")
    if len(columns) != 2 or len(set(columns)) != 2 or any(len(row) != 2 for row in rows):
        return ChartRecommendation(reason="Automatic charts need exactly one label column and one numeric measure.")
    candidates = []
    for index in range(2):
        converted = [_numeric(row[index]) for row in rows]
        if all(valid for valid, number in converted) and any(number is not None for valid, number in converted):
            candidates.append((index, [number for valid, number in converted]))
    if len(candidates) != 1:
        return ChartRecommendation(reason="The table does not have an unambiguous numeric measure suitable for a chart.")
    number_index, numbers = candidates[0]
    label_index = 1 - number_index
    labels = [row[label_index] for row in rows]
    if any(label is not None and (not isinstance(label, str) or not label.strip() or len(label) > 80) for label in labels):
        return ChartRecommendation(reason="The result labels are unsuitable for an automatic chart.")
    pairs = [(label, number) for label, number in zip(labels, numbers) if label is not None]
    if len(pairs) < 2 or sum(number is not None for label, number in pairs) < 2:
        return ChartRecommendation(reason="A chart needs at least two valid data points.")
    if len({label for label, number in pairs}) != len(pairs):
        return ChartRecommendation(reason="Repeated labels need an explicit backend aggregation before charting.")
    parsed = [_date(label) for label, number in pairs]
    label_name, number_name = escape(columns[label_index]), escape(columns[number_index])
    excluded = len(rows) - len(pairs)
    if all(value is not None for value in parsed):
        if len(pairs) > 100 or len(set(parsed)) != len(parsed):
            return ChartRecommendation(reason="The time series is too large or has duplicate timestamps.")
        ordered = sorted(zip(parsed, pairs), key=lambda item: item[0])
        figure = go.Figure(go.Scatter(
            x=[date for date, pair in ordered], y=[pair[1] for date, pair in ordered],
            mode="lines+markers", connectgaps=False, line={"color": "#2563eb", "width": 3},
            hovertemplate=f"{label_name}: %{{x}}<br>{number_name}: %{{y}}<extra></extra>",
        ))
        kind = "line"
    else:
        # Mixed valid/invalid date-like values would imply a misleading time axis.
        if any(value is not None for value in parsed) or any(re.match(r"^\d{4}-\d{2}(?:-|$)", label) for label, number in pairs):
            return ChartRecommendation(reason="Mixed date labels cannot be charted reliably.")
        complete = [(label, number) for label, number in pairs if number is not None]
        excluded += len(pairs) - len(complete)
        if len(complete) > 20:
            return ChartRecommendation(reason="More than 20 categories would overcrowd this chart; use a narrower query.")
        figure = go.Figure(go.Bar(
            x=[escape(label) for label, number in complete], y=[number for label, number in complete],
            marker_color="#2563eb", hovertemplate="%{x}<br>%{y}<extra></extra>",
        ))
        figure.update_yaxes(rangemode="tozero")
        kind = "bar"
    figure.update_layout(
        title=f"{number_name} by {label_name}", xaxis_title=label_name, yaxis_title=number_name,
        template="plotly_white", height=380, margin={"l": 20, "r": 20, "t": 55, "b": 30},
        showlegend=False,
    )
    return ChartRecommendation(kind=kind, figure=figure, excluded_rows=excluded)
