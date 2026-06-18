from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

import pandas as pd


CANONICAL_COLUMNS = [
    "date",
    "channel",
    "source_file",
    "data_type",
    "sku_id",
    "sku_name",
    "city",
    "store",
    "sales_qty",
    "sales_amount",
    "purchase_qty",
    "stock_qty",
]

REQUIRED_FIELDS = ("date",)
MAPPABLE_FIELDS = (
    "date",
    "sku_id",
    "sku_name",
    "city",
    "store",
    "sales_qty",
    "sales_amount",
    "purchase_qty",
    "stock_qty",
)

FIELD_LABELS = {
    "date": "日期",
    "sku_id": "SKU 编码",
    "sku_name": "商品名称",
    "city": "城市/区域",
    "store": "门店/仓库",
    "sales_qty": "销量/数量",
    "sales_amount": "销售额/金额",
    "purchase_qty": "采购数量",
    "stock_qty": "库存",
}

COLUMN_ALIASES = {
    "date": [
        "date", "日期", "销售日期", "交易日期", "业务日期", "业务时间", "统计日期",
        "下单时间", "完成时间", "账单生成时间", "约定到货日期", "要求到货日期", "采购日期", "day",
    ],
    "channel": ["channel", "渠道", "平台", "渠道名称"],
    "sku_id": [
        "sku_id", "sku编码", "商品编码", "商品id", "前端商品编码", "后端商品编码",
        "货品id", "sku id", "货号", "商品69码", "商品条码", "sku",
    ],
    "sku_name": ["sku_name", "sku名称", "商品名称", "品名", "商品", "货品名称"],
    "city": ["city", "城市", "区域", "子公司名称", "仓库所在城市", "公司名称"],
    "store": ["store", "门店", "经营店名称", "仓库", "物理仓", "入库机构部门"],
    "sales_qty": [
        "sales_qty", "销量", "销售数量", "销售件数", "商品销售量", "商品数量",
        "结算数量", "qty",
    ],
    "sales_amount": [
        "sales_amount", "销售额", "销售金额", "商品销售额", "含税金额", "结算金额",
        "单据结算金额", "计划金额", "应付金额", "gmv", "amount",
    ],
    "purchase_qty": [
        "purchase_qty", "采购数量", "采购件数", "确认数量", "送货数量", "实收数量",
        "可供数量", "箱数", "订购数量", "下单数量", "采购量",
    ],
    "stock_qty": [
        "stock_qty", "库存", "库存数量", "可售库存", "库存总数", "在库库存",
        "补货可用在库库存", "前置站点库存数量", "大仓库存数量", "stock",
    ],
}

FIELD_KEYWORDS = {
    "date": ("日期", "时间", "date", "day"),
    "sku_id": ("sku", "商品编码", "商品id", "货品id", "货号", "商品条码", "69码"),
    "sku_name": ("商品名称", "sku名称", "品名", "货品名称"),
    "city": ("城市", "区域", "子公司"),
    "store": ("门店", "经营店", "仓库", "物理仓"),
    "sales_qty": ("销量", "销售数量", "销售量", "商品数量", "结算数量"),
    "sales_amount": ("销售额", "销售金额", "含税金额", "结算金额", "成交金额", "gmv", "金额"),
    "purchase_qty": ("采购数量", "采购件数", "确认数量", "送货数量", "实收数量", "可供数量", "箱数", "采购量"),
    "stock_qty": ("库存总数", "可售库存", "在库库存", "站点库存", "大仓库存", "库存数量", "剩余库存", "库存"),
}

KNOWN_CHANNELS = ("盒马", "小象", "叮咚", "朴朴", "奥乐齐", "美团", "京东", "天猫", "抖音")
MEASURE_LABEL_HINTS = ("库存", "数量", "销量", "销售额", "金额", "件数", "斤数", "满足率", "准时率", "坏损率")
XIAOXIANG_STOCK_COMPONENTS = (
    "大仓库存数量",
    "前置站点库存数量",
    "供应商到大仓在途数量",
    "大仓到门店在途数量",
)
PLACEHOLDER_VALUES = {"", "--", "-", "—", "nan", "none", "null", "无", "n/a", "na"}


