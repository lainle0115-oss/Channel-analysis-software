from __future__ import annotations

import sys
import types

if sys.platform == "darwin" and "_scproxy" not in sys.modules:
    scproxy = types.ModuleType("_scproxy")
    scproxy._get_proxy_settings = lambda: {}
    scproxy._get_proxies = lambda: {}
    sys.modules["_scproxy"] = scproxy

import altair as alt
import pandas as pd


CHART_COLORS = ["#4338A8", "#6558C7", "#8A7FDB", "#20A884", "#D69A3A", "#A6A0D8", "#6F7180", "#B8796A"]
DIMENSION_LABELS = {"channel": "渠道", "source_file": "来源文件", "sku_name": "商品", "city": "城市/区域"}
METRIC_LABELS = {"sales_qty": "销量", "sales_amount": "销售额", "purchase_qty": "采购数量", "stock_qty": "库存"}


def choose_available_metric(frame: pd.DataFrame, preferred: str) -> tuple[str, str | None]:
    candidates = [preferred] + [
        column for column in ("sales_qty", "sales_amount", "purchase_qty", "stock_qty") if column != preferred
    ]
    for metric in candidates:
        if metric in frame and pd.to_numeric(frame[metric], errors="coerce").fillna(0).abs().sum() > 0:
            if metric == preferred:
                return metric, None
            return metric, f"当前数据没有有效{METRIC_LABELS[preferred]}，已自动改为展示{METRIC_LABELS[metric]}。"
    return preferred, f"当前筛选范围内{METRIC_LABELS[preferred]}均为 0，图表仍展示已识别的分类与日期。"


def trend_chart(frame: pd.DataFrame, dimension: str, metric: str, height: int = 320) -> alt.Chart | None:
    if frame.empty or dimension not in frame or metric not in frame:
        return None
    label = DIMENSION_LABELS[dimension]
    metric_label = METRIC_LABELS[metric]
    chart_data = (
        frame.dropna(subset=["date"])
        .groupby(["date", dimension], as_index=False)[metric]
        .sum()
        .rename(columns={dimension: label, metric: metric_label})
    )
    if chart_data.empty:
        return None

    numeric_metric = pd.to_numeric(chart_data[metric_label], errors="coerce").fillna(0)
    domain_min = min(0.0, float(numeric_metric.min()) * 1.1)
    domain_max = max(1.0, float(numeric_metric.max()) * 1.1)
    selection = alt.selection_point(fields=[label], bind="legend")
    legend = (
        alt.Legend(
            orient="bottom",
            title=None,
            columns=1,
            labelLimit=520,
            symbolLimit=80,
            labelFontSize=12,
            rowPadding=8,
            symbolSize=120,
        )
        if dimension == "sku_name"
        else alt.Legend(
            orient="top",
            title=None,
            labelLimit=260,
            columns=4,
            symbolLimit=40,
        )
    )
    encoding = {
        "y": alt.Y(f"{metric_label}:Q", title=metric_label, stack=None, scale=alt.Scale(domain=[domain_min, domain_max])),
        "color": alt.Color(
            f"{label}:N",
            scale=alt.Scale(range=CHART_COLORS),
            legend=legend,
        ),
        "opacity": alt.condition(selection, alt.value(1), alt.value(0.16)),
        "tooltip": [
            alt.Tooltip("date:T", title="日期", format="%Y-%m-%d"),
            alt.Tooltip(f"{label}:N", title=label),
            alt.Tooltip(f"{metric_label}:Q", title=metric_label, format=",.0f"),
        ],
    }
    if chart_data["date"].nunique() < 4:
        chart = alt.Chart(chart_data).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
            x=alt.X(
                "yearmonthdate(date):O",
                title=None,
                axis=alt.Axis(format="%m-%d", labelAngle=0, labelLimit=100),
                scale=alt.Scale(paddingInner=0.34, paddingOuter=0.16),
            ),
            xOffset=alt.XOffset(
                f"{label}:N",
                scale=alt.Scale(paddingInner=0.16, paddingOuter=0.08),
            ),
            **encoding,
        )
    else:
        chart = alt.Chart(chart_data).mark_line(point=alt.OverlayMarkDef(size=45), strokeWidth=2.2).encode(
            x=alt.X("date:T", title=None, axis=alt.Axis(format="%m-%d", labelAngle=0)),
            **encoding,
        )
    return chart.add_params(selection).properties(height=height)


def horizontal_bar_chart(frame: pd.DataFrame, category: str, metric: str, height: int = 300) -> alt.Chart | None:
    if frame.empty or category not in frame or metric not in frame:
        return None
    clean = frame[[category, metric]].copy()
    clean[category] = clean[category].fillna("").astype(str).str.strip()
    clean.loc[clean[category] == "", category] = f"未识别{DIMENSION_LABELS.get(category, '分类')}"
    clean[metric] = pd.to_numeric(clean[metric], errors="coerce").fillna(0)
    chart_data = (
        clean.groupby(category, as_index=False, dropna=False)[metric]
        .sum()
        .sort_values(metric, ascending=False)
        .head(12)
    )
    if chart_data.empty:
        return None
    category_label = DIMENSION_LABELS.get(category, "分类")
    metric_label = METRIC_LABELS.get(metric, "数值")
    return (
        alt.Chart(chart_data)
        .mark_bar(color="#6558C7", opacity=1)
        .encode(
            x=alt.X(f"{metric}:Q", title=metric_label),
            y=alt.Y(
                f"{category}:N",
                sort="-x",
                title=None,
                axis=alt.Axis(labelLimit=300, labelPadding=8),
            ),
            tooltip=[
                alt.Tooltip(f"{category}:N", title=category_label),
                alt.Tooltip(f"{metric}:Q", title=metric_label, format=",.0f"),
            ],
        )
        .properties(height=height, padding={"left": 8, "right": 18, "top": 4, "bottom": 4})
    )
