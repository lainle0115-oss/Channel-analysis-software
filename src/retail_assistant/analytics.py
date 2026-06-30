from __future__ import annotations

import pandas as pd


def _with_purchase_column(data: pd.DataFrame) -> pd.DataFrame:
    if "purchase_qty" in data:
        return data
    result = data.copy()
    result["purchase_qty"] = 0
    return result


def latest_inventory_rows(data: pd.DataFrame) -> pd.DataFrame:
    """Return each channel/SKU's latest available inventory snapshot rows."""
    if data.empty:
        return data.copy()
    inventory_data = data.copy()
    if "data_type" in inventory_data:
        inventory_data = inventory_data[~inventory_data["data_type"].eq("采购")].copy()
    if inventory_data.empty:
        return data.iloc[0:0].copy()
    latest_dates = inventory_data.groupby(["channel", "sku_id"])["date"].transform("max")
    return inventory_data[inventory_data["date"] == latest_dates].copy()


def calculate_kpis(data: pd.DataFrame) -> dict[str, float | int]:
    data = _with_purchase_column(data)
    if data.empty:
        return {
            "sales_amount": 0.0, "sales_qty": 0.0, "purchase_qty": 0.0, "sku_count": 0,
            "channel_count": 0, "city_count": 0, "latest_stock": 0.0,
        }
    latest = latest_inventory_rows(data)
    return {
        "sales_amount": float(data["sales_amount"].sum()),
        "sales_qty": float(data["sales_qty"].sum()),
        "purchase_qty": float(data.get("purchase_qty", pd.Series(dtype=float)).sum()),
        "sku_count": int(data["sku_id"].nunique()),
        "channel_count": int(data["channel"].nunique()),
        "city_count": int(data.loc[data["city"] != "全部区域", "city"].nunique()),
        "latest_stock": float(latest["stock_qty"].sum()),
    }


def daily_metrics(data: pd.DataFrame) -> pd.DataFrame:
    data = _with_purchase_column(data)
    return (
        data.groupby(["date", "channel"], as_index=False)
        .agg(sales_qty=("sales_qty", "sum"), sales_amount=("sales_amount", "sum"), purchase_qty=("purchase_qty", "sum"))
        .sort_values(["date", "channel"])
    )


def channel_summary(data: pd.DataFrame) -> pd.DataFrame:
    data = _with_purchase_column(data)
    if data.empty:
        return pd.DataFrame()
    totals = (
        data.groupby("channel", as_index=False)
        .agg(
            sales_qty=("sales_qty", "sum"),
            sales_amount=("sales_amount", "sum"),
            purchase_qty=("purchase_qty", "sum"),
            sku_count=("sku_id", "nunique"),
            city_count=("city", "nunique"),
        )
    )
    latest = (
        latest_inventory_rows(data)
        .groupby("channel", as_index=False)["stock_qty"]
        .sum()
        .rename(columns={"stock_qty": "latest_stock"})
    )
    result = totals.merge(latest, on="channel", how="left").fillna({"latest_stock": 0})
    total_qty = max(result["sales_qty"].sum(), 1)
    result["qty_share"] = result["sales_qty"] / total_qty
    return result.sort_values("sales_qty", ascending=False)


def sku_summary(data: pd.DataFrame) -> pd.DataFrame:
    data = _with_purchase_column(data)
    if data.empty:
        return pd.DataFrame(columns=[
            "channel", "sku_id", "sku_name", "sales_qty", "sales_amount", "purchase_qty",
            "active_days", "city_count", "latest_stock",
        ])
    totals = (
        data.groupby(["channel", "sku_id", "sku_name"], as_index=False)
        .agg(
            sales_qty=("sales_qty", "sum"),
            sales_amount=("sales_amount", "sum"),
            purchase_qty=("purchase_qty", "sum"),
            active_days=("date", "nunique"),
            city_count=("city", "nunique"),
        )
    )
    latest = (
        latest_inventory_rows(data)
        .groupby(["channel", "sku_id"], as_index=False)["stock_qty"]
        .sum()
        .rename(columns={"stock_qty": "latest_stock"})
    )
    return totals.merge(latest, on=["channel", "sku_id"], how="left").fillna({"latest_stock": 0})