def _clean_label(value: object) -> str:
    return (
        str(value)
        .strip()
        .lower()
        .replace("\n", "")
        .replace(" ", "")
        .replace("_", "")
        .replace("-", "")
    )


def _clean_match_value(value: object) -> str:
    return _clean_label(value)


def _meaningful_ratio(raw: pd.DataFrame, column: object | None) -> float:
    if column is None or column not in raw.columns or raw.empty:
        return 0.0
    values = raw[column].dropna().astype(str).map(_clean_match_value)
    if values.empty:
        return 0.0
    meaningful = values[~values.isin(PLACEHOLDER_VALUES)]
    return float(len(meaningful) / len(values))


def _sku_column_priority(column: object) -> int:
    label = _clean_label(column)
    priorities = (
        ("商品编码", 120),
        ("货品id", 115),
        ("商品id", 105),
        ("前端商品编码", 100),
        ("后端商品编码", 100),
        ("skuid", 90),
        ("sku编码", 85),
        ("商品条码", 70),
        ("69码", 65),
        ("sku", 55),
    )
    return next((score for keyword, score in priorities if keyword in label), 0)


def infer_mapping(columns: pd.Index) -> dict[str, object | None]:
    cleaned = {_clean_label(column): column for column in columns}
    mapping: dict[str, object | None] = {}
    used: set[object] = set()
    for field in MAPPABLE_FIELDS:
        match = next(
            (
                cleaned[_clean_label(alias)]
                for alias in COLUMN_ALIASES[field]
                if _clean_label(alias) in cleaned and cleaned[_clean_label(alias)] not in used
            ),
            None,
        )
        if match is None:
            scored = [
                (
                    (
                        0
                        if field in {"city", "store"}
                        and any(hint in _clean_label(column) for hint in MEASURE_LABEL_HINTS)
                        else sum(keyword in _clean_label(column) for keyword in FIELD_KEYWORDS[field])
                    ),
                    column,
                )
                for column in columns
                if column not in used
            ]
            score, candidate = max(scored, key=lambda item: item[0], default=(0, None))
            match = candidate if score > 0 else None
        mapping[field] = match
        if match is not None:
            used.add(match)
    return mapping


def refine_mapping(raw: pd.DataFrame, mapping: dict[str, object | None] | None = None) -> dict[str, object | None]:
    refined = dict(mapping or infer_mapping(raw.columns))
    current_sku = refined.get("sku_id")
    current_quality = _meaningful_ratio(raw, current_sku)
    if current_quality < 0.5:
        used = {value for field, value in refined.items() if field != "sku_id" and value is not None}
        candidates: list[tuple[float, int, object]] = []
        for column in raw.columns:
            if column in used:
                continue
            label = _clean_label(column)
            looks_like_sku = (
                any(keyword in label for keyword in FIELD_KEYWORDS["sku_id"])
                or any(_clean_label(alias) == label for alias in COLUMN_ALIASES["sku_id"])
            )
            if not looks_like_sku:
                continue
            quality = _meaningful_ratio(raw, column)
            if quality <= 0:
                continue
            candidates.append((quality, _sku_column_priority(column), column))
        if candidates:
            _, _, best_column = max(candidates, key=lambda item: (item[0], item[1]))
            refined["sku_id"] = best_column

    if infer_data_type(raw) == "采购":
        refined["sales_qty"] = None
        refined["sales_amount"] = None
        refined["stock_qty"] = None
    return refined


def _header_score(columns: pd.Index) -> int:
    mapping = infer_mapping(columns)
    score = sum(value is not None for value in mapping.values())
    if mapping["date"] is not None:
        score += 2
    if mapping["sales_qty"] is not None or mapping["purchase_qty"] is not None:
        score += 2
    return score


def read_sales_file(file: str | Path | BinaryIO) -> pd.DataFrame:
    name = str(getattr(file, "name", file)).lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
        workbook = pd.ExcelFile(file)
        previews = []
        for sheet in workbook.sheet_names:
            for header in range(0, 12):
                try:
                    previews.append((pd.read_excel(workbook, sheet_name=sheet, header=header, nrows=8), sheet, header))
                except (ValueError, IndexError, StopIteration):
                    continue
        if not previews:
            raise ValueError(f"{getattr(file, 'name', file)} 中未找到可读取的 Excel 表头。")
        _, sheet, header = max(previews, key=lambda item: _header_score(item[0].columns))
        return pd.read_excel(workbook, sheet_name=sheet, header=header)

    previews = []
    for header in range(0, 8):
        if hasattr(file, "seek"):
            file.seek(0)
        try:
            previews.append((pd.read_csv(file, header=header, nrows=8), header))
        except pd.errors.ParserError:
            continue
    if not previews:
        raise ValueError(f"{getattr(file, 'name', file)} 中未找到可读取的 CSV 表头。")
    _, header = max(previews, key=lambda item: _header_score(item[0].columns))
    if hasattr(file, "seek"):
        file.seek(0)
    return pd.read_csv(file, header=header)


def infer_channel(raw: pd.DataFrame, fallback: str) -> str:
    labels = {_clean_label(column) for column in raw.columns}
    filename = _clean_label(fallback)
    for channel in KNOWN_CHANNELS:
        if _clean_label(channel) in filename:
            return channel
    if {"业务日期", "经营店名称", "供应商编码"} & labels:
        return "盒马"
    if {"采购单号", "物理仓", "货品id"} <= labels or {"入库机构部门", "物理仓", "货品id"} <= labels:
        return "盒马"
    if {"商品id", "商品合作模式", "前置站点库存数量"} & labels:
        return "小象"
    if {"门店/大仓名称", "skuid", "约定到货日期"} & {_clean_label(column) for column in raw.columns}:
        return "小象"
    for column in raw.columns:
        if _clean_label(column) in {"业态", "渠道"}:
            values = raw[column].dropna().astype(str).head(50).str.cat(sep=" ")
            for channel in KNOWN_CHANNELS:
                if channel in values:
                    return channel
    return fallback


def infer_data_type(raw: pd.DataFrame) -> str:
    labels = {_clean_label(column) for column in raw.columns}
    if any("采购单号" in label or "采购数量" in label or "约定到货日期" in label for label in labels):
        return "采购"
    if any("对账单号" in label or "结算金额" in label or "含税金额" in label for label in labels):
        return "结算"
    if any("库存" in label for label in labels) and any("销售" in label for label in labels):
        return "销售库存"
    if any("库存" in label for label in labels):
        return "库存"
    return "销售"


def profile_file(raw: pd.DataFrame, filename: str) -> dict[str, object]:
    mapping = refine_mapping(raw, infer_mapping(raw.columns))
    missing = [FIELD_LABELS[field] for field in REQUIRED_FIELDS if mapping[field] is None]
    if mapping["sales_qty"] is None and mapping["purchase_qty"] is None and mapping["stock_qty"] is None:
        missing.append("销量、采购数量或库存")
    return {
        "filename": filename,
        "channel": infer_channel(raw, Path(filename).stem),
        "data_type": infer_data_type(raw),
        "rows": len(raw),
        "mapping": mapping,
        "mapped_count": sum(value is not None for value in mapping.values()),
        "missing": missing,
    }


def _parse_dates(values: pd.Series) -> pd.Series:
    text = values.astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
    compact = text.str.fullmatch(r"\d{8}", na=False)
    parsed = pd.to_datetime(text, errors="coerce")
    parsed.loc[compact] = pd.to_datetime(text.loc[compact], format="%Y%m%d", errors="coerce")
    return parsed