def detect_anomalies(data: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "channel", "sku_id", "sku_name", "sales_qty", "avg_sales_qty",
        "stock_qty", "sales_change", "issue", "action",
    ]
    if data.empty:
        return pd.DataFrame(columns=columns)
    operational = data.copy()
    if "data_type" in operational:
        operational = operational[~operational["data_type"].eq("采购")].copy()
    if operational.empty:
        return pd.DataFrame(columns=columns)

    daily = (
        operational.groupby(["date", "channel", "sku_id", "sku_name"], as_index=False)
        .agg(sales_qty=("sales_qty", "sum"), stock_qty=("stock_qty", "sum"))
    )
    latest_date = daily["date"].max()
    latest = daily[daily["date"] == latest_date].copy()
    baseline = (
        daily[daily["date"] < latest_date]
        .groupby(["channel", "sku_id"])["sales_qty"]
        .mean()
        .rename("avg_sales_qty")
        .reset_index()
    )
    latest = latest.merge(baseline, on=["channel", "sku_id"], how="left")
    latest["avg_sales_qty"] = latest["avg_sales_qty"].fillna(latest["sales_qty"])
    denominator = latest["avg_sales_qty"].astype(float).where(latest["avg_sales_qty"] != 0)
    latest["sales_change"] = ((latest["sales_qty"] - latest["avg_sales_qty"]) / denominator).fillna(0.0)

    issues: list[dict[str, object]] = []
    for row in latest.itertuples(index=False):
        issue = action = None
        if row.stock_qty <= 0 and row.sales_qty > 0:
            issue, action = "缺货风险", "立即确认渠道库存并安排补货"
        elif row.stock_qty < max(row.sales_qty * 2, 5):
            issue, action = "库存覆盖不足", "复核未来3天销量并制定补货计划"
        elif row.sales_change <= -0.3:
            issue, action = "销量异常下降", "检查价格、活动、上架状态和竞品变化"
        elif row.sales_change >= 0.5:
            issue, action = "销量异常增长", "确认增长原因并检查库存承接能力"
        if issue:
            issues.append({**row._asdict(), "issue": issue, "action": action})
    return pd.DataFrame(issues, columns=columns)


def generate_management_summary(data: pd.DataFrame, anomalies: pd.DataFrame) -> str:
    data = _with_purchase_column(data)
    kpis = calculate_kpis(data)
    if data.empty:
        return "当前没有可分析的数据。"
    channels = channel_summary(data)
    if kpis["sales_qty"] <= 0 and kpis["purchase_qty"] > 0:
        return (
            f"当前仅检测到采购数据，覆盖 {kpis['channel_count']} 个渠道、{kpis['sku_count']} 个 SKU，"
            f"采购数量 {kpis['purchase_qty']:,.0f} 件。"
            "请上传对应销售数据后，再查看销量、销售额、库存异常和采销比。"
        )
    leading = channels.iloc[0]
    amount_channels = data.groupby("channel")["sales_amount"].apply(lambda values: values.abs().sum() > 0)
    amount_label = "销售额" if amount_channels.all() else "已提供渠道销售额"
    amount_text = f"{amount_label} ¥{kpis['sales_amount']:,.0f}、" if kpis["sales_amount"] > 0 else ""
    purchase_text = (
        f"采购数量 {kpis['purchase_qty']:,.0f} 件，采销比 {kpis['purchase_qty'] / kpis['sales_qty']:.1%}。"
        if kpis["sales_qty"] > 0 and kpis["purchase_qty"] > 0
        else (f"采购数量 {kpis['purchase_qty']:,.0f} 件。" if kpis["purchase_qty"] > 0 else "")
    )
    return (
        f"本期覆盖 {kpis['channel_count']} 个渠道、{kpis['sku_count']} 个 SKU，"
        f"{amount_text}销量 {kpis['sales_qty']:,.0f} 件。"
        f"{purchase_text}"
        f"{leading['channel']} 销量最高，占比 {leading['qty_share']:.1%}。"
        f"最新库存 {kpis['latest_stock']:,.0f} 件，识别出 {len(anomalies)} 条需跟进异常。"
    )