def normalize_sales_data(
    raw: pd.DataFrame,
    default_channel: str = "未知渠道",
    mapping: dict[str, object | None] | None = None,
    source_file: str = "",
    data_type: str | None = None,
) -> pd.DataFrame:
    mapping = mapping or refine_mapping(raw, infer_mapping(raw.columns))
    mapped_sources = [source for source in mapping.values() if source is not None]
    if len(mapped_sources) != len(set(mapped_sources)):
        raise ValueError(f"{source_file or default_channel} 存在一个原始字段被映射到多个标准字段，请修正字段映射。")
    rename_map = {source: field for field, source in mapping.items() if source is not None}
    normalized = raw.rename(columns=rename_map).copy()
    missing_required = [field for field in REQUIRED_FIELDS if field not in normalized.columns]
    if missing_required:
        missing_labels = ", ".join(FIELD_LABELS[field] for field in missing_required)
        available = ", ".join(str(column) for column in raw.columns)
        raise ValueError(
            f"{source_file or default_channel} 缺少必要字段: {missing_labels}。"
            f"检测到的原始字段: {available}"
        )
    if "sales_qty" not in normalized.columns and "purchase_qty" not in normalized.columns and "stock_qty" not in normalized.columns:
        available = ", ".join(str(column) for column in raw.columns)
        raise ValueError(
            f"{source_file or default_channel} 缺少销量、采购数量或库存字段。"
            f"检测到的原始字段: {available}"
        )

    warnings: list[str] = []
    inferred_data_type = data_type or infer_data_type(raw)
    is_purchase = inferred_data_type == "采购"
    if "sku_id" not in normalized and "sku_name" not in normalized:
        normalized["sku_id"] = "汇总"
        normalized["sku_name"] = "汇总数据"
        warnings.append(f"{source_file or default_channel} 未提供 SKU 字段，数据按汇总记录处理。")
    elif "sku_id" not in normalized:
        normalized["sku_id"] = normalized["sku_name"].astype(str)
    elif "sku_name" not in normalized:
        normalized["sku_name"] = normalized["sku_id"].astype(str)

    defaults = {
        "channel": default_channel,
        "source_file": source_file or default_channel,
        "data_type": data_type or infer_data_type(raw),
        "city": "全部区域",
        "store": "全部门店",
        "stock_qty": 0,
        "sales_qty": 0,
        "sales_amount": 0,
        "purchase_qty": 0,
    }
    for column, default in defaults.items():
        if column not in normalized:
            normalized[column] = default
    xiaoxiang_stock_components = [column for column in XIAOXIANG_STOCK_COMPONENTS if column in raw.columns]
    if "小象" in default_channel and len(xiaoxiang_stock_components) >= 2:
        normalized["stock_qty"] = (
            raw[xiaoxiang_stock_components]
            .apply(pd.to_numeric, errors="coerce")
            .fillna(0)
            .sum(axis=1)
        )
        warnings.append(
            f"{source_file or default_channel} 小象库存按大仓、前置站点及在途库存合计，并仅在最新日期作为当前库存使用。"
        )
    if is_purchase:
        if mapping.get("purchase_qty") is None and mapping.get("sales_qty") is not None:
            normalized["purchase_qty"] = normalized["sales_qty"]
        normalized["sales_qty"] = 0
        normalized["sales_amount"] = 0
        normalized["stock_qty"] = 0
    if mapping.get("sales_amount") is None and not is_purchase:
        warnings.append(f"{source_file or default_channel} 未提供销售额字段，销售额按 0 展示。")
    if mapping.get("sales_qty") is None and not is_purchase:
        warnings.append(f"{source_file or default_channel} 未提供销量字段，销量按 0 展示并自动使用库存图表。")
    if mapping.get("purchase_qty") is None and is_purchase:
        warnings.append(f"{source_file or default_channel} 未提供采购数量字段，采购数量按 0 展示。")

    normalized = normalized[CANONICAL_COLUMNS]
    normalized["date"] = _parse_dates(normalized["date"])
    for column in ("sales_qty", "sales_amount", "purchase_qty", "stock_qty"):
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce").fillna(0)
    normalized = normalized.dropna(subset=["date"])
    for column in ("channel", "source_file", "data_type", "sku_id", "sku_name", "city", "store"):
        normalized[column] = normalized[column].fillna("").astype(str).str.strip()
    normalized.loc[normalized["city"] == "", "city"] = "全部区域"
    normalized.loc[normalized["store"] == "", "store"] = "全部门店"

    if mapping.get("store") is not None:
        hema_sales = normalized["channel"].str.contains("盒马", na=False) & normalized["data_type"].isin(["销售", "销售库存"])
        non_store_hema = hema_sales & ~normalized["store"].str.contains("店", na=False)
        removed_hema_rows = int(non_store_hema.sum())
        if removed_hema_rows:
            normalized = normalized.loc[~non_store_hema].copy()
            warnings.append(
                f"{source_file or default_channel} 按盒马销售口径仅保留经营店名称含“店”的记录，"
                f"已排除 {removed_hema_rows:,} 条前置仓、FDC 或其他非门店记录。"
            )

    result = (
        normalized.drop_duplicates(keep="last")
        .sort_values(["date", "channel", "sku_id"])
        .reset_index(drop=True)
    )
    result.attrs["warnings"] = warnings
    return result


def combine_sales_files(files: list[dict[str, object]]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    warnings: list[str] = []
    for item in files:
        normalized = normalize_sales_data(
            item["frame"],
            default_channel=str(item["channel"]),
            mapping=item.get("mapping"),
            source_file=str(item.get("source_file", "")),
            data_type=str(item.get("data_type", "")) or None,
        )
        warnings.extend(normalized.attrs.get("warnings", []))
        frames.append(normalized)
    if not frames:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)
    result = pd.concat(frames, ignore_index=True)
    business_columns = [
        "date", "channel", "data_type", "sku_id", "sku_name", "city", "store",
        "sales_qty", "sales_amount", "purchase_qty", "stock_qty",
    ]
    before = len(result)
    result = result.drop_duplicates(subset=business_columns, keep="last").reset_index(drop=True)
    removed = before - len(result)
    if removed:
        warnings.append(f"跨文件识别并移除了 {removed:,} 条重复业务记录，避免重叠周报/月报重复计算。")

    sales_reference = result[
        result["data_type"].isin(["销售", "销售库存", "结算"])
        & ((result["sales_qty"].abs() > 0) | (result["sales_amount"].abs() > 0))
    ].copy()
    purchase_rows = result["data_type"].eq("采购")
    if not sales_reference.empty and purchase_rows.any():
        sales_sku_ids = {
            _clean_match_value(value)
            for value in sales_reference["sku_id"].dropna()
            if _clean_match_value(value) and _clean_match_value(value) != "汇总"
        }
        sales_sku_names = {
            _clean_match_value(value)
            for value in sales_reference["sku_name"].dropna()
            if _clean_match_value(value) and _clean_match_value(value) != "汇总数据"
        }
        purchase_sku_ids = result.loc[purchase_rows, "sku_id"].map(_clean_match_value)
        purchase_sku_names = result.loc[purchase_rows, "sku_name"].map(_clean_match_value)
        matched_purchase = purchase_sku_ids.isin(sales_sku_ids) | purchase_sku_names.isin(sales_sku_names)
        unmatched_index = matched_purchase.index[~matched_purchase]
        if len(unmatched_index):
            excluded_qty = float(result.loc[unmatched_index, "purchase_qty"].sum())
            excluded_skus = result.loc[unmatched_index, "sku_id"].nunique()
            result = result.drop(index=unmatched_index).reset_index(drop=True)
            warnings.append(
                f"采购订单中有 {excluded_skus:,} 个 SKU 未出现在已上传销售数据中，"
                f"已排除 {excluded_qty:,.0f} 件采购量，不纳入采销对比。"
            )
    result.attrs["warnings"] = list(dict.fromkeys(warnings))
    return result
