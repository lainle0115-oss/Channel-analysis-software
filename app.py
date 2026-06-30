from pathlib import Path
import hashlib
import html
import json
import os
import re
import secrets
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))

from retail_assistant.analytics import (  # noqa: E402
    calculate_kpis,
    channel_summary,
    daily_metrics,
    detect_anomalies,
    generate_management_summary,
    latest_inventory_rows,
    sku_summary,
)
from retail_assistant.auth_store import AuthStore, AuthStoreError, AuthUser  # noqa: E402
from retail_assistant.charts import (  # noqa: E402
    choose_available_metric,
    trend_chart,
)
from retail_assistant.normalize import (  # noqa: E402
    combine_normalized_frames,
    normalize_sales_data,
    profile_file,
    read_sales_file,
)
from retail_assistant.reporting import (  # noqa: E402
    REPORT_TYPE_LABELS,
    export_period_report_docx,
    generate_period_report,
    period_report_tables,
    report_period,
)
from retail_assistant.weather import fetch_regional_weather, format_weather_note  # noqa: E402


ROOT = Path(__file__).parent
UPLOAD_STORE = ROOT / ".streamlit" / "uploaded_files"
GUEST_UPLOAD_STORE = ROOT / ".streamlit" / "guest_uploads"
UPLOAD_MANIFEST = UPLOAD_STORE / "manifest.json"
ALLOWED_UPLOAD_SUFFIXES = {".csv", ".xls", ".xlsx"}
DEFAULT_MAX_UPLOAD_BYTES = 200 * 1024 * 1024
try:
    MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", DEFAULT_MAX_UPLOAD_BYTES))
except ValueError:
    MAX_UPLOAD_BYTES = DEFAULT_MAX_UPLOAD_BYTES
UPLOAD_KIND_LABELS = {
    "sales": "销售数据",
    "purchase": "采购数据",
    "auto": "自动识别",
}

st.set_page_config(page_title="零售渠道经营驾驶舱", page_icon="渠", layout="wide")
st.markdown(
    """
    <style>
    :root {
        --ink: #1d1d1f;
        --muted: #6e6e73;
        --canvas: #f5f5f7;
        --panel: #ffffff;
        --line: #e5e5e7;
        --navy: #1d1d1f;
        --teal: #0071e3;
        --teal-dark: #0066cc;
        --teal-soft: #eef6ff;
        --brand-start: #8129e6;
        --brand-mid: #6629f3;
        --brand-end: #3328d8;
        --brand-gradient: linear-gradient(105deg, var(--brand-start) 0%, var(--brand-mid) 50%, var(--brand-end) 100%);
        --brand-glow: rgba(101, 88, 247, .28);
        --pill-bg: rgba(255,255,255,.18);
        --pill-border: rgba(255,255,255,.24);
        --sidebar-pill-bg: rgba(255,255,255,.86);
        --sidebar-pill-border: rgba(111, 88, 247, .26);
        --sidebar-pill-shadow: 0 10px 24px rgba(87, 80, 238, .10), inset 0 1px 0 rgba(255,255,255,.88);
        --sidebar-pill-hover: rgba(111, 88, 247, .10);
        --sidebar-control-height: 3.05rem;
        --button-1-gradient: linear-gradient(115deg, #9f6dff 0%, #6f3cff 44%, #1378ff 100%);
        --button-1-shadow: 0 18px 38px rgba(90, 69, 245, .28), inset 0 1px 0 rgba(255,255,255,.46);
        --amber: #d8911c;
        --red: #c84b4b;
        --blue-soft: #edf5f2;
        --radius: 8px;
        --shadow: 0 1px 3px rgba(23, 50, 77, .05);
    }
    html, body, .stApp {
        background: var(--canvas);
        color: var(--ink);
        font-family: "PingFang SC", "Microsoft YaHei", -apple-system, BlinkMacSystemFont, sans-serif;
    }
    .stApp:before {
        content: "";
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        width: 100vw;
        height: 72px;
        z-index: 99989;
        pointer-events: none;
        background:
            radial-gradient(circle at 4% 0%, rgba(255,255,255,.22) 0, rgba(255,255,255,0) 30%),
            var(--brand-gradient);
        box-shadow: 0 10px 28px rgba(75, 40, 222, .24);
    }
    .block-container {
        padding: 5.45rem 1rem 2.5rem;
        max-width: 1680px;
    }
    section[data-testid="stSidebar"],
    [data-testid="stSidebar"] {
        background-color: #ffffff !important;
        background-image: none !important;
        border-right: 1px solid var(--line);
        min-width: 242px;
        max-width: 242px;
    }
    [data-testid="stSidebarContent"] { padding-top: 4.15rem; }
    [data-testid="stSidebarHeader"] {
        display: none !important;
        height: 0 !important;
        min-height: 0 !important;
        padding: 0 !important;
        margin: 0 !important;
    }
    [data-testid="stSidebar"] * { color: var(--ink); }
    @keyframes sidebarButtonShine {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }
    .sidebar-section-title {
        position: relative;
        display: flex !important;
        align-items: center !important;
        justify-content: flex-start !important;
        min-height: 2.95rem !important;
        width: 100%;
        box-sizing: border-box;
        margin: .08rem 0 .88rem !important;
        padding: .62rem .86rem .62rem 1rem !important;
        border-radius: 18px !important;
        border: 1px solid var(--sidebar-pill-border) !important;
        background:
            radial-gradient(circle at 18% 0%, rgba(255,255,255,.82), transparent 36%),
            linear-gradient(180deg, rgba(255,255,255,.38), rgba(255,255,255,.16)),
            #ffffff !important;
        color: #4f38e8 !important;
        font-size: .92rem !important;
        font-weight: 900;
        letter-spacing: -.01em;
        box-shadow: var(--sidebar-pill-shadow), 0 18px 38px rgba(90, 69, 245, .14) !important;
        overflow: hidden;
    }
    .sidebar-section-title:before {
        content: "";
        width: 4px;
        height: 1.35rem;
        border-radius: 999px;
        margin-right: .62rem;
        background: var(--brand-gradient);
        box-shadow: 0 6px 14px rgba(86, 61, 232, .22);
    }
    .sidebar-section-title:after {
        content: "";
        position: absolute;
        right: .88rem;
        width: .42rem;
        height: .42rem;
        border-radius: 999px;
        background: rgba(79, 56, 232, .18);
        box-shadow: 0 0 0 5px rgba(79, 56, 232, .06);
    }
    .sidebar-section-title span {
        color: #4f38e8 !important;
        font-size: .92rem !important;
        font-weight: 900 !important;
        line-height: 1.1 !important;
    }
    [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 { font-size: .92rem; }
    [data-testid="stSidebar"] .stCaption { font-size: .72rem; line-height: 1.45; }
    .sidebar-top-fill {
        display: none !important;
        position: fixed;
        top: 0;
        left: 0;
        width: 242px;
        height: 72px;
        z-index: 999995;
        pointer-events: none;
        background:
            radial-gradient(circle at 12% 0%, rgba(255,255,255,.28) 0, rgba(255,255,255,0) 34%),
            var(--brand-gradient);
        box-shadow: 0 10px 28px rgba(75, 40, 222, .24);
    }
    [data-testid="stHeader"] {
        display: block !important;
        height: 0 !important;
        min-height: 0 !important;
        background: transparent !important;
        overflow: visible !important;
        pointer-events: none !important;
    }
    [data-testid="stHeader"] > * { pointer-events: none !important; }
    [data-testid="stHeader"] [data-testid="stToolbar"],
    [data-testid="stHeader"] [data-testid="stDecoration"],
    [data-testid="stStatusWidget"],
    [data-testid="stAppDeployButton"],
    [data-testid="stMainMenuButton"] {
        display: none !important;
    }
    [data-testid="stSidebarCollapseButton"],
    [data-testid="stSidebarCollapsedControl"],
    [data-testid="collapsedControl"],
    [data-testid="stExpandSidebarButton"] {
        visibility: visible !important;
        opacity: 1 !important;
        pointer-events: auto !important;
        overflow: visible !important;
        z-index: 100001 !important;
    }
    [data-testid="stSidebar"] [data-testid="stBaseButton-headerNoPadding"],
    [data-testid="stSidebarCollapseButton"] [data-testid="stBaseButton-headerNoPadding"],
    [data-testid="stHeader"] [data-testid="stBaseButton-headerNoPadding"]:not([data-testid="stMainMenuButton"]) {
        display: flex !important;
        visibility: visible !important;
        opacity: 1 !important;
        position: fixed !important;
        left: clamp(12px, 15.6rem, 252px) !important;
        top: 92px !important;
        z-index: 100000 !important;
        width: 40px !important;
        height: 40px !important;
        min-width: 40px !important;
        padding: 0 !important;
        border: 1px solid rgba(229, 229, 231, .88) !important;
        border-radius: 999px !important;
        background: rgba(255, 255, 255, .96) !important;
        color: #1d1d1f !important;
        box-shadow: 0 10px 26px rgba(18, 24, 38, .16), 0 1px 0 rgba(255,255,255,.8) inset !important;
        backdrop-filter: saturate(180%) blur(18px) !important;
        pointer-events: auto !important;
        align-items: center !important;
        justify-content: center !important;
        transition: transform .18s ease, box-shadow .18s ease, left .18s ease !important;
    }
    [data-testid="stSidebarCollapseButton"] [data-testid="stBaseButton-headerNoPadding"]:before,
    [data-testid="stHeader"] [data-testid="stBaseButton-headerNoPadding"]:not([data-testid="stMainMenuButton"]):before {
        content: "‹";
        display: block;
        color: #1d1d1f;
        font-size: 26px;
        line-height: 1;
        font-weight: 600;
        transform: translateY(-1px);
    }
    [data-testid="stSidebarCollapseButton"] [data-testid="stBaseButton-headerNoPadding"] > *,
    [data-testid="stHeader"] [data-testid="stBaseButton-headerNoPadding"]:not([data-testid="stMainMenuButton"]) > *,
    [data-testid="stSidebarCollapsedControl"] button > *,
    [data-testid="collapsedControl"] button > * {
        display: none !important;
    }
    [data-testid="stSidebar"][aria-expanded="false"] [data-testid="stBaseButton-headerNoPadding"] {
        left: 314px !important;
    }
    [data-testid="stSidebar"][aria-expanded="false"] [data-testid="stBaseButton-headerNoPadding"]:before {
        content: "›";
    }
    [data-testid="stSidebarCollapsedControl"] {
        position: fixed !important;
        left: 14px !important;
        top: 92px !important;
        z-index: 100001 !important;
        pointer-events: auto !important;
    }
    [data-testid="stSidebarCollapsedControl"] button,
    [data-testid="collapsedControl"] button,
    [data-testid="stExpandSidebarButton"] {
        display: flex !important;
        visibility: visible !important;
        opacity: 1 !important;
        width: 40px !important;
        height: 40px !important;
        min-width: 40px !important;
        border-radius: 999px !important;
        background: rgba(255,255,255,.96) !important;
        border: 1px solid rgba(229,229,231,.88) !important;
        color: #1d1d1f !important;
        box-shadow: 0 10px 26px rgba(18, 24, 38, .16), 0 1px 0 rgba(255,255,255,.8) inset !important;
        backdrop-filter: saturate(180%) blur(18px) !important;
    }
    [data-testid="stSidebarCollapsedControl"] button:before,
    [data-testid="collapsedControl"] button:before,
    [data-testid="stExpandSidebarButton"]:before {
        content: "›";
        display: block;
        color: #1d1d1f;
        font-size: 26px;
        line-height: 1;
        font-weight: 600;
        transform: translateY(-1px);
    }
    [data-testid="stSidebarCollapsedControl"] button svg,
    [data-testid="collapsedControl"] button svg,
    [data-testid="stExpandSidebarButton"] svg {
        color: #1d1d1f !important;
        width: 18px !important;
        height: 18px !important;
    }
    [data-testid="stSidebar"] [data-testid="stBaseButton-headerNoPadding"]:hover,
    [data-testid="stHeader"] [data-testid="stBaseButton-headerNoPadding"]:not([data-testid="stMainMenuButton"]):hover {
        transform: translateX(-2px) scale(1.03);
        box-shadow: 0 14px 30px rgba(18, 24, 38, .22), 0 0 0 4px rgba(101, 88, 247, .12) !important;
    }
    [data-testid="stSidebar"] [data-testid="stBaseButton-headerNoPadding"] svg,
    [data-testid="stHeader"] [data-testid="stBaseButton-headerNoPadding"]:not([data-testid="stMainMenuButton"]) svg {
        color: #1d1d1f !important;
        width: 18px !important;
        height: 18px !important;
    }
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {
        background: linear-gradient(180deg, rgba(255,255,255,.92), rgba(255,255,255,.74));
        border: 1px dashed rgba(111, 88, 247, .30);
        border-radius: 16px;
        box-shadow: inset 0 1px 0 rgba(255,255,255,.84);
    }
    [data-testid="stFileUploaderDropzone"] {
        position: relative !important;
    }
    [data-testid="stFileUploaderDropzone"] input[type="file"] {
        position: absolute !important;
        inset: 0 !important;
        width: 100% !important;
        height: 100% !important;
        margin: 0 !important;
        padding: 0 !important;
        border: 0 !important;
        opacity: 0 !important;
        clip: auto !important;
        clip-path: none !important;
        overflow: visible !important;
        white-space: normal !important;
        cursor: pointer !important;
        pointer-events: auto !important;
        z-index: 4 !important;
    }
    [data-testid="stFileUploaderDropzone"] > span > button[data-testid="stBaseButton-secondary"] {
        display: grid !important;
        place-items: center !important;
        position: relative !important;
        z-index: 2 !important;
        align-items: center !important;
        justify-content: center !important;
        text-align: center !important;
        background:
            radial-gradient(circle at 18% 0%, rgba(255,255,255,.76), transparent 36%),
            linear-gradient(180deg, rgba(255,255,255,.30), rgba(255,255,255,.12)),
            var(--sidebar-pill-bg) !important;
        color: #4f38e8 !important;
        border: 1px solid var(--sidebar-pill-border) !important;
        border-radius: 999px !important;
        min-width: 7.6rem;
        min-height: var(--sidebar-control-height);
        padding: .58rem 1rem !important;
        white-space: nowrap;
        line-height: 1 !important;
        overflow: hidden !important;
        box-shadow: var(--sidebar-pill-shadow) !important;
        backdrop-filter: saturate(180%) blur(16px) !important;
        pointer-events: none !important;
        transition: transform .16s ease, box-shadow .16s ease, filter .16s ease !important;
    }
    [data-testid="stFileUploaderDropzone"] > span > button[data-testid="stBaseButton-secondary"]:hover {
        background:
            radial-gradient(circle at 18% 0%, rgba(255,255,255,.82), transparent 36%),
            linear-gradient(180deg, rgba(255,255,255,.36), rgba(255,255,255,.16)),
            var(--sidebar-pill-hover) !important;
        filter: saturate(108%) brightness(1.01);
        transform: translateY(-1px);
        box-shadow: 0 14px 28px rgba(87, 80, 238, .16), inset 0 1px 0 rgba(255,255,255,.9) !important;
    }
    [data-testid="stFileUploaderDropzone"] > span > button[data-testid="stBaseButton-secondary"] > * {
        color: #4f38e8 !important;
        position: absolute !important;
        inset: 0 !important;
        display: grid !important;
        place-items: center !important;
        width: 100% !important;
        height: 100% !important;
        opacity: 0 !important;
        pointer-events: none !important;
    }
    [data-testid="stFileUploaderFile"] {
        background: #ffffff !important;
        border: 1px solid var(--line);
        border-radius: 6px;
        padding: .45rem .55rem;
        align-items: center;
    }
    [data-testid="stFileUploaderFile"] > div:has(svg),
    [data-testid="stFileUploaderFile"] > div:first-child {
        width: 2.1rem !important;
        height: 2.1rem !important;
        min-width: 2.1rem !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        border-radius: 8px !important;
        background: #eaf7ef !important;
        color: #1f7a45 !important;
        position: relative !important;
    }
    [data-testid="stFileUploaderFile"] [data-testid*="Icon"],
    [data-testid="stFileUploaderFile"] div[class*="fileIcon"],
    [data-testid="stFileUploaderFile"] div[class*="FileIcon"] {
        background: #eaf7ef !important;
        color: #1f7a45 !important;
        border-radius: 8px !important;
    }
    [data-testid="stFileUploaderFile"] > div:has(svg) svg,
    [data-testid="stFileUploaderFile"] > div:first-child svg,
    [data-testid="stFileUploaderFile"] [data-testid*="Icon"] svg,
    [data-testid="stFileUploaderFile"] div[class*="fileIcon"] svg,
    [data-testid="stFileUploaderFile"] div[class*="FileIcon"] svg {
        display: none !important;
    }
    [data-testid="stFileUploaderFile"] > div:has(svg):after,
    [data-testid="stFileUploaderFile"] > div:first-child:after,
    [data-testid="stFileUploaderFile"] [data-testid*="Icon"]:after,
    [data-testid="stFileUploaderFile"] div[class*="fileIcon"]:after,
    [data-testid="stFileUploaderFile"] div[class*="FileIcon"]:after {
        content: "XLS";
        font-size: .62rem;
        font-weight: 800;
        letter-spacing: .02em;
    }
    [data-testid="stFileUploaderFile"] button {
        background: transparent !important;
        color: var(--muted) !important;
        min-width: 2.4rem !important;
        padding: .15rem !important;
        border: 0 !important;
        font-size: 0 !important;
    }
    [data-testid="stFileUploaderFile"] button:after {
        content: "删除" !important;
        font-size: .72rem !important;
        color: var(--muted) !important;
    }
    [data-testid="stFileUploaderFile"] button span,
    [data-testid="stFileUploaderFile"] button p { display: none !important; }
    [data-testid="stFileUploaderFile"] button svg { display: none !important; }
    [data-testid="stFileChip"] {
        background: #ffffff !important;
        border: 1px solid var(--line);
        border-radius: 8px !important;
        padding: .45rem .5rem !important;
        gap: .55rem !important;
        min-width: 100% !important;
    }
    [data-testid="stFileChip"] > div:first-child {
        width: 2.1rem !important;
        height: 2.1rem !important;
        min-width: 2.1rem !important;
        border-radius: 8px !important;
        background: #eaf7ef !important;
        color: #1f7a45 !important;
        position: relative !important;
    }
    [data-testid="stFileChip"] > div:first-child svg {
        display: none !important;
    }
    [data-testid="stFileChip"] > div:first-child:after {
        content: "XLS";
        position: absolute;
        inset: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: .62rem;
        font-weight: 800;
        letter-spacing: .02em;
    }
    [data-testid="stFileChip"]:has([data-testid="stFileChipName"][title$=".csv"]) > div:first-child {
        background: #edf4ff !important;
        color: #1f63b8 !important;
    }
    [data-testid="stFileChip"]:has([data-testid="stFileChipName"][title$=".csv"]) > div:first-child:after {
        content: "CSV";
    }
    [data-testid="stFileChip"]:has([data-testid="stFileChipName"][title$=".doc"]) > div:first-child,
    [data-testid="stFileChip"]:has([data-testid="stFileChipName"][title$=".docx"]) > div:first-child {
        background: #eaf1ff !important;
        color: #2558b8 !important;
    }
    [data-testid="stFileChip"]:has([data-testid="stFileChipName"][title$=".doc"]) > div:first-child:after,
    [data-testid="stFileChip"]:has([data-testid="stFileChipName"][title$=".docx"]) > div:first-child:after {
        content: "DOC";
    }
    [data-baseweb="input"] > div,
    [data-baseweb="textarea"] > div,
    [data-baseweb="select"] > div {
        background: #ffffff !important;
        border-color: #cdd8de !important;
        color: var(--ink) !important;
        box-shadow: none !important;
    }
    [data-baseweb="input"] input,
    [data-baseweb="textarea"] textarea,
    [data-baseweb="select"] input,
    [data-baseweb="select"] [role="combobox"] {
        background: transparent !important;
        color: var(--ink) !important;
        -webkit-text-fill-color: var(--ink) !important;
    }
    [data-baseweb="input"] input::placeholder,
    [data-baseweb="textarea"] textarea::placeholder,
    [data-baseweb="select"] input::placeholder {
        color: #86868b !important;
        -webkit-text-fill-color: #86868b !important;
        opacity: 1 !important;
    }
    [data-baseweb="tag"] {
        background: var(--blue-soft) !important;
        color: var(--navy) !important;
    }
    [data-baseweb="tag"] * { color: var(--navy) !important; }
    [data-baseweb="popover"] {
        background: #ffffff !important;
        color: var(--ink) !important;
    }
    [role="option"] { color: var(--ink) !important; }
    [role="option"]:hover { background: var(--blue-soft) !important; }
    .saved-file-chip {
        margin: .16rem 0;
        padding: .46rem .52rem;
        border: 1px solid rgba(210, 213, 219, .88);
        border-radius: 10px;
        background: rgba(255,255,255,.92);
        box-shadow: inset 0 1px 0 rgba(255,255,255,.9);
        min-height: 3.05rem;
        display: flex;
        align-items: center;
        gap: .58rem;
        overflow: hidden;
        transition: transform .16s ease, border-color .16s ease, box-shadow .16s ease;
    }
    .saved-file-chip:hover {
        transform: translateY(-1px);
        border-color: rgba(111, 88, 247, .26);
        box-shadow: 0 10px 22px rgba(87, 80, 238, .10), inset 0 1px 0 rgba(255,255,255,.96);
    }
    .saved-file-icon {
        width: 2.3rem;
        height: 2.3rem;
        min-width: 2.3rem;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        border-radius: 10px;
        background: #eaf7ef;
        color: #1f7a45 !important;
        font-size: .64rem;
        font-weight: 900;
        letter-spacing: .03em;
    }
    .saved-file-meta {
        min-width: 0;
        flex: 1 1 auto;
        line-height: 1.2;
    }
    .saved-file-name {
        display: block;
        color: var(--ink) !important;
        font-size: .82rem;
        font-weight: 760;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    .saved-file-size {
        display: block;
        color: var(--muted) !important;
        font-size: .72rem;
        margin-top: .16rem;
    }
    div[data-testid="stHorizontalBlock"]:has(.saved-file-chip) {
        align-items: center !important;
    }
    div[data-testid="stHorizontalBlock"]:has(.saved-file-chip) [data-testid="stColumn"]:last-child {
        display: flex !important;
        align-items: center !important;
        justify-content: flex-start !important;
    }
    div[data-testid="stHorizontalBlock"]:has(.saved-file-chip) [data-testid="stColumn"]:last-child div.stButton > button {
        width: 2.55rem !important;
        min-width: 2.55rem !important;
        height: 2.55rem !important;
        min-height: 2.55rem !important;
        padding: 0 !important;
        border-radius: 999px !important;
        font-size: 0 !important;
        background: rgba(255,255,255,.92) !important;
        border: 1px solid rgba(210, 213, 219, .9) !important;
        box-shadow: inset 0 1px 0 rgba(255,255,255,.92), 0 8px 18px rgba(87, 80, 238, .08) !important;
    }
    div[data-testid="stHorizontalBlock"]:has(.saved-file-chip) [data-testid="stColumn"]:last-child div.stButton > button p {
        font-size: .9rem !important;
        font-weight: 900 !important;
        color: #4f38e8 !important;
        transform: none !important;
    }
    .data-intake-panel {
        margin: 0 0 .62rem;
        padding: .78rem .95rem;
        border-radius: 20px;
        border: 1px solid rgba(205, 194, 255, .72);
        background:
            radial-gradient(circle at 6% 0%, rgba(112, 91, 255, .10), transparent 32%),
            linear-gradient(180deg, rgba(255,255,255,.96), rgba(255,255,255,.84));
        box-shadow: 0 16px 34px rgba(87, 80, 238, .10), inset 0 1px 0 rgba(255,255,255,.96);
    }
    .data-intake-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        margin-bottom: 0;
    }
    .data-intake-title {
        display: flex;
        align-items: center;
        gap: .58rem;
        color: #4f38e8;
        font-weight: 900;
        letter-spacing: -.01em;
    }
    .data-intake-title:before {
        content: "";
        width: 4px;
        height: 1.28rem;
        border-radius: 999px;
        background: var(--brand-gradient);
        box-shadow: 0 6px 14px rgba(86, 61, 232, .22);
    }
    .data-intake-meta {
        color: var(--muted);
        font-size: .78rem;
        line-height: 1.55;
    }
    .data-intake-save-note {
        display: inline-flex;
        align-items: center;
        gap: .45rem;
        padding: .36rem .58rem;
        border-radius: 999px;
        background: rgba(111, 88, 247, .08);
        color: #4f38e8;
        font-size: .76rem;
        font-weight: 760;
        white-space: nowrap;
    }
    .data-intake-subtitle {
        margin: .05rem 0 .3rem;
        color: var(--ink);
        font-size: .9rem;
        font-weight: 820;
    }
    .data-intake-subtitle.compact {
        margin-top: .5rem;
    }
    .upload-kind-heading {
        min-height: 3.05rem;
        margin: .04rem 0 .42rem;
        padding: .64rem .78rem;
        border-radius: 14px;
        border: 1px solid rgba(210, 213, 219, .84);
        background: rgba(255,255,255,.86);
        box-shadow: inset 0 1px 0 rgba(255,255,255,.92);
    }
    .upload-kind-heading span {
        display: block;
        color: var(--ink) !important;
        font-size: .9rem;
        font-weight: 880;
        line-height: 1.1;
    }
    .upload-kind-heading small {
        display: block;
        color: var(--muted) !important;
        font-size: .72rem;
        font-weight: 650;
        line-height: 1.35;
        margin-top: .22rem;
        overflow-wrap: anywhere;
    }
    .upload-kind-heading.sales {
        border-color: rgba(0, 113, 227, .24);
        background: linear-gradient(180deg, rgba(247,251,255,.96), rgba(255,255,255,.84));
    }
    .upload-kind-heading.purchase {
        border-color: rgba(216, 145, 28, .28);
        background: linear-gradient(180deg, rgba(255,250,241,.96), rgba(255,255,255,.84));
    }
    .saved-upload-summary {
        display: flex;
        align-items: center;
        justify-content: flex-start;
        flex-wrap: wrap;
        gap: .42rem;
        margin: .72rem 0 .46rem;
        color: var(--muted);
        font-size: .76rem;
    }
    .saved-upload-summary span,
    .saved-upload-summary strong {
        display: inline-flex;
        align-items: center;
        min-height: 1.82rem;
        padding: .26rem .58rem;
        border-radius: 999px;
        border: 1px solid rgba(210, 213, 219, .82);
        background: rgba(255,255,255,.78);
        white-space: nowrap;
    }
    .saved-upload-summary strong {
        color: var(--ink);
        font-weight: 820;
    }
    .saved-file-list {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: .48rem;
        margin-bottom: .55rem;
    }
    .saved-file-line {
        min-width: 0;
        padding: .46rem .52rem;
        border: 1px solid rgba(210, 213, 219, .88);
        border-radius: 10px;
        background: rgba(255,255,255,.92);
        box-shadow: inset 0 1px 0 rgba(255,255,255,.9);
        min-height: 3.05rem;
        display: flex;
        align-items: center;
        gap: .58rem;
        overflow: hidden;
    }
    .saved-file-more {
        display: flex;
        align-items: center;
        justify-content: center;
        min-height: 3.05rem;
        border: 1px dashed rgba(184, 169, 255, .72);
        border-radius: 10px;
        color: var(--muted);
        font-size: .78rem;
        background: rgba(255,255,255,.56);
    }
    .data-intake-empty {
        min-height: 3.8rem;
        display: flex;
        align-items: center;
        justify-content: center;
        border: 1px dashed rgba(184, 169, 255, .72);
        border-radius: 16px;
        color: var(--muted);
        background: rgba(255,255,255,.62);
        font-size: .84rem;
    }
    .sidebar-nav-title {
        display: flex;
        align-items: center;
        justify-content: flex-start;
        position: relative;
        min-height: 2.95rem;
        width: 100%;
        box-sizing: border-box;
        margin: 1.12rem 0 .62rem;
        padding: .62rem .86rem .62rem 1rem;
        border-radius: 18px;
        border: 1px solid var(--sidebar-pill-border);
        background:
            radial-gradient(circle at 18% 0%, rgba(255,255,255,.82), transparent 36%),
            linear-gradient(180deg, rgba(255,255,255,.38), rgba(255,255,255,.16)),
            #ffffff;
        box-shadow: var(--sidebar-pill-shadow), 0 18px 38px rgba(90, 69, 245, .14);
        font-weight: 900;
        color: #4f38e8;
        letter-spacing: -.01em;
        overflow: hidden;
    }
    .sidebar-nav-title:before {
        content: "";
        width: 4px;
        height: 1.35rem;
        border-radius: 999px;
        margin-right: .62rem;
        background: var(--brand-gradient);
        box-shadow: 0 6px 14px rgba(86, 61, 232, .22);
    }
    .sidebar-nav-title:after {
        content: "";
        position: absolute;
        right: .88rem;
        width: .42rem;
        height: .42rem;
        border-radius: 999px;
        background: rgba(79, 56, 232, .18);
        box-shadow: 0 0 0 5px rgba(79, 56, 232, .06);
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] {
        display: none !important;
    }
    .sidebar-subnav {
        width: 100%;
        box-sizing: border-box;
        padding: 0 .42rem 0 1rem;
        margin: 0 0 .92rem;
    }
    .sidebar-subnav-item {
        position: relative;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        width: calc(100% - 1.92rem) !important;
        min-height: 2.48rem !important;
        box-sizing: border-box !important;
        margin: 0 0 .42rem 1.3rem !important;
        padding: .48rem .78rem !important;
        border-radius: 999px !important;
        border: 1px solid rgba(184, 169, 255, .54) !important;
        background: rgba(255,255,255,.82) !important;
        color: #5f636f !important;
        box-shadow: 0 8px 20px rgba(87, 80, 238, .08), inset 0 1px 0 rgba(255,255,255,.9) !important;
        text-decoration: none !important;
        font-size: .82rem !important;
        font-weight: 850 !important;
        line-height: 1.08 !important;
        text-align: center !important;
        white-space: nowrap !important;
        transition: transform .16s ease, color .16s ease, border-color .16s ease, box-shadow .16s ease;
    }
    .sidebar-subnav-item:before {
        content: "";
        position: absolute;
        left: -1.18rem;
        width: .28rem;
        height: .28rem;
        border-radius: 999px;
        background: rgba(111, 88, 247, .26);
    }
    .sidebar-subnav-item:hover {
        transform: translateX(2px);
        color: #4f38e8 !important;
        border-color: rgba(111, 88, 247, .38) !important;
        box-shadow: 0 12px 26px rgba(87, 80, 238, .13), inset 0 1px 0 rgba(255,255,255,.94) !important;
    }
    .sidebar-subnav-item.active {
        color: #4f38e8 !important;
        border-color: rgba(111, 88, 247, .46) !important;
        background: #ffffff !important;
        box-shadow: 0 14px 28px rgba(87, 80, 238, .16), inset 0 -3px 0 rgba(111, 88, 247, .78) !important;
        font-weight: 850 !important;
    }
    .sidebar-subnav-item.active:before {
        background: var(--brand-gradient);
        box-shadow: 0 0 0 4px rgba(111, 88, 247, .10);
    }
    .business-topbar {
        display: flex !important;
        align-items: center !important;
        justify-content: space-between !important;
        gap: 1rem !important;
        height: 72px !important;
        min-height: 72px !important;
        margin: 0 !important;
        padding: 0 1.65rem !important;
        color: #ffffff !important;
        background:
            radial-gradient(circle at 10% 0%, rgba(255,255,255,.22) 0, rgba(255,255,255,0) 28%),
            var(--brand-gradient) !important;
        box-shadow: 0 10px 28px rgba(75, 40, 222, .26) !important;
        position: fixed !important;
        top: 0 !important;
        left: 0 !important;
        right: 0 !important;
        width: 100vw !important;
        z-index: 1000002 !important;
        overflow: hidden !important;
    }
    .business-topbar:before {
        content: "";
        position: absolute;
        inset: 0;
        background: linear-gradient(90deg, rgba(255,255,255,.16), rgba(255,255,255,0) 38%, rgba(255,255,255,.08));
        pointer-events: none;
    }
    .business-brand {
        display: flex !important;
        align-items: center !important;
        gap: .65rem !important;
        margin-left: 0 !important;
        font-weight: 760 !important;
        letter-spacing: .01em !important;
        position: relative !important;
        z-index: 1 !important;
    }
    .business-brand-mark {
        display: grid;
        place-items: center;
        width: 30px;
        height: 30px;
        border-radius: 9px;
        color: #fff;
        background: rgba(255,255,255,.16);
        border: 1px solid rgba(255,255,255,.36);
        box-shadow: 0 8px 20px rgba(0,0,0,.12), inset 0 1px 0 rgba(255,255,255,.22);
        font-size: .82rem;
        font-weight: 800;
    }
    .business-brand small {
        padding-left: .65rem;
        border-left: 1px solid rgba(255,255,255,.45);
        font-size: .75rem;
        font-weight: 560;
        opacity: .94;
    }
    .business-meta {
        display: flex;
        align-items: center;
        gap: 1.2rem;
        font-size: .72rem;
        white-space: nowrap;
        position: relative;
        z-index: 1;
    }
    .business-meta .live {
        padding: .3rem .7rem;
        border-radius: 999px;
        background: var(--pill-bg);
        border: 1px solid var(--pill-border);
        box-shadow: inset 0 1px 0 rgba(255,255,255,.18);
    }
    .topbar-auth-pill {
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        min-width: 7.6rem;
        min-height: 2.1rem;
        padding: .3rem .85rem;
        border-radius: 999px;
        color: #ffffff !important;
        text-decoration: none !important;
        font-weight: 780;
        letter-spacing: -.01em;
        background: rgba(255,255,255,.16);
        border: 1px solid rgba(255,255,255,.32);
        box-shadow: inset 0 1px 0 rgba(255,255,255,.22), 0 10px 26px rgba(23, 16, 92, .18);
        backdrop-filter: saturate(180%) blur(16px);
        transition: transform .16s ease, background .16s ease, box-shadow .16s ease;
    }
    .topbar-auth-pill:hover {
        background: rgba(255,255,255,.22);
        transform: translateY(-1px);
        box-shadow: inset 0 1px 0 rgba(255,255,255,.28), 0 14px 32px rgba(23, 16, 92, .24);
    }
    .st-key-auth_topbar_controls {
        position: fixed !important;
        top: 9px !important;
        right: 1.5rem !important;
        z-index: 1000003 !important;
        width: min(12.5rem, calc(100vw - 2rem)) !important;
        display: flex !important;
        flex-direction: column !important;
        align-items: center !important;
        gap: .18rem !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    .st-key-auth_topbar_controls [data-testid="stButton"] {
        width: 100% !important;
        align-self: center !important;
    }
    .st-key-auth_topbar_controls button {
        width: 100% !important;
        min-width: 0 !important;
        min-height: 2rem !important;
        padding: .28rem .82rem !important;
        border-radius: 999px !important;
        color: #ffffff !important;
        font-weight: 780 !important;
        letter-spacing: 0 !important;
        background: rgba(255,255,255,.16) !important;
        border: 1px solid rgba(255,255,255,.32) !important;
        box-shadow: inset 0 1px 0 rgba(255,255,255,.22), 0 10px 26px rgba(23, 16, 92, .18) !important;
        backdrop-filter: saturate(180%) blur(16px) !important;
        transition: transform .16s ease, background .16s ease, box-shadow .16s ease !important;
    }
    .st-key-auth_topbar_controls button:hover {
        background: rgba(255,255,255,.22) !important;
        transform: translateY(-1px);
        box-shadow: inset 0 1px 0 rgba(255,255,255,.28), 0 14px 32px rgba(23, 16, 92, .24) !important;
    }
    .st-key-auth_topbar_controls button p {
        color: #ffffff !important;
        font-size: .86rem !important;
        font-weight: 780 !important;
        line-height: 1 !important;
        white-space: nowrap !important;
    }
    .topbar-auth-hint {
        width: 100%;
        color: rgba(255,255,255,.78);
        font-size: .62rem;
        font-weight: 620;
        line-height: 1.12;
        text-align: center;
        text-shadow: 0 1px 8px rgba(36, 19, 120, .22);
        pointer-events: none;
        white-space: nowrap;
    }
    @media (max-width: 760px) {
        .st-key-auth_topbar_controls {
            right: .75rem !important;
            width: 9rem !important;
        }
        .topbar-auth-hint {
            display: none !important;
        }
    }
    .hero {
        display: grid;
        grid-template-columns: minmax(230px, .75fr) minmax(420px, 1.7fr);
        align-items: center;
        gap: 1.2rem;
        padding: .95rem 1.15rem;
        border: 1px solid var(--line);
        border-radius: 14px;
        background: var(--panel);
        box-shadow: 0 8px 26px rgba(20, 24, 36, .06);
        margin-bottom: .8rem;
    }
    .hero-kicker {
        color: var(--teal-dark);
        font-weight: 700;
        letter-spacing: .03em;
        font-size: .7rem;
    }
    .hero h1 {
        color: var(--ink);
        margin: .14rem 0 0;
        font-size: 1.35rem;
        line-height: 1.2;
        font-weight: 720;
    }
    .hero p {
        color: var(--muted);
        margin: 0;
        padding-left: 1.2rem;
        border-left: 1px solid var(--line);
        font-size: .82rem;
        line-height: 1.55;
    }
    .diagnostic-panel {
        padding: .75rem .9rem;
        margin: .55rem 0 .75rem;
        border: 1px solid #e2e8f0;
        border-left: 3px solid var(--teal);
        border-radius: var(--radius);
        background: #ffffff;
    }
    .diagnostic-title {
        display: flex;
        align-items: center;
        gap: .45rem;
        margin-bottom: .4rem;
        color: var(--ink);
        font-size: .78rem;
        font-weight: 760;
    }
    .diagnostic-dot {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: var(--teal);
        box-shadow: 0 0 0 4px var(--teal-soft);
    }
    .diagnostic-summary {
        color: var(--ink);
        font-size: .78rem;
        line-height: 1.55;
    }
    .diagnostic-items {
        display: flex;
        flex-wrap: wrap;
        gap: .35rem .5rem;
        margin-top: .45rem;
    }
    .diagnostic-chip {
        padding: .22rem .48rem;
        border-radius: 4px;
        color: #8b5310;
        background: #fff7e8;
        font-size: .7rem;
    }
    [data-testid="stMetric"] {
        background: var(--panel);
        border: 1px solid var(--line);
        padding: .65rem .75rem;
        border-radius: var(--radius);
        box-shadow: var(--shadow);
        min-height: 112px;
        transition: border-color .15s ease, box-shadow .15s ease;
    }
    [data-testid="stMetric"]:hover { border-color: #a7cff8; box-shadow: 0 4px 14px rgba(0,113,227,.08); }
    [data-testid="stMetricLabel"] { color: var(--muted); font-size: .82rem; }
    [data-testid="stMetricValue"] {
        color: var(--ink);
        font-weight: 720;
        letter-spacing: -.02em;
        font-size: clamp(1.15rem, 1.7vw, 1.7rem);
        white-space: normal;
        overflow: visible;
    }
    .section-note {
        background: var(--teal-soft);
        border: 1px solid #d9e9fa;
        padding: .65rem .8rem;
        border-radius: var(--radius);
        color: var(--ink);
        margin: .35rem 0 .9rem;
        line-height: 1.5;
    }
    .channel-card {
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: var(--radius);
        padding: .9rem 1rem;
        min-height: 106px;
        box-shadow: var(--shadow);
    }
    .channel-card .name { font-weight: 700; color: var(--muted); font-size: .86rem; }
    .channel-card .big { font-size: 1.55rem; font-weight: 720; color: var(--ink); margin: .2rem 0; }
    .channel-card .meta { color: var(--muted); font-size: .82rem; line-height: 1.45; }
    .bar-list {
        display: grid;
        gap: .62rem;
        padding: .55rem .15rem .7rem;
    }
    .bar-list.compact {
        gap: .45rem;
        padding: .35rem .1rem .55rem;
    }
    .bar-row {
        display: grid;
        grid-template-columns: minmax(110px, 28%) minmax(140px, 1fr) 68px;
        gap: .7rem;
        align-items: center;
    }
    .bar-label {
        color: var(--ink);
        font-size: .82rem;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    .bar-track {
        height: 18px;
        border-radius: 5px;
        background: #e8edf0;
        overflow: hidden;
    }
    .bar-fill {
        height: 100%;
        min-width: 2px;
        border-radius: 5px;
        transition: filter .15s ease, opacity .15s ease;
    }
    .bar-row:hover .bar-fill { filter: brightness(.9); }
    .bar-value {
        color: var(--ink);
        font-size: .8rem;
        font-variant-numeric: tabular-nums;
        text-align: right;
    }
    .trend-summary-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: .55rem;
        margin: .15rem 0 .65rem;
    }
    .trend-summary-card {
        min-height: 76px;
        padding: .7rem .75rem;
        border-radius: 14px;
        border: 1px solid var(--sidebar-pill-border);
        background:
            radial-gradient(circle at 18% 0%, rgba(255,255,255,.82), transparent 36%),
            linear-gradient(180deg, rgba(255,255,255,.34), rgba(255,255,255,.14)),
            rgba(255,255,255,.76);
        box-shadow: var(--sidebar-pill-shadow);
    }
    .trend-summary-card .label {
        color: var(--muted);
        font-size: .72rem;
        font-weight: 720;
        margin-bottom: .28rem;
    }
    .trend-summary-card .value {
        color: var(--ink);
        font-size: 1.08rem;
        line-height: 1.15;
        font-weight: 850;
        letter-spacing: -.02em;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .pipeline-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: .8rem;
        margin: .35rem 0 1rem;
    }
    .pipeline-card {
        padding: .95rem 1rem;
        border-radius: 18px;
        border: 1px solid rgba(211,215,226,.78);
        background: linear-gradient(180deg, rgba(255,255,255,.95), rgba(255,255,255,.82));
        box-shadow: 0 12px 26px rgba(29,29,31,.06), inset 0 1px 0 rgba(255,255,255,.92);
    }
    .pipeline-card .label {
        color: var(--muted);
        font-size: .74rem;
        font-weight: 850;
    }
    .pipeline-card .value {
        margin-top: .28rem;
        color: var(--ink);
        font-size: 1.55rem;
        line-height: 1;
        font-weight: 950;
        letter-spacing: -.03em;
    }
    .pipeline-card .hint {
        margin-top: .34rem;
        color: var(--muted);
        font-size: .72rem;
    }
    .report-panel {
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: var(--radius);
        padding: 1rem 1.2rem;
        box-shadow: var(--shadow);
        margin: 1rem 0;
    }
    .report-panel h1, .report-panel h2, .report-panel h3 { color: var(--navy); letter-spacing: -.02em; }
    .context-chip {
        display: inline-block;
        padding: .3rem .6rem;
        margin: .15rem .25rem .15rem 0;
        border-radius: 6px;
        background: var(--blue-soft);
        color: var(--navy);
        font-size: .78rem;
        font-weight: 650;
    }
    .stTabs [data-baseweb="tab-list"],
    [data-testid="stTabs"] [role="tablist"] {
        display: inline-flex !important;
        gap: .28rem !important;
        width: auto !important;
        max-width: 100% !important;
        background: rgba(255,255,255,.68) !important;
        padding: .28rem !important;
        border: 1px solid rgba(218, 224, 235, .82) !important;
        border-radius: 999px !important;
        box-shadow: 0 12px 30px rgba(31, 41, 55, .08), inset 0 1px 0 rgba(255,255,255,.82) !important;
        backdrop-filter: saturate(180%) blur(18px) !important;
        margin: .25rem 0 .75rem !important;
    }
    .stTabs [data-baseweb="tab"],
    [data-testid="stTabs"] [role="tab"] {
        background: transparent !important;
        border: 0 !important;
        border-radius: 999px !important;
        padding: .5rem 1.05rem !important;
        min-height: 38px !important;
        position: relative !important;
        transition: color .18s ease, background .18s ease, box-shadow .18s ease, transform .18s ease !important;
    }
    .stTabs [data-baseweb="tab"]:hover,
    [data-testid="stTabs"] [role="tab"]:hover {
        background: rgba(255,255,255,.72);
        transform: translateY(-1px);
    }
    .stTabs [data-baseweb="tab"] p,
    [data-testid="stTabs"] [role="tab"] p {
        color: #6b6f7c !important;
        font-weight: 760;
        letter-spacing: -.01em;
    }
    .stTabs [aria-selected="true"],
    [data-testid="stTabs"] [role="tab"][aria-selected="true"] {
        background: rgba(255,255,255,.92) !important;
        border-bottom: 0 !important;
        box-shadow: 0 10px 24px rgba(101, 88, 247, .18), 0 0 0 1px rgba(101, 88, 247, .16) inset !important;
    }
    .stTabs [aria-selected="true"]:after,
    [data-testid="stTabs"] [role="tab"][aria-selected="true"]:after {
        content: "";
        position: absolute;
        left: 50%;
        bottom: 4px;
        width: 28px;
        height: 3px;
        border-radius: 999px;
        transform: translateX(-50%);
        background: var(--brand-gradient);
        box-shadow: 0 0 14px rgba(101, 88, 247, .72), 0 0 28px rgba(129, 41, 230, .38);
    }
    .stTabs [aria-selected="true"] p,
    [data-testid="stTabs"] [role="tab"][aria-selected="true"] p { color: #3f32d6 !important; }
    .stTabs [data-baseweb="tab-highlight"] { display: none !important; }
    .stTabs [data-baseweb="tab-border"] { display: none !important; }
    [data-testid="stSegmentedControl"] {
        margin-bottom: .25rem !important;
    }
    [data-testid="stSegmentedControl"] [role="radiogroup"] {
        display: inline-flex !important;
        gap: .28rem !important;
        width: auto !important;
        max-width: 100% !important;
        background: rgba(255,255,255,.68) !important;
        padding: .28rem !important;
        border: 1px solid rgba(218, 224, 235, .82) !important;
        border-radius: 999px !important;
        box-shadow: 0 12px 30px rgba(31, 41, 55, .08), inset 0 1px 0 rgba(255,255,255,.82) !important;
        backdrop-filter: saturate(180%) blur(18px) !important;
    }
    [data-testid="stSegmentedControl"] label {
        position: relative !important;
        min-height: 38px !important;
        padding: .48rem 1.05rem !important;
        border-radius: 999px !important;
        background: transparent !important;
        border: 0 !important;
        color: #6b6f7c !important;
        transition: background .18s ease, box-shadow .18s ease, transform .18s ease !important;
    }
    [data-testid="stSegmentedControl"] label:hover {
        background: rgba(255,255,255,.72) !important;
        transform: translateY(-1px);
    }
    [data-testid="stSegmentedControl"] label:has(input:checked) {
        background: rgba(255,255,255,.92) !important;
        box-shadow: 0 10px 24px rgba(101, 88, 247, .18), 0 0 0 1px rgba(101, 88, 247, .16) inset !important;
    }
    [data-testid="stSegmentedControl"] label:has(input:checked):after {
        content: "";
        position: absolute;
        left: 50%;
        bottom: 4px;
        width: 28px;
        height: 3px;
        border-radius: 999px;
        transform: translateX(-50%);
        background: var(--brand-gradient);
        box-shadow: 0 0 14px rgba(101, 88, 247, .72), 0 0 28px rgba(129, 41, 230, .38);
    }
    [data-testid="stSegmentedControl"] label p,
    [data-testid="stSegmentedControl"] label span {
        color: #6b6f7c !important;
        font-weight: 780 !important;
        line-height: 1 !important;
    }
    [data-testid="stSegmentedControl"] label:has(input:checked) p,
    [data-testid="stSegmentedControl"] label:has(input:checked) span {
        color: #3f32d6 !important;
    }
    [data-testid="stButtonGroup"] [role="radiogroup"] {
        display: inline-flex !important;
        gap: .28rem !important;
        width: auto !important;
        max-width: 100% !important;
        background: rgba(255,255,255,.68) !important;
        padding: .28rem !important;
        border: 1px solid rgba(218, 224, 235, .82) !important;
        border-radius: 999px !important;
        box-shadow: 0 12px 30px rgba(31, 41, 55, .08), inset 0 1px 0 rgba(255,255,255,.82) !important;
        backdrop-filter: saturate(180%) blur(18px) !important;
    }
    [data-testid="stButtonGroup"] button[data-testid^="stBaseButton-segmented_control"] {
        position: relative !important;
        min-height: 38px !important;
        padding: .48rem 1.05rem !important;
        border-radius: 999px !important;
        background: transparent !important;
        border: 0 !important;
        color: #6b6f7c !important;
        box-shadow: none !important;
        transition: color .18s ease, background .18s ease, box-shadow .18s ease, transform .18s ease !important;
    }
    [data-testid="stButtonGroup"] button[data-testid^="stBaseButton-segmented_control"]:hover {
        background: rgba(255,255,255,.72) !important;
        transform: translateY(-1px);
    }
    [data-testid="stButtonGroup"] button[data-testid="stBaseButton-segmented_controlActive"] {
        background: rgba(255,255,255,.92) !important;
        border-bottom: 0 !important;
        box-shadow: 0 10px 24px rgba(101, 88, 247, .18), 0 0 0 1px rgba(101, 88, 247, .16) inset !important;
    }
    [data-testid="stButtonGroup"] button[data-testid="stBaseButton-segmented_controlActive"]:after {
        content: "";
        position: absolute;
        left: 50%;
        bottom: 4px;
        width: 28px;
        height: 3px;
        border-radius: 999px;
        transform: translateX(-50%);
        background: var(--brand-gradient);
        box-shadow: 0 0 14px rgba(101, 88, 247, .72), 0 0 28px rgba(129, 41, 230, .38);
    }
    [data-testid="stButtonGroup"] button[data-testid^="stBaseButton-segmented_control"] p,
    [data-testid="stButtonGroup"] button[data-testid^="stBaseButton-segmented_control"] span {
        color: #6b6f7c !important;
        font-weight: 780 !important;
        line-height: 1 !important;
    }
    [data-testid="stButtonGroup"] button[data-testid="stBaseButton-segmented_controlActive"] p,
    [data-testid="stButtonGroup"] button[data-testid="stBaseButton-segmented_controlActive"] span {
        color: #3f32d6 !important;
    }
    [data-testid="stMain"] [data-testid="stRadio"] label,
    [data-testid="stMain"] [data-testid="stRadio"] label * { color: var(--ink) !important; }
    [data-testid="stToggle"] label, [data-testid="stToggle"] label * { color: var(--ink) !important; }
    [data-testid="stDataFrame"] { background: #ffffff; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
    div.stButton > button,
    div.stDownloadButton > button,
    div.stFormSubmitButton > button {
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        text-align: center !important;
        position: relative;
        isolation: isolate;
        overflow: hidden;
        border-radius: 999px;
        border: 1px solid var(--sidebar-pill-border);
        background:
            radial-gradient(circle at 18% 0%, rgba(255,255,255,.78), transparent 36%),
            linear-gradient(180deg, rgba(255,255,255,.32), rgba(255,255,255,.12)),
            var(--sidebar-pill-bg);
        color: #4f38e8;
        font-weight: 800;
        letter-spacing: -.01em;
        padding: .58rem .95rem;
        line-height: 1 !important;
        box-shadow: var(--sidebar-pill-shadow);
        backdrop-filter: saturate(180%) blur(16px);
        transition: transform .18s ease, box-shadow .18s ease, filter .18s ease;
    }
    div.stButton > button p,
    div.stDownloadButton > button p,
    div.stFormSubmitButton > button p {
        width: 100% !important;
        margin: 0 !important;
        text-align: center !important;
        line-height: 1 !important;
    }
    div.stButton > button *,
    div.stDownloadButton > button *,
    div.stFormSubmitButton > button * {
        color: #4f38e8 !important;
        font-weight: 850 !important;
    }
    div.stButton > button:before,
    div.stDownloadButton > button:before,
    div.stFormSubmitButton > button:before {
        content: "";
        position: absolute;
        inset: 1px;
        border-radius: inherit;
        background: linear-gradient(180deg, rgba(255,255,255,.22), rgba(255,255,255,0));
        z-index: -1;
    }
    div.stButton > button:hover,
    div.stDownloadButton > button:hover,
    div.stFormSubmitButton > button:hover {
        transform: translateY(-1px);
        filter: saturate(1.05);
        background:
            radial-gradient(circle at 18% 0%, rgba(255,255,255,.82), transparent 36%),
            linear-gradient(180deg, rgba(255,255,255,.36), rgba(255,255,255,.16)),
            var(--sidebar-pill-hover);
        box-shadow: 0 14px 28px rgba(87, 80, 238, .16), inset 0 1px 0 rgba(255,255,255,.9);
    }
    div.stButton > button:active,
    div.stDownloadButton > button:active,
    div.stFormSubmitButton > button:active {
        transform: translateY(0) scale(.98);
    }
    div.stButton > button[kind="secondary"],
    div.stButton > button[data-testid="stBaseButton-secondary"],
    div.stDownloadButton > button[kind="secondary"],
    div.stDownloadButton > button[data-testid="stBaseButton-secondary"],
    div.stFormSubmitButton > button[kind="secondaryFormSubmit"],
    div.stFormSubmitButton > button[data-testid="stBaseButton-secondaryFormSubmit"] {
        background:
            radial-gradient(circle at 18% 0%, rgba(255,255,255,.78), transparent 36%),
            linear-gradient(180deg, rgba(255,255,255,.32), rgba(255,255,255,.12)),
            var(--sidebar-pill-bg);
        color: #4f38e8;
        border: 1px solid var(--sidebar-pill-border);
        box-shadow: var(--sidebar-pill-shadow);
    }
    div.stButton > button:has(p:only-child) {
        min-height: 2.8rem;
    }
    [data-testid="stSidebar"] div.stButton > button {
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        width: 100% !important;
        max-width: 100% !important;
        margin-left: auto !important;
        margin-right: auto !important;
        min-height: var(--sidebar-control-height) !important;
        border-radius: 999px !important;
        background:
            radial-gradient(circle at 18% 0%, rgba(255,255,255,.78), transparent 36%),
            linear-gradient(180deg, rgba(255,255,255,.32), rgba(255,255,255,.12)),
            var(--sidebar-pill-bg) !important;
        color: #4f38e8 !important;
        border: 1px solid var(--sidebar-pill-border) !important;
        box-shadow: var(--sidebar-pill-shadow) !important;
        backdrop-filter: saturate(180%) blur(16px) !important;
    }
    [data-testid="stSidebar"] div.stButton > button:hover {
        background:
            radial-gradient(circle at 18% 0%, rgba(255,255,255,.82), transparent 36%),
            linear-gradient(180deg, rgba(255,255,255,.36), rgba(255,255,255,.16)),
            var(--sidebar-pill-hover) !important;
        box-shadow: 0 14px 28px rgba(87, 80, 238, .16), inset 0 1px 0 rgba(255,255,255,.9) !important;
    }
    [data-testid="stSidebar"] div.stButton > button * {
        color: #4f38e8 !important;
        font-weight: 850 !important;
        line-height: 1 !important;
        text-align: center !important;
    }
    [data-testid="stSidebar"] div.stButton > button p {
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        width: 100% !important;
        margin: 0 !important;
        min-height: 1.25rem !important;
        font-size: .95rem !important;
        font-weight: 900 !important;
        letter-spacing: 0 !important;
        transform: translateY(-1px);
    }
    [data-testid="stSidebar"] div.stButton > button:has(p:only-child) {
        min-height: var(--sidebar-control-height) !important;
        padding: .48rem .74rem !important;
    }
    [data-testid="stSidebar"] div.stButton > button:has(p:only-child) p {
        font-size: .84rem !important;
    }
    [data-testid="stSidebar"] div.stButton > button:has(p:only-child) p:only-child {
        font-weight: 900 !important;
    }
    [data-testid="stSidebar"] div.stButton > button p:only-child {
        min-width: 1em;
    }
    [data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"] {
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        text-align: center !important;
        min-height: var(--sidebar-control-height) !important;
        min-width: 2rem !important;
        max-width: 100% !important;
        margin-left: auto !important;
        margin-right: auto !important;
        padding: .48rem .68rem !important;
        border-radius: 999px !important;
        background:
            radial-gradient(circle at 18% 0%, rgba(255,255,255,.78), transparent 36%),
            linear-gradient(180deg, rgba(255,255,255,.32), rgba(255,255,255,.12)),
            var(--sidebar-pill-bg) !important;
        color: #4f38e8 !important;
        border: 1px solid var(--sidebar-pill-border) !important;
        box-shadow: var(--sidebar-pill-shadow) !important;
        backdrop-filter: saturate(180%) blur(16px) !important;
    }
    [data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"]:hover {
        background:
            radial-gradient(circle at 18% 0%, rgba(255,255,255,.82), transparent 36%),
            linear-gradient(180deg, rgba(255,255,255,.36), rgba(255,255,255,.16)),
            var(--sidebar-pill-hover) !important;
        box-shadow: 0 14px 28px rgba(87, 80, 238, .16), inset 0 1px 0 rgba(255,255,255,.9) !important;
    }
    [data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"] *,
    [data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"] p {
        color: #4f38e8 !important;
        font-weight: 900 !important;
        line-height: 1 !important;
        text-align: center !important;
        margin: 0 !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] {
        background: transparent !important;
        border: 0 !important;
        box-shadow: none !important;
        margin: .45rem 0 !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] details {
        border: 0 !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary {
        border: 1px solid var(--sidebar-pill-border) !important;
        border-radius: 14px !important;
        background:
            radial-gradient(circle at 18% 0%, rgba(255,255,255,.78), transparent 36%),
            linear-gradient(180deg, rgba(255,255,255,.32), rgba(255,255,255,.12)),
            var(--sidebar-pill-bg) !important;
        box-shadow: var(--sidebar-pill-shadow) !important;
        min-height: 3.15rem !important;
        padding: .72rem .82rem !important;
        transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary:hover {
        transform: translateY(-1px);
        border-color: rgba(111, 88, 247, .36) !important;
        box-shadow: 0 14px 28px rgba(87, 80, 238, .14), inset 0 1px 0 rgba(255,255,255,.9) !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary p {
        color: var(--ink) !important;
        font-weight: 760 !important;
        line-height: 1.35 !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] {
        margin-top: .45rem !important;
        padding: .65rem .7rem .75rem !important;
        border: 1px solid rgba(111, 88, 247, .12) !important;
        border-radius: 12px !important;
        background: rgba(255,255,255,.68) !important;
    }
    [data-testid="stExpander"] { background: #fff; border: 1px solid var(--line); border-radius: 10px; }
    [data-testid="stAppDeployButton"], [data-testid="stToolbar"] { display: none !important; }
    [data-testid="stElementToolbar"] { display: none !important; }
    [data-testid="stFileUploaderDropzoneInstructions"] > div > span { display: none !important; }
    [data-testid="stFileUploaderDropzoneInstructions"]:before {
        content: "拖拽文件到此处\\A支持 CSV、XLSX、XLS，单文件不超过 200MB";
        white-space: pre-line;
        color: var(--muted);
        font-size: .76rem;
        line-height: 1.45;
    }
    [data-testid="stFileUploaderDropzone"] > span > button[data-testid="stBaseButton-secondary"] { font-size: 0 !important; }
    [data-testid="stFileUploaderDropzone"] > span > button[data-testid="stBaseButton-secondary"]:after {
        content: "选择文件";
        position: absolute;
        inset: 0;
        display: grid;
        align-items: center;
        justify-content: center;
        place-items: center;
        width: 100%;
        height: 100%;
        text-align: center;
        font-size: .82rem;
        font-weight: 850;
        line-height: 1;
        white-space: nowrap;
        pointer-events: none;
    }
    h2, h3 { color: var(--ink); letter-spacing: -.02em; }
    h2 { font-size: 1.12rem !important; }
    h3 { font-size: .98rem !important; }
    @media (max-width: 720px) {
        html, body, .stApp {
            overflow-x: hidden !important;
        }
        .block-container {
            padding: 4.85rem .72rem 2rem !important;
            max-width: 100vw !important;
        }
        section[data-testid="stSidebar"],
        [data-testid="stSidebar"] {
            min-width: min(86vw, 320px) !important;
            max-width: min(86vw, 320px) !important;
            width: min(86vw, 320px) !important;
            transform: none !important;
            translate: none !important;
            left: 0 !important;
            border-right: 1px solid rgba(229,229,231,.94) !important;
            box-shadow: 18px 0 42px rgba(18, 24, 38, .16) !important;
        }
        section[data-testid="stSidebar"][aria-expanded="false"],
        [data-testid="stSidebar"][aria-expanded="false"],
        section[data-testid="stSidebar"].stSidebar[aria-expanded="false"] {
            transform: none !important;
            translate: none !important;
            left: 0 !important;
            margin-left: 0 !important;
        }
        [data-testid="stSidebar"] { background-size: 100% 64px !important; }
        [data-testid="stSidebarContent"] {
            padding-top: 3.55rem !important;
            padding-left: .72rem !important;
            padding-right: .72rem !important;
        }
        .stApp:before { height: 64px; }
        .sidebar-top-fill { height: 64px; }
        [data-testid="stSidebarCollapseButton"],
        [data-testid="stSidebarCollapsedControl"],
        [data-testid="collapsedControl"],
        [data-testid="stExpandSidebarButton"] {
            z-index: 1000006 !important;
        }
        [data-testid="stSidebar"] [data-testid="stBaseButton-headerNoPadding"],
        [data-testid="stSidebarCollapseButton"] [data-testid="stBaseButton-headerNoPadding"],
        [data-testid="stHeader"] [data-testid="stBaseButton-headerNoPadding"]:not([data-testid="stMainMenuButton"]),
        [data-testid="stSidebarCollapsedControl"] button,
        [data-testid="collapsedControl"] button,
        [data-testid="stExpandSidebarButton"] {
            display: flex !important;
            visibility: visible !important;
            opacity: 1 !important;
            top: 76px !important;
            left: 14px !important;
            width: 42px !important;
            height: 42px !important;
            min-width: 42px !important;
            min-height: 42px !important;
            align-items: center !important;
            justify-content: center !important;
            padding: 0 !important;
            overflow: visible !important;
            border-radius: 999px !important;
            background: rgba(255,255,255,.98) !important;
            border: 1px solid rgba(211, 215, 226, .95) !important;
            color: #1d1d1f !important;
            box-shadow: 0 14px 34px rgba(20, 24, 36, .24), 0 0 0 5px rgba(101, 88, 247, .10) !important;
            z-index: 1000006 !important;
        }
        [data-testid="stSidebar"] [data-testid="stBaseButton-headerNoPadding"]:before,
        [data-testid="stSidebarCollapseButton"] [data-testid="stBaseButton-headerNoPadding"]:before,
        [data-testid="stHeader"] [data-testid="stBaseButton-headerNoPadding"]:not([data-testid="stMainMenuButton"]):before,
        [data-testid="stSidebarCollapsedControl"] button:before,
        [data-testid="collapsedControl"] button:before,
        [data-testid="stExpandSidebarButton"]:before {
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            width: 100% !important;
            height: 100% !important;
            font-size: 26px !important;
            line-height: 1 !important;
            font-weight: 850 !important;
            color: #1d1d1f !important;
            transform: translateY(-1px) !important;
        }
        [data-testid="stSidebar"][aria-expanded="true"] [data-testid="stBaseButton-headerNoPadding"],
        [data-testid="stSidebarCollapseButton"] [data-testid="stBaseButton-headerNoPadding"] {
            left: calc(min(86vw, 320px) - 19px) !important;
        }
        [data-testid="stSidebarCollapsedControl"] {
            top: 76px !important;
            left: 14px !important;
            z-index: 1000006 !important;
        }
        [data-testid="stExpandSidebarButton"] {
            position: fixed !important;
            pointer-events: auto !important;
        }
        .business-topbar {
            left: 0 !important;
            height: 64px !important;
            min-height: 64px !important;
            padding: 0 .72rem 0 3.75rem !important;
            gap: .5rem !important;
            z-index: 1000003 !important;
        }
        .business-brand {
            margin-left: 0 !important;
            gap: .45rem !important;
            min-width: 0 !important;
        }
        .business-brand-mark {
            width: 28px !important;
            height: 28px !important;
            border-radius: 8px !important;
            font-size: .76rem !important;
        }
        .business-brand > span:not(.business-brand-mark) {
            max-width: 42vw !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            white-space: nowrap !important;
            font-size: .88rem !important;
        }
        .business-brand small { display: none !important; }
        .business-meta { display: none; }
        .hero {
            grid-template-columns: 1fr !important;
            gap: .65rem !important;
            padding: .85rem .9rem !important;
            border-radius: 16px !important;
            margin-bottom: .65rem !important;
        }
        .hero h1 {
            font-size: 1.22rem !important;
            line-height: 1.25 !important;
        }
        .hero p { padding: .55rem 0 0; border-left: 0; border-top: 1px solid var(--line); }
        .diagnostic-panel,
        .section-note,
        .channel-card,
        [data-testid="stMetric"] {
            border-radius: 16px !important;
        }
        .trend-summary-grid {
            grid-template-columns: 1fr !important;
        }
        .saved-file-list {
            grid-template-columns: 1fr 1fr !important;
        }
        .upload-kind-heading {
            min-height: auto !important;
            padding: .58rem .66rem !important;
        }
        .pipeline-grid {
            grid-template-columns: 1fr 1fr !important;
            gap: .55rem !important;
        }
        .pipeline-card {
            padding: .75rem .8rem !important;
            border-radius: 15px !important;
        }
        .pipeline-card .value {
            font-size: 1.18rem !important;
        }
        .bar-row {
            grid-template-columns: minmax(96px, 38%) minmax(96px, 1fr) 54px !important;
            gap: .45rem !important;
        }
        .bar-label,
        .bar-value {
            font-size: .75rem !important;
        }
        [data-testid="stTabs"] [role="tablist"],
        .stTabs [data-baseweb="tab-list"],
        [data-testid="stSegmentedControl"] [role="radiogroup"],
        [data-testid="stButtonGroup"] [role="radiogroup"] {
            display: flex !important;
            width: 100% !important;
            max-width: 100% !important;
            overflow-x: auto !important;
            scrollbar-width: none !important;
            -webkit-overflow-scrolling: touch !important;
            justify-content: flex-start !important;
        }
        [data-testid="stTabs"] [role="tablist"]::-webkit-scrollbar,
        .stTabs [data-baseweb="tab-list"]::-webkit-scrollbar,
        [data-testid="stSegmentedControl"] [role="radiogroup"]::-webkit-scrollbar,
        [data-testid="stButtonGroup"] [role="radiogroup"]::-webkit-scrollbar {
            display: none !important;
        }
        [data-testid="stTabs"] [role="tab"],
        .stTabs [data-baseweb="tab"],
        [data-testid="stSegmentedControl"] label,
        [data-testid="stButtonGroup"] button[data-testid^="stBaseButton-segmented_control"] {
            flex: 0 0 auto !important;
            min-width: max-content !important;
            padding-left: .86rem !important;
            padding-right: .86rem !important;
        }
        [data-testid="stHorizontalBlock"] {
            gap: .72rem !important;
        }
        [data-testid="stFileUploaderDropzone"] {
            padding: .8rem .7rem !important;
        }
        [data-testid="stFileUploaderDropzone"] > span > button[data-testid="stBaseButton-secondary"] {
            width: 100% !important;
            min-width: 0 !important;
        }
        [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] {
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: nowrap !important;
            align-items: center !important;
            gap: .52rem !important;
        }
        [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] [data-testid="stColumn"]:first-child {
            flex: 1 1 auto !important;
            width: auto !important;
            min-width: 0 !important;
        }
        [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] [data-testid="stColumn"]:last-child {
            flex: 0 0 42px !important;
            width: 42px !important;
            min-width: 42px !important;
        }
        [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] [data-testid="stColumn"]:last-child div.stButton > button {
            width: 42px !important;
            min-width: 42px !important;
            height: 42px !important;
            min-height: 42px !important;
            padding: 0 !important;
        }
        [data-testid="stDataFrame"],
        [data-testid="stVegaLiteChart"] {
            max-width: 100% !important;
            overflow-x: auto !important;
        }
        h2 { font-size: 1.02rem !important; }
        h3 { font-size: .94rem !important; }
    }
    @media (max-width: 420px) {
        .block-container { padding-left: .55rem !important; padding-right: .55rem !important; }
        .business-topbar { padding-left: 3.35rem !important; padding-right: .55rem !important; }
        .business-brand > span:not(.business-brand-mark) { max-width: 48vw !important; font-size: .82rem !important; }
        .business-brand-mark { display: none !important; }
        .hero h1 { font-size: 1.12rem !important; }
        .diagnostic-summary { font-size: .74rem !important; }
        [data-testid="stSidebar"] .stCaption { font-size: .68rem !important; }
        .saved-file-list {
            grid-template-columns: 1fr !important;
        }
        .saved-file-chip {
            padding: .42rem .5rem !important;
            min-height: 2.9rem !important;
        }
        [data-testid="stTabs"] [role="tab"],
        .stTabs [data-baseweb="tab"],
        [data-testid="stSegmentedControl"] label,
        [data-testid="stButtonGroup"] button[data-testid^="stBaseButton-segmented_control"] {
            min-height: 36px !important;
            padding: .45rem .72rem !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource(show_spinner=False)
def get_auth_store() -> AuthStore:
    store = AuthStore()
    store.init_db()
    return store


def _session_user() -> AuthUser | None:
    raw_user = st.session_state.get("current_user")
    if not isinstance(raw_user, dict) or not raw_user.get("id"):
        return None
    store = get_auth_store()
    user = store.get_user(str(raw_user["id"]))
    if user is None:
        st.session_state.pop("current_user", None)
    return user


def _clear_auth_query() -> None:
    try:
        if "auth" in st.query_params:
            del st.query_params["auth"]
    except Exception:
        pass


def _close_auth_dialog() -> None:
    st.session_state["show_auth_dialog"] = False
    _clear_auth_query()


@st.dialog("账号登录 / 注册", on_dismiss=_close_auth_dialog)
def render_account_dialog() -> None:
    """Show account actions without blocking guest usage."""
    try:
        store = get_auth_store()
    except AuthStoreError as exc:
        st.error(str(exc))
        return

    current = _session_user()
    if current is not None:
        st.success(f"已登录：{current.email}")
        if current.is_admin:
            st.caption("权限：管理员")
        st.caption("登录账号会保留上传文件、Pipeline 和报告设置；游客数据关闭会话后不保留。")
        if st.button("退出登录", width="stretch"):
            st.session_state.pop("current_user", None)
            _close_auth_dialog()
            st.rerun()
        if st.button("关闭", width="stretch"):
            _close_auth_dialog()
            st.rerun()
        return

    st.caption("不登录也可以直接使用。登录或注册后，上传文件、Pipeline 和报告设置会保存在账号下。")
    login_tab, register_tab = st.tabs(["登录", "注册"])
    with login_tab:
        with st.form("account-login-form", clear_on_submit=False):
            email = st.text_input("邮箱", key="login-email")
            password = st.text_input("密码", type="password", key="login-password")
            submitted = st.form_submit_button("登录", type="primary")
        if submitted:
            user = store.authenticate(email, password)
            if user is None:
                st.error("邮箱或密码不正确。")
            else:
                st.session_state["current_user"] = user.to_session()
                st.session_state["promote_guest_state_to_user_id"] = user.id
                _close_auth_dialog()
                st.rerun()

    with register_tab:
        with st.form("account-register-form", clear_on_submit=False):
            name = st.text_input("姓名 / 公司名", key="register-name")
            email = st.text_input("注册邮箱", key="register-email")
            password = st.text_input("设置密码", type="password", key="register-password")
            submitted = st.form_submit_button("创建账号", type="primary")
        if submitted:
            try:
                user = store.register_user(email, password, name)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.session_state["current_user"] = user.to_session()
                st.session_state["promote_guest_state_to_user_id"] = user.id
                st.success("账号已创建。")
                _close_auth_dialog()
                st.rerun()


current_user = _session_user()
if st.query_params.get("auth") == "1":
    st.session_state["show_auth_dialog"] = True
    _clear_auth_query()
if st.session_state.get("show_auth_dialog"):
    render_account_dialog()


def _safe_upload_filename(name: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z._\-\u4e00-\u9fff]+", "_", Path(name).name).strip("._")
    return cleaned or "uploaded_file"


def _guest_session_id() -> str:
    if "guest_session_id" not in st.session_state:
        st.session_state["guest_session_id"] = secrets.token_hex(12)
    return str(st.session_state["guest_session_id"])


def _user_upload_dir(user_id: str) -> Path:
    return UPLOAD_STORE / user_id


def _active_upload_dir(user: AuthUser | None) -> Path:
    if user is not None:
        return _user_upload_dir(user.id)
    return GUEST_UPLOAD_STORE / _guest_session_id()


def _is_safe_upload_path(
    path: Path,
    user_id: str | None = None,
    guest_session_id: str | None = None,
) -> bool:
    try:
        if user_id:
            root = _user_upload_dir(user_id).resolve()
        elif guest_session_id:
            root = (GUEST_UPLOAD_STORE / guest_session_id).resolve()
        else:
            root = UPLOAD_STORE.resolve()
        return path.resolve().is_relative_to(root)
    except (OSError, RuntimeError):
        return False


def _upload_validation_error(name: str, size: int) -> str | None:
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        allowed = "、".join(sorted(suffix.lstrip(".").upper() for suffix in ALLOWED_UPLOAD_SUFFIXES))
        return f"{name} 已拒绝：仅支持 {allowed} 文件。"
    if size <= 0:
        return f"{name} 已拒绝：文件为空。"
    if size > MAX_UPLOAD_BYTES:
        return f"{name} 已拒绝：单文件不能超过 {_format_bytes(MAX_UPLOAD_BYTES)}。"
    return None


def _load_legacy_saved_uploads() -> list[dict[str, object]]:
    if not UPLOAD_MANIFEST.exists():
        return []
    try:
        records = json.loads(UPLOAD_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    valid: list[dict[str, object]] = []
    for record in records if isinstance(records, list) else []:
        path = Path(str(record.get("path", "")))
        name = str(record.get("name", path.name))
        size = int(record.get("size") or 0)
        if (
            path.exists()
            and path.is_file()
            and _is_safe_upload_path(path)
            and _upload_validation_error(name, size) is None
        ):
            valid.append(record)
    return valid


def _reset_upload_widget() -> None:
    st.session_state["upload_nonce"] = int(st.session_state.get("upload_nonce", 0)) + 1


def _upload_kind(value: object) -> str:
    kind = str(value or "auto")
    return kind if kind in UPLOAD_KIND_LABELS else "auto"


def _upload_kind_label(value: object) -> str:
    return UPLOAD_KIND_LABELS[_upload_kind(value)]


def _migrate_legacy_uploads_for_user(user: AuthUser) -> None:
    session_key = f"legacy_uploads_migrated_{user.id}"
    if st.session_state.get(session_key):
        return
    store = get_auth_store()
    existing = store.list_uploads(user.id)
    if existing:
        st.session_state[session_key] = True
        return
    for record in _load_legacy_saved_uploads():
        path = Path(str(record.get("path", "")))
        if not path.exists() or not path.is_file():
            continue
        try:
            content = path.read_bytes()
        except OSError:
            continue
        digest = hashlib.sha256(content).hexdigest()[:16]
        target_dir = _user_upload_dir(user.id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{digest}_{_safe_upload_filename(str(record.get('name', path.name)))}"
        if not target.exists():
            target.write_bytes(content)
        store.add_upload(
            user.id,
            str(record.get("name", path.name)),
            str(target),
            int(record.get("size") or target.stat().st_size),
            upload_kind="auto",
        )
    st.session_state[session_key] = True


def _load_guest_uploads() -> list[dict[str, object]]:
    guest_id = _guest_session_id()
    records = st.session_state.get("guest_upload_records", [])
    valid: list[dict[str, object]] = []
    for record in records if isinstance(records, list) else []:
        path = Path(str(record.get("path", "")))
        name = str(record.get("name", path.name))
        size = int(record.get("size") or 0)
        if (
            path.exists()
            and path.is_file()
            and _is_safe_upload_path(path, guest_session_id=guest_id)
            and _upload_validation_error(name, size) is None
        ):
            valid.append({**record, "upload_kind": _upload_kind(record.get("upload_kind"))})
    st.session_state["guest_upload_records"] = valid
    return valid


def _load_saved_uploads(user: AuthUser | None) -> list[dict[str, object]]:
    if user is None:
        return _load_guest_uploads()
    _migrate_legacy_uploads_for_user(user)
    store = get_auth_store()
    records = store.list_uploads(user.id)
    valid: list[dict[str, object]] = []
    for record in records:
        path = Path(str(record.get("path", "")))
        name = str(record.get("name", path.name))
        size = int(record.get("size") or 0)
        if (
            path.exists()
            and path.is_file()
            and _is_safe_upload_path(path, user.id)
            and _upload_validation_error(name, size) is None
        ):
            valid.append({**record, "upload_kind": _upload_kind(record.get("upload_kind"))})
        else:
            store.delete_upload(str(record.get("id", "")), user.id, is_admin=user.is_admin)
    return valid


def _persist_uploads(
    uploaded_files: list[object] | None,
    user: AuthUser | None,
    upload_kind: str,
) -> tuple[list[dict[str, object]], list[str], bool, int]:
    store = get_auth_store() if user is not None else None
    records = _load_saved_uploads(user)
    seen = {str(record.get("name")) + ":" + str(record.get("size")) for record in records}
    errors: list[str] = []
    processed = bool(uploaded_files)
    saved_count = 0
    clean_kind = _upload_kind(upload_kind)
    for uploaded in uploaded_files or []:
        content = uploaded.getvalue()
        original_name = str(uploaded.name)
        validation_error = _upload_validation_error(original_name, len(content))
        if validation_error:
            errors.append(validation_error)
            continue
        digest = hashlib.sha256(content).hexdigest()[:16]
        identity = f"{original_name}:{len(content)}"
        if identity in seen:
            continue
        safe_name = _safe_upload_filename(original_name)
        target_dir = _active_upload_dir(user)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{digest}_{safe_name}"
        counter = 1
        while target.exists():
            target = target_dir / f"{digest}_{counter}_{safe_name}"
            counter += 1
        target.write_bytes(content)
        if user is not None and store is not None:
            records.append(store.add_upload(user.id, original_name, str(target), len(content), upload_kind=clean_kind))
        else:
            records.append({
                "id": secrets.token_hex(16),
                "user_id": "guest",
                "name": original_name,
                "path": str(target),
                "size": len(content),
                "upload_kind": clean_kind,
                "created_at": "",
            })
            st.session_state["guest_upload_records"] = records
        seen.add(identity)
        saved_count += 1
    return _load_saved_uploads(user), errors, processed, saved_count


def _delete_saved_upload(upload_id: str, user: AuthUser | None) -> bool:
    if user is None:
        guest_id = _guest_session_id()
        records = _load_guest_uploads()
        kept: list[dict[str, object]] = []
        deleted = False
        for record in records:
            if str(record.get("id")) != upload_id:
                kept.append(record)
                continue
            path = Path(str(record.get("path", "")))
            if _is_safe_upload_path(path, guest_session_id=guest_id):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            deleted = True
        st.session_state["guest_upload_records"] = kept
        return deleted
    store = get_auth_store()
    record = store.delete_upload(upload_id, user.id, is_admin=user.is_admin)
    if not record:
        return False
    path = Path(str(record.get("path", "")))
    if _is_safe_upload_path(path, str(record.get("user_id", user.id))):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    return True


def _clear_saved_uploads(user: AuthUser | None) -> None:
    if user is None:
        guest_id = _guest_session_id()
        for record in _load_guest_uploads():
            path = Path(str(record.get("path", "")))
            if not _is_safe_upload_path(path, guest_session_id=guest_id):
                continue
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        st.session_state["guest_upload_records"] = []
        return
    store = get_auth_store()
    for record in store.clear_uploads(user.id):
        path = Path(str(record.get("path", "")))
        if not _is_safe_upload_path(path, user.id):
            continue
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _promote_guest_uploads_to_user(user: AuthUser) -> None:
    guest_id = _guest_session_id()
    guest_records = _load_guest_uploads()
    if not guest_records:
        return
    store = get_auth_store()
    existing = {
        str(record.get("name")) + ":" + str(record.get("size"))
        for record in store.list_uploads(user.id)
    }
    for record in guest_records:
        source = Path(str(record.get("path", "")))
        name = str(record.get("name", source.name))
        size = int(record.get("size") or 0)
        if not source.exists() or not _is_safe_upload_path(source, guest_session_id=guest_id):
            continue
        identity = f"{name}:{size}"
        if identity in existing:
            continue
        try:
            content = source.read_bytes()
        except OSError:
            continue
        digest = hashlib.sha256(content).hexdigest()[:16]
        target_dir = _user_upload_dir(user.id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{digest}_{_safe_upload_filename(name)}"
        counter = 1
        while target.exists():
            target = target_dir / f"{digest}_{counter}_{_safe_upload_filename(name)}"
            counter += 1
        target.write_bytes(content)
        store.add_upload(user.id, name, str(target), len(content), upload_kind=_upload_kind(record.get("upload_kind")))
        existing.add(identity)
    _clear_saved_uploads(None)


def _format_bytes(size: object) -> str:
    value = float(size or 0)
    if value >= 1024 * 1024:
        return f"{value / 1024 / 1024:.1f}MB"
    if value >= 1024:
        return f"{value / 1024:.1f}KB"
    return f"{value:.0f}B"


def _file_type_label(name: object) -> str:
    suffix = Path(str(name)).suffix.lower().lstrip(".")
    if suffix == "csv":
        return "CSV"
    if suffix in {"xls", "xlsx"}:
        return "XLS"
    if suffix in {"doc", "docx"}:
        return "DOC"
    return "FILE"


def _saved_file_refs(saved_uploads: list[dict[str, object]]) -> tuple[tuple[str, str, str, int, int, str], ...]:
    refs: list[tuple[str, str, str, int, int, str]] = []
    for record in saved_uploads:
        path = Path(str(record.get("path", "")))
        if not path.exists() or not path.is_file():
            continue
        stat = path.stat()
        refs.append((
            str(record.get("id", "")),
            str(record.get("name", path.name)),
            str(path),
            int(stat.st_size),
            int(stat.st_mtime_ns),
            _upload_kind(record.get("upload_kind")),
        ))
    return tuple(refs)


@st.cache_data(show_spinner=False)
def _load_normalized_file(
    file_id: str,
    filename: str,
    path_str: str,
    size: int,
    mtime_ns: int,
    upload_kind: str,
) -> tuple[pd.DataFrame, dict[str, object] | None, str | None]:
    del file_id, size, mtime_ns
    file_path = Path(path_str)
    try:
        raw = read_sales_file(file_path)
        profile = profile_file(raw, filename)
        profile = {**profile, "upload_kind": _upload_kind(upload_kind), "upload_label": _upload_kind_label(upload_kind)}
        data_type = str(profile["data_type"])
        if _upload_kind(upload_kind) == "purchase":
            data_type = "采购"
            profile["data_type"] = "采购"
        normalized = normalize_sales_data(
            raw,
            default_channel=str(profile["channel"]).strip() or Path(filename).stem,
            mapping=profile["mapping"],
            source_file=filename,
            data_type=data_type,
        )
        return normalized, profile, None
    except Exception as exc:
        return pd.DataFrame(), None, f"{filename} 读取失败：{exc}"


@st.cache_data(show_spinner=False)
def _load_channel_dataset(
    file_refs: tuple[tuple[str, str, str, int, int, str], ...],
    use_sample: bool,
) -> tuple[pd.DataFrame, list[dict[str, object]], list[str], str | None]:
    normalized_frames: list[pd.DataFrame] = []
    profiles: list[dict[str, object]] = []
    errors: list[str] = []

    if file_refs:
        for file_id, filename, path_str, size, mtime_ns, upload_kind in file_refs:
            normalized, profile, error = _load_normalized_file(file_id, filename, path_str, size, mtime_ns, upload_kind)
            if error:
                errors.append(error)
                continue
            normalized_frames.append(normalized)
            if profile is not None:
                profiles.append(profile)
    elif use_sample:
        for path in sorted((ROOT / "data" / "sample").glob("*.csv")):
            stat = path.stat()
            normalized, profile, error = _load_normalized_file(
                f"sample:{path.name}",
                path.name,
                str(path),
                int(stat.st_size),
                int(stat.st_mtime_ns),
                "sales",
            )
            if error:
                errors.append(error)
                continue
            normalized_frames.append(normalized)
            if profile is not None:
                profiles.append({**profile, "channel": path.stem, "data_type": "销售库存"})

    if not normalized_frames:
        return pd.DataFrame(), profiles, errors, None
    try:
        data = combine_normalized_frames(normalized_frames)
    except ValueError as exc:
        return pd.DataFrame(), profiles, errors, str(exc)
    return data, profiles, errors, None


def _handle_uploads(
    uploaded_files: list[object] | None,
    user: AuthUser | None,
    upload_kind: str,
) -> list[dict[str, object]]:
    saved_uploads, upload_errors, processed, saved_count = _persist_uploads(uploaded_files, user, upload_kind)
    if not processed:
        return saved_uploads
    messages: list[tuple[str, str]] = []
    if saved_count:
        st.session_state["use_sample_data"] = False
        messages.append(("success", f"已保存 {saved_count} 个{_upload_kind_label(upload_kind)}文件，正在刷新分析结果。"))
    messages.extend(("warning", message) for message in upload_errors)
    st.session_state["upload_flash_messages"] = messages
    _reset_upload_widget()
    st.rerun()
    return saved_uploads


def _render_upload_flash_messages() -> None:
    messages = st.session_state.pop("upload_flash_messages", [])
    for level, message in messages if isinstance(messages, list) else []:
        if level == "success":
            st.success(str(message))
        elif level == "info":
            st.info(str(message))
        else:
            st.warning(str(message))


def _render_saved_upload_manager(saved_uploads: list[dict[str, object]], user: AuthUser | None) -> None:
    if not saved_uploads:
        empty_note = "暂无保存文件，上传后会保存在账号下。" if user is not None else "暂无临时文件，游客上传不会长期保留。"
        st.markdown(f"<div class='data-intake-empty'>{html.escape(empty_note)}</div>", unsafe_allow_html=True)
        return

    sales_count = sum(_upload_kind(record.get("upload_kind")) == "sales" for record in saved_uploads)
    purchase_count = sum(_upload_kind(record.get("upload_kind")) == "purchase" for record in saved_uploads)
    auto_count = len(saved_uploads) - sales_count - purchase_count
    total_size = sum(int(record.get("size") or 0) for record in saved_uploads)
    st.markdown(
        f"""
        <div class="saved-upload-summary">
          <span>销售 {sales_count}</span>
          <span>采购 {purchase_count}</span>
          <span>自动识别 {auto_count}</span>
          <strong>{len(saved_uploads)} 个文件 · {_format_bytes(total_size)}</strong>
        </div>
        """,
        unsafe_allow_html=True,
    )

    preview_records = saved_uploads[:8]
    rows = []
    for record in preview_records:
        filename = str(record.get("name", "未命名文件"))
        rows.append(
            "<div class='saved-file-line'>"
            f"<span class='saved-file-icon'>{html.escape(_file_type_label(filename))}</span>"
            "<span class='saved-file-meta'>"
            f"<span class='saved-file-name'>{html.escape(filename)}</span>"
            f"<span class='saved-file-size'>{html.escape(_upload_kind_label(record.get('upload_kind')))} · {_format_bytes(record.get('size'))}</span>"
            "</span>"
            "</div>"
        )
    remainder = len(saved_uploads) - len(preview_records)
    more_note = f"<div class='saved-file-more'>另有 {remainder} 个文件在管理区中</div>" if remainder > 0 else ""
    st.markdown(f"<div class='saved-file-list'>{''.join(rows)}{more_note}</div>", unsafe_allow_html=True)

    options = [str(record.get("id")) for record in saved_uploads]
    labels = {
        str(record.get("id")): f"{_upload_kind_label(record.get('upload_kind'))} · {record.get('name')} · {_format_bytes(record.get('size'))}"
        for record in saved_uploads
    }
    with st.expander("管理已保存文件", expanded=False):
        table = pd.DataFrame([
            {
                "类型": _upload_kind_label(record.get("upload_kind")),
                "文件名": record.get("name"),
                "大小": _format_bytes(record.get("size")),
                "上传时间": record.get("created_at") or "当前会话",
            }
            for record in saved_uploads
        ])
        st.dataframe(table, width="stretch", hide_index=True, height=min(360, 42 + 36 * max(len(table), 1)))
        selected_id = st.selectbox(
            "选择要删除的文件",
            options,
            format_func=lambda value: labels.get(str(value), str(value)),
            key="delete-upload-select",
        )
        if st.button("删除所选文件", type="secondary", width="stretch"):
            if _delete_saved_upload(str(selected_id), user):
                _reset_upload_widget()
            st.rerun()


def render_data_intake_panel(saved_uploads: list[dict[str, object]], user: AuthUser | None) -> tuple[list[dict[str, object]], bool]:
    save_note = (
        f"已保存 {len(saved_uploads)} 个上传文件"
        if user is not None
        else f"游客临时文件 {len(saved_uploads)} 个"
    )
    meta_note = (
        "已登录，上传文件会保留在当前账号下。"
        if user is not None
        else "游客可直接分析；登录/注册后才会跨刷新保留上传文件和 Pipeline。"
    )
    st.markdown(
        f"""
        <div class="data-intake-panel">
          <div class="data-intake-head">
            <div>
              <div class="data-intake-title">数据接入</div>
              <div class="data-intake-meta">{html.escape(meta_note)}</div>
            </div>
            <div class="data-intake-save-note">{html.escape(save_note)}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if "upload_nonce" not in st.session_state:
        st.session_state["upload_nonce"] = 0
    _render_upload_flash_messages()
    upload_sales, upload_purchase, controls_right = st.columns([1, 1, .72], gap="large", vertical_alignment="top")
    with upload_sales:
        st.markdown(
            "<div class='upload-kind-heading sales'><span>销售数据</span><small>销量、销售额、库存日报 / 周报 / 月报</small></div>",
            unsafe_allow_html=True,
        )
        sales_uploads = st.file_uploader(
            "上传销售数据 Excel / CSV",
            type=["csv", "xlsx", "xls"],
            accept_multiple_files=True,
            key=f"sales-uploaded-files-{st.session_state['upload_nonce']}",
            label_visibility="collapsed",
        )
        saved_uploads = _handle_uploads(sales_uploads, user, "sales")
    with upload_purchase:
        st.markdown(
            "<div class='upload-kind-heading purchase'><span>采购数据</span><small>采购单、到货、订购数量文件</small></div>",
            unsafe_allow_html=True,
        )
        purchase_uploads = st.file_uploader(
            "上传采购数据 Excel / CSV",
            type=["csv", "xlsx", "xls"],
            accept_multiple_files=True,
            key=f"purchase-uploaded-files-{st.session_state['upload_nonce']}",
            label_visibility="collapsed",
        )
        saved_uploads = _handle_uploads(purchase_uploads, user, "purchase")
        if "use_sample_data" not in st.session_state:
            st.session_state["use_sample_data"] = not bool(saved_uploads)
    with controls_right:
        st.markdown("<div class='data-intake-subtitle'>数据模式</div>", unsafe_allow_html=True)
        use_sample = st.toggle("使用示例数据", key="use_sample_data")
        if saved_uploads and st.button("清除已保存文件", type="secondary", width="stretch"):
            _clear_saved_uploads(user)
            _reset_upload_widget()
            st.rerun()

    _render_saved_upload_manager(saved_uploads, user)
    return saved_uploads, bool(use_sample)


def format_table(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in ("sales_amount",):
        if column in result:
            numeric_values = pd.to_numeric(result[column], errors="coerce")
            if numeric_values.notna().any():
                result[column] = numeric_values.round(2)
    for column in ("qty_share", "qty_change", "sales_change", "purchase_sales_ratio"):
        if column in result:
            signed = column in {"qty_change", "sales_change"}
            result[column] = result[column].map(
                lambda value: format_percent_cell(value, signed=signed)
            )
    return result.rename(columns={
        "date": "日期",
        "channel": "渠道",
        "source_file": "来源文件",
        "data_type": "数据类型",
        "sku_id": "SKU 编码",
        "sku_name": "商品名称",
        "city": "城市/区域",
        "store": "门店",
        "sales_qty": "销量",
        "sales_amount": "销售额",
        "purchase_qty": "采购数量",
        "purchase_sales_ratio": "采销比",
        "purchase_sales_gap": "采购-销售差额",
        "stock_qty": "库存",
        "latest_stock": "最新库存",
        "previous_sales_qty": "上期销量",
        "yoy_sales_qty": "去年同期销量",
        "yoy_sales_amount": "去年同期销售额",
        "avg_sales_qty": "历史日均销量",
        "qty_share": "销量占比",
        "qty_change": "销量变化",
        "yoy_qty_change": "销量同比变化",
        "sales_change": "销量变化",
        "sku_count": "SKU 数",
        "city_count": "城市数",
        "active_days": "有效天数",
        "issue": "问题",
        "action": "建议动作",
    })


def format_percent_cell(value: object, *, signed: bool = False) -> object:
    if pd.isna(value):
        return ""
    numeric_value = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric_value):
        return value
    return f"{numeric_value:+.1%}" if signed else f"{numeric_value:.1%}"


def render_trend(frame: pd.DataFrame, dimension: str, metric: str, height: int = 320) -> None:
    selected_metric, note = choose_available_metric(frame, metric)
    if note:
        st.caption(note)
    chart = trend_chart(frame, dimension, selected_metric, height)
    if chart is None:
        st.info("当前筛选条件下暂无可绘制数据，请检查字段映射、日期范围或渠道筛选。")
        return
    st.altair_chart(chart, width="stretch")


def render_bar(
    frame: pd.DataFrame,
    category: str,
    metric: str,
    height: int = 300,
    *,
    limit: int = 12,
    drop_zero: bool = False,
    compact: bool = False,
) -> None:
    selected_metric, note = choose_available_metric(frame, metric)
    if note:
        st.caption(note)
    if selected_metric == "stock_qty":
        frame = latest_inventory_rows(frame)
    if frame.empty or category not in frame or selected_metric not in frame:
        st.info("当前筛选条件下暂无可比较数据。")
        return
    chart_data = frame[[category, selected_metric]].copy()
    chart_data[category] = chart_data[category].fillna("").astype(str).str.strip()
    category_label = {"channel": "渠道", "sku_name": "商品", "city": "城市/区域"}.get(category, "分类")
    chart_data.loc[chart_data[category] == "", category] = f"未识别{category_label}"
    chart_data[selected_metric] = pd.to_numeric(chart_data[selected_metric], errors="coerce").fillna(0)
    chart_data = (
        chart_data.groupby(category, as_index=False, dropna=False)[selected_metric]
        .sum()
        .sort_values(selected_metric, ascending=False)
    )
    if drop_zero:
        chart_data = chart_data[chart_data[selected_metric].abs() > 0]
    chart_data = chart_data.head(limit)
    if chart_data.empty:
        st.info("当前筛选条件下暂无可比较数据。")
        return
    max_value = max(float(chart_data[selected_metric].abs().max()), 1.0)
    colors = ["#4338A8", "#6558C7", "#8A7FDB", "#20A884", "#D69A3A", "#A6A0D8", "#6F7180", "#B8796A"]
    rows = []
    for index, row in enumerate(chart_data.itertuples(index=False, name=None)):
        label, value = str(row[0]), float(row[1])
        width = max(abs(value) / max_value * 100, 0)
        safe_label = html.escape(label)
        rows.append(
            f'<div class="bar-row" title="{safe_label}：{value:,.0f}">'
            f'<div class="bar-label">{safe_label}</div>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{width:.2f}%;background:{colors[index % len(colors)]}"></div></div>'
            f'<div class="bar-value">{value:,.0f}</div></div>'
        )
    compact_class = " compact" if compact else ""
    st.markdown(f'<div class="bar-list{compact_class}">{"".join(rows)}</div>', unsafe_allow_html=True)


def render_table(frame: pd.DataFrame, empty_message: str) -> None:
    if frame.empty:
        st.markdown(f'<div class="section-note">{empty_message}</div>', unsafe_allow_html=True)
        return
    st.dataframe(format_table(frame), width="stretch", hide_index=True)


@st.cache_data(ttl=1800, show_spinner=False)
def cached_regional_weather() -> tuple[list[dict[str, object]], list[str]]:
    return fetch_regional_weather()


def amount_display(frame: pd.DataFrame) -> str:
    if frame.empty or frame["sales_amount"].abs().sum() == 0:
        return "未提供"
    return f"¥{frame['sales_amount'].sum():,.0f}"


def amount_coverage(frame: pd.DataFrame) -> tuple[int, int]:
    if frame.empty:
        return 0, 0
    by_channel = frame.groupby("channel")["sales_amount"].apply(lambda values: values.abs().sum() > 0)
    return int(by_channel.sum()), int(len(by_channel))


def report_period_options(frame: pd.DataFrame, report_type: str) -> list[pd.Timestamp]:
    dates = pd.Series(pd.to_datetime(frame["date"].dropna()))
    if dates.empty:
        return []
    start = pd.Timestamp(dates.min()).normalize()
    end = pd.Timestamp(dates.max()).normalize()
    if report_type == "daily":
        periods = list(pd.date_range(start, end, freq="D"))
    elif report_type == "weekly":
        week_start = start - pd.Timedelta(days=start.weekday())
        week_end = end - pd.Timedelta(days=end.weekday())
        periods = list(pd.date_range(week_start, week_end, freq="7D"))
    elif report_type == "monthly":
        periods = list(pd.period_range(start, end, freq="M").to_timestamp())
    else:
        periods = sorted((pd.Timestamp(value).normalize() for value in dates.unique()), reverse=True)
    periods = sorted((pd.Timestamp(value).normalize() for value in periods), reverse=True)
    deduped: list[pd.Timestamp] = []
    seen_labels: set[str] = set()
    for value in periods:
        label = format_report_period_option(value, report_type)
        if label in seen_labels:
            continue
        seen_labels.add(label)
        deduped.append(value)
    return deduped


def format_report_period_option(value: pd.Timestamp, report_type: str) -> str:
    start, end, _, _ = report_period(report_type, value)
    if report_type == "daily":
        return f"{start:%Y-%m-%d}"
    if report_type == "weekly":
        return f"{start:%Y-%m-%d} 至 {end:%Y-%m-%d}"
    return f"{start:%Y年%m月}（{start:%m-%d} 至 {end:%m-%d}）"


NAV_ITEMS = ["经营总览", "渠道对比", "SKU 分析", "销售 Pipeline", "报告中心", "数据质量"]
ADMIN_NAV_ITEM = "用户管理"

PIPELINE_FIELDS = [
    ("Account / Company", "客户公司", "某智能硬件公司 / 盒马鲜生"),
    ("Contact Person", "联系人", "采购经理 / 产品经理"),
    ("Lead Source", "线索来源", "渠道复购 / 展会 / LinkedIn / 转介绍"),
    ("Stage", "当前销售阶段", "初步沟通 / 技术交流 / 测试 / 报价 / 谈判"),
    ("Deal Size", "预计订单金额", "RMB 500,000"),
    ("Probability", "成交概率", "30% / 50% / 80%"),
    ("Expected Close Date", "预计成交日期", "2026-07-30"),
    ("Pain Point", "客户痛点", "现有成本高 / 供货不稳定 / 动销集中"),
    ("Decision Maker", "决策人", "总经理 / 采购负责人"),
    ("Next Step", "下一步动作", "安排技术会议 / 跟进样品反馈"),
    ("Risk", "风险点", "价格高于竞品 / 审批周期长 / 技术未完成"),
    ("Status Update", "最新进展", "已完成样品测试，等待反馈"),
]
PIPELINE_DISPLAY_COLUMNS = {field: label for field, label, _ in PIPELINE_FIELDS}
PIPELINE_INTERNAL_COLUMNS = {label: field for field, label, _ in PIPELINE_FIELDS}
PIPELINE_DISPLAY_ORDER = [label for _, label, _ in PIPELINE_FIELDS]
PIPELINE_STAGE_ORDER = ["初步沟通", "技术交流", "测试", "报价", "谈判", "合同/采购", "成交", "流失"]
PIPELINE_DEFAULT_ROWS = [
    {
        "Account / Company": "盒马鲜生",
        "Contact Person": "采购经理",
        "Lead Source": "渠道复购",
        "Stage": "谈判",
        "Deal Size": 128000,
        "Probability": 0.78,
        "Expected Close Date": "2026-06-28",
        "Pain Point": "重点 SKU 补货节奏不稳定",
        "Decision Maker": "采购负责人",
        "Next Step": "确认下周采购单与仓配计划",
        "Risk": "价格审批延迟",
        "Status Update": "已对齐采购 SKU，待确认排期",
    },
    {
        "Account / Company": "小象超市",
        "Contact Person": "酒水品类",
        "Lead Source": "月度复盘",
        "Stage": "报价",
        "Deal Size": 86000,
        "Probability": 0.62,
        "Expected Close Date": "2026-07-05",
        "Pain Point": "城市覆盖增长但动销 SKU 集中",
        "Decision Maker": "品类负责人",
        "Next Step": "提交组合装试销方案",
        "Risk": "试销城市未定",
        "Status Update": "已完成销量复盘，等待报价反馈",
    },
    {
        "Account / Company": "叮咚买菜",
        "Contact Person": "平台招商",
        "Lead Source": "新客拓展",
        "Stage": "初步沟通",
        "Deal Size": 52000,
        "Probability": 0.38,
        "Expected Close Date": "2026-07-18",
        "Pain Point": "缺少稳定供货证明",
        "Decision Maker": "平台招商负责人",
        "Next Step": "补齐供货资质与报价",
        "Risk": "准入审核周期较长",
        "Status Update": "已建立联系人，待补齐资质材料",
    },
]


def default_pipeline_frame() -> pd.DataFrame:
    return pd.DataFrame(PIPELINE_DEFAULT_ROWS, columns=[field for field, _, _ in PIPELINE_FIELDS])


def empty_pipeline_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=[field for field, _, _ in PIPELINE_FIELDS])


def normalize_pipeline_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
    result = frame.copy() if frame is not None else default_pipeline_frame()
    if result.empty:
        return empty_pipeline_frame()
    if "Contact" in result.columns and "Contact Person" not in result.columns:
        result["Contact Person"] = result["Contact"]
    for column, _, _ in PIPELINE_FIELDS:
        if column not in result.columns:
            result[column] = ""
    result = result[[column for column, _, _ in PIPELINE_FIELDS]].copy()
    result["Deal Size"] = pd.to_numeric(result["Deal Size"], errors="coerce").fillna(0.0)
    probability = pd.to_numeric(result["Probability"], errors="coerce").fillna(0.0)
    if probability.max() > 1:
        probability = probability / 100
    result["Probability"] = probability.clip(0, 1)
    result["Expected Close Date"] = pd.to_datetime(result["Expected Close Date"], errors="coerce").dt.date
    text_columns = [column for column, _, _ in PIPELINE_FIELDS if column not in {"Deal Size", "Probability", "Expected Close Date"}]
    for column in text_columns:
        result[column] = result[column].fillna("").astype(str)
    meaningful_text = result[text_columns].apply(lambda column: column.str.strip().ne(""))
    meaningful_numeric = result[["Deal Size", "Probability"]].abs().sum(axis=1).ne(0)
    meaningful_date = pd.to_datetime(result["Expected Close Date"], errors="coerce").notna()
    result = result[meaningful_text.any(axis=1) | meaningful_numeric | meaningful_date].reset_index(drop=True)
    if result.empty:
        return empty_pipeline_frame()
    return result


def _user_state_key(name: str, user: AuthUser | None) -> str:
    return f"{name}_{user.id}" if user is not None else f"{name}_guest"


def _serializable_pipeline_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    result = frame.copy()
    result["Expected Close Date"] = result["Expected Close Date"].map(
        lambda value: "" if pd.isna(value) else str(value)
    )
    return result.to_dict("records")


def _load_pipeline_records_for_user(user: AuthUser | None) -> list[dict[str, object]]:
    if user is None:
        return default_pipeline_frame().to_dict("records")
    raw = get_auth_store().get_user_setting(user.id, "pipeline_records")
    if not raw:
        return default_pipeline_frame().to_dict("records")
    try:
        records = json.loads(raw)
    except json.JSONDecodeError:
        return default_pipeline_frame().to_dict("records")
    return records if isinstance(records, list) else default_pipeline_frame().to_dict("records")


def get_pipeline_frame(user: AuthUser | None) -> pd.DataFrame:
    state_key = _user_state_key("pipeline_records", user)
    if state_key not in st.session_state:
        st.session_state[state_key] = _load_pipeline_records_for_user(user)
    return normalize_pipeline_frame(pd.DataFrame(st.session_state[state_key]))


def save_pipeline_frame(user: AuthUser | None, frame: pd.DataFrame) -> None:
    records = _serializable_pipeline_records(frame)
    st.session_state[_user_state_key("pipeline_records", user)] = records
    if user is not None:
        get_auth_store().set_user_setting(user.id, "pipeline_records", json.dumps(records, ensure_ascii=False))


def get_include_pipeline_setting(user: AuthUser | None) -> bool:
    state_key = _user_state_key("include_pipeline_in_reports", user)
    if state_key in st.session_state:
        return bool(st.session_state[state_key])
    value = False
    if user is not None:
        raw = get_auth_store().get_user_setting(user.id, "include_pipeline_in_reports")
        value = raw == "true"
    st.session_state[state_key] = value
    return value


def persist_include_pipeline_setting(user: AuthUser | None, value: bool) -> None:
    if user is not None:
        get_auth_store().set_user_setting(user.id, "include_pipeline_in_reports", "true" if value else "false")


def pipeline_report_records(user: AuthUser | None) -> list[dict[str, object]]:
    return _serializable_pipeline_records(get_pipeline_frame(user))


def promote_guest_state_if_needed(user: AuthUser | None) -> None:
    if user is None:
        return
    if st.session_state.get("promote_guest_state_to_user_id") != user.id:
        return
    _promote_guest_uploads_to_user(user)
    guest_pipeline_key = _user_state_key("pipeline_records", None)
    if guest_pipeline_key in st.session_state:
        save_pipeline_frame(user, normalize_pipeline_frame(pd.DataFrame(st.session_state[guest_pipeline_key])))
        st.session_state.pop(guest_pipeline_key, None)
    guest_include_key = _user_state_key("include_pipeline_in_reports", None)
    if guest_include_key in st.session_state:
        st.session_state[_user_state_key("include_pipeline_in_reports", user)] = bool(st.session_state[guest_include_key])
        persist_include_pipeline_setting(user, bool(st.session_state[guest_include_key]))
        st.session_state.pop(guest_include_key, None)
    st.session_state.pop("promote_guest_state_to_user_id", None)


def render_pipeline_cards(frame: pd.DataFrame) -> None:
    open_frame = frame[~frame["Stage"].isin(["成交", "流失"])].copy()
    open_amount = float(open_frame["Deal Size"].sum())
    weighted_amount = float((open_frame["Deal Size"] * open_frame["Probability"]).sum())
    high_risk_count = int(open_frame["Risk"].astype(str).str.strip().ne("").sum())
    upcoming = open_frame[
        pd.to_datetime(open_frame["Expected Close Date"], errors="coerce")
        .between(pd.Timestamp.today().normalize(), pd.Timestamp.today().normalize() + pd.Timedelta(days=30))
    ]
    card_html = f"""
    <div class="pipeline-grid">
      <div class="pipeline-card"><div class="label">开放商机</div><div class="value">{len(open_frame):,}</div><div class="hint">未成交 / 未流失</div></div>
      <div class="pipeline-card"><div class="label">预计订单金额</div><div class="value">¥{open_amount:,.0f}</div><div class="hint">按开放商机合计</div></div>
      <div class="pipeline-card"><div class="label">加权预测金额</div><div class="value">¥{weighted_amount:,.0f}</div><div class="hint">金额 × 成交概率</div></div>
      <div class="pipeline-card"><div class="label">30 天内预计成交</div><div class="value">{len(upcoming):,}</div><div class="hint">需优先跟进 · 风险 {high_risk_count} 条</div></div>
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)


def render_pipeline_module(user: AuthUser | None) -> None:
    st.subheader("销售 Pipeline")
    st.caption("维护重点客户、销售阶段、预计金额、成交概率和下一步动作；可选择是否写入日报、周报、月报。")
    pipeline_frame = get_pipeline_frame(user)
    include_key = _user_state_key("include_pipeline_in_reports", user)
    if include_key not in st.session_state:
        st.session_state[include_key] = get_include_pipeline_setting(user)
    include_pipeline = st.toggle(
        "将销售 Pipeline 写入日报 / 周报 / 月报",
        key=include_key,
        help="关闭后，报告只输出销售、采购、库存和异常分析，不显示 Pipeline 章节。",
    )
    persist_include_pipeline_setting(user, bool(include_pipeline))
    render_pipeline_cards(pipeline_frame)
    editor_display = pipeline_frame.rename(columns=PIPELINE_DISPLAY_COLUMNS)
    editor_display.insert(0, "删除", False)
    with st.form("pipeline-editor-form", clear_on_submit=False):
        edited = st.data_editor(
            editor_display,
            width="stretch",
            height=210,
            hide_index=True,
            num_rows="dynamic",
            column_order=["删除", *PIPELINE_DISPLAY_ORDER],
            column_config={
                "删除": st.column_config.CheckboxColumn("删除", help="勾选后点击保存会删除该行"),
                "销售阶段": st.column_config.SelectboxColumn("销售阶段", options=PIPELINE_STAGE_ORDER),
                "预计订单金额": st.column_config.NumberColumn("预计订单金额", min_value=0, step=1000, format="¥%d"),
                "成交概率": st.column_config.NumberColumn("成交概率", min_value=0.0, max_value=1.0, step=0.05, format="%.0%"),
                "预计成交日期": st.column_config.DateColumn("预计成交日期"),
            },
            key="pipeline-editor",
        )
        saved = st.form_submit_button("保存 Pipeline")
    if saved:
        edited_frame = edited.copy()
        if "删除" in edited_frame.columns:
            delete_mask = edited_frame["删除"].fillna(False).astype(bool)
            edited_frame = edited_frame.loc[~delete_mask].drop(columns=["删除"])
        edited_frame = edited_frame.rename(columns=PIPELINE_INTERNAL_COLUMNS)
        normalized = normalize_pipeline_frame(edited_frame)
        save_pipeline_frame(user, normalized)
        st.success("Pipeline 已保存。")
        st.rerun()
    normalized = pipeline_frame

    with st.container(border=True):
        st.markdown("**阶段金额分布**")
        stage_frame = (
            normalized.groupby("Stage", as_index=False)
            .agg(Deal_Size=("Deal Size", "sum"), Count=("Stage", "size"))
        )
        stage_frame["Stage"] = pd.Categorical(stage_frame["Stage"], categories=PIPELINE_STAGE_ORDER, ordered=True)
        stage_frame = stage_frame.sort_values("Stage").rename(columns={"Stage": "阶段", "Deal_Size": "预计金额", "Count": "商机数"})
        stage_frame = stage_frame[stage_frame["预计金额"] > 0]
        if stage_frame.empty:
            st.info("当前 Pipeline 暂无预计金额。")
        else:
            max_amount = max(float(stage_frame["预计金额"].max()), 1.0)
            colors = ["#4338A8", "#6558C7", "#8A7FDB", "#20A884", "#D69A3A"]
            stage_rows = []
            for index, (_, row) in enumerate(stage_frame.iterrows()):
                amount = float(row["预计金额"])
                width = amount / max_amount * 100
                label = html.escape(str(row["阶段"]))
                count = int(row["商机数"])
                stage_rows.append(
                    f'<div class="bar-row" title="{label}：¥{amount:,.0f}">'
                    f'<div class="bar-label">{label}<br><small>{count} 个商机</small></div>'
                    f'<div class="bar-track"><div class="bar-fill" style="width:{width:.2f}%;background:{colors[index % len(colors)]}"></div></div>'
                    f'<div class="bar-value">¥{amount:,.0f}</div></div>'
                )
            st.markdown(f"<div class='bar-list'>{''.join(stage_rows)}</div>", unsafe_allow_html=True)

    st.subheader("本周跟进行动")
    action_rows = normalized[
        ~normalized["Stage"].isin(["成交", "流失"])
    ][[
        "Account / Company",
        "Stage",
        "Deal Size",
        "Probability",
        "Expected Close Date",
        "Next Step",
        "Risk",
        "Status Update",
    ]].copy()
    action_rows["Deal Size"] = action_rows["Deal Size"].map(lambda value: f"¥{value:,.0f}")
    action_rows["Probability"] = action_rows["Probability"].map(lambda value: f"{value:.0%}")
    st.dataframe(
        action_rows.rename(columns={
            "Account / Company": "客户公司",
            "Stage": "阶段",
            "Deal Size": "预计金额",
            "Probability": "成交概率",
            "Expected Close Date": "预计成交日期",
            "Next Step": "下一步动作",
            "Risk": "风险点",
            "Status Update": "最新进展",
        }),
        width="stretch",
        hide_index=True,
    )


def render_admin_module(user: AuthUser) -> None:
    if not user.is_admin:
        st.error("当前账号没有管理员权限。")
        return
    store = get_auth_store()
    st.subheader("用户管理")
    st.caption("管理员可查看账号、角色、注册时间、最近登录和上传文件概览。")

    users = pd.DataFrame(store.list_users())
    if users.empty:
        st.info("暂无用户。")
    else:
        users_display = users.rename(columns={
            "email": "邮箱",
            "name": "姓名 / 公司",
            "role": "角色",
            "created_at": "注册时间",
            "last_login_at": "最近登录",
            "upload_count": "上传文件数",
            "upload_bytes": "上传容量",
        })[["邮箱", "姓名 / 公司", "角色", "注册时间", "最近登录", "上传文件数", "上传容量"]].copy()
        users_display["上传容量"] = users_display["上传容量"].map(_format_bytes)
        st.dataframe(users_display, width="stretch", hide_index=True)

    uploads = pd.DataFrame(store.list_uploads())
    st.subheader("上传文件概览")
    if uploads.empty:
        st.info("暂无上传文件。")
    else:
        uploads_display = uploads.rename(columns={
            "user_email": "用户",
            "name": "文件名",
            "size": "文件大小",
            "created_at": "上传时间",
            "path": "服务器路径",
        })[["用户", "文件名", "文件大小", "上传时间", "服务器路径"]].copy()
        uploads_display["文件大小"] = uploads_display["文件大小"].map(_format_bytes)
        st.dataframe(uploads_display, width="stretch", hide_index=True)


promote_guest_state_if_needed(current_user)


with st.sidebar:
    st.markdown("<div class='sidebar-top-fill'></div>", unsafe_allow_html=True)
    st.markdown("<div class='sidebar-nav-title'>功能导航</div>", unsafe_allow_html=True)
    nav_items = [*NAV_ITEMS, *([ADMIN_NAV_ITEM] if current_user is not None and current_user.is_admin else [])]
    query_module = st.query_params.get("module")
    active_module = query_module if query_module in nav_items else st.session_state.get("active_module", "经营总览")
    if active_module not in nav_items:
        active_module = "经营总览"
    st.session_state["active_module"] = active_module
    for nav_item in nav_items:
        if st.button(
            nav_item,
            key=f"sidebar-nav-{nav_item}",
            type="primary" if nav_item == active_module else "secondary",
            width="stretch",
        ):
            st.session_state["active_module"] = nav_item
            st.query_params["module"] = nav_item
            st.rerun()

auth_label = "注册 / 登录" if current_user is None else ("管理员账号" if current_user.is_admin else "我的账号")
auth_hint = "登录后保存上传和 Pipeline" if current_user is None else html.escape(current_user.email)
st.markdown(
    f"""
    <div class="business-topbar">
      <div class="business-brand">
        <span class="business-brand-mark">渠</span>
        <span>零售渠道经营驾驶舱</span>
        <small>销售与库存分析系统</small>
      </div>
      <div class="business-meta"></div>
    </div>
    """,
    unsafe_allow_html=True,
)
with st.container(key="auth_topbar_controls"):
    if st.button(auth_label, key="topbar-auth-button", help=auth_hint, width="stretch"):
        st.session_state["show_auth_dialog"] = True
        st.rerun()
    st.markdown(f"<div class='topbar-auth-hint'>{html.escape(auth_hint)}</div>", unsafe_allow_html=True)

st.markdown(
    """
    <div class="hero">
      <div>
        <div class="hero-kicker">经营分析工作台</div>
        <h1>渠道销售与库存分析</h1>
      </div>
      <p>统一异构渠道报表，按渠道、来源文件和 SKU 追踪趋势，定位异常并生成可跟进的经营报告。</p>
    </div>
    """,
    unsafe_allow_html=True,
)

if active_module == ADMIN_NAV_ITEM:
    if current_user is None:
        st.warning("请先登录管理员账号。")
    else:
        render_admin_module(current_user)
    st.stop()

saved_uploads = _load_saved_uploads(current_user)
if active_module == "经营总览":
    saved_uploads, use_sample = render_data_intake_panel(saved_uploads, current_user)
else:
    if "use_sample_data" not in st.session_state:
        st.session_state["use_sample_data"] = not bool(saved_uploads)
    use_sample = bool(st.session_state.get("use_sample_data", not bool(saved_uploads)))

data, profiles, load_errors, combine_error = _load_channel_dataset(_saved_file_refs(saved_uploads), use_sample)
for load_error in load_errors:
    st.error(load_error)
if combine_error:
    st.error(combine_error)
    st.info("请检查上传文件是否包含日期、销量、SKU 等必要字段，或删除后重新上传。")
    st.stop()

if data.empty:
    st.info("请在经营总览的数据接入区上传渠道文件，或开启示例数据。")
    st.stop()

warnings = data.attrs.get("warnings", [])
if warnings:
    with st.expander(f"数据口径提醒 · {len(warnings)} 条", expanded=False):
        for warning in warnings:
            st.warning(warning)

min_date, max_date = data["date"].min().date(), data["date"].max().date()
start_date, end_date = min_date, max_date
selected_channels = sorted(data["channel"].unique())
filtered = data.copy()
if filtered.empty:
    st.warning("当前数据为空。请在左侧上传渠道文件，或开启示例数据。")
    st.stop()

kpis = calculate_kpis(filtered)
anomalies = detect_anomalies(filtered)
amount_channels, total_channels = amount_coverage(filtered)

issue_chips = "".join(
    f'<span class="diagnostic-chip">{html.escape(str(issue))} {count} 条</span>'
    for issue, count in anomalies["issue"].value_counts().head(4).items()
) if not anomalies.empty else '<span class="diagnostic-chip">暂无高优先级异常</span>'
st.markdown(
    f"""
    <div class="diagnostic-panel">
      <div class="diagnostic-title"><span class="diagnostic-dot"></span>核心异动指标概览</div>
      <div class="diagnostic-summary">{html.escape(generate_management_summary(filtered, anomalies))}</div>
      <div class="diagnostic-items">{issue_chips}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

metric_columns = st.columns(7)
metric_columns[0].metric("渠道数", kpis["channel_count"])
metric_columns[1].metric("SKU 数", kpis["sku_count"])
metric_columns[2].metric("商品销量", f"{kpis['sales_qty']:,.0f}")
metric_columns[3].metric(
    "销售额" if amount_channels == total_channels else "销售额（部分渠道）",
    amount_display(filtered),
)
metric_columns[4].metric("采购数量", f"{kpis['purchase_qty']:,.0f}")
metric_columns[5].metric("最新库存", f"{kpis['latest_stock']:,.0f}")
metric_columns[6].metric("待跟进异常", len(anomalies))

if amount_channels < total_channels:
    missing_amount_channels = sorted(
        channel
        for channel, values in filtered.groupby("channel")["sales_amount"]
        if values.abs().sum() == 0
    )
    st.info(
        f"销售额口径仅覆盖 {amount_channels}/{total_channels} 个渠道。"
        f"{'、'.join(missing_amount_channels)} 上传的数据没有销售额或售价字段，因此不纳入金额合计。"
    )

if active_module == "经营总览":
    summaries = channel_summary(filtered)
    cards = st.columns(min(max(len(summaries), 1), 4))
    for index, row in enumerate(summaries.head(4).itertuples(index=False)):
        with cards[index]:
            st.markdown(
                f"""
                <div class="channel-card">
                  <div class="name">{row.channel}</div>
                  <div class="big">{row.sales_qty:,.0f} 件</div>
                  <div class="meta">销量占比 {row.qty_share:.1%} · {row.sku_count} 个 SKU<br>采购 {row.purchase_qty:,.0f} · 最新库存 {row.latest_stock:,.0f}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    st.subheader("趋势与结构分析")
    control_left, control_right = st.columns([1, 2])
    with control_left:
        trend_view = st.segmented_control("分析视角", ["渠道", "SKU"], default="渠道")
    with control_right:
        trend_metric = st.segmented_control("趋势指标", ["销量", "销售额", "采购数量", "库存"], default="销量")
    trend_column = {
        "销量": "sales_qty",
        "销售额": "sales_amount",
        "采购数量": "purchase_qty",
        "库存": "stock_qty",
    }[trend_metric or "销量"]
    dimension = {"渠道": "channel", "SKU": "sku_name"}[trend_view or "渠道"]

    trend_filter_left, trend_filter_right = st.columns([1, 2])
    trend_min_date = filtered["date"].min().date()
    trend_max_date = filtered["date"].max().date()
    with trend_filter_left:
        trend_dates = st.date_input(
            "趋势日期范围",
            value=(trend_min_date, trend_max_date),
            min_value=trend_min_date,
            max_value=trend_max_date,
            key="overview-trend-dates",
        )
    trend_sku_options = (
        filtered[["sku_id", "sku_name"]]
        .drop_duplicates()
        .assign(label=lambda frame: frame["sku_name"] + " · " + frame["sku_id"])
        .sort_values("label")
    )
    with trend_filter_right:
        trend_sku_labels = st.multiselect(
            "趋势 SKU（留空展示销量前 8 个）",
            trend_sku_options["label"].tolist(),
            placeholder="选择一个或多个 SKU，左右图表将同步更新",
            key="overview-trend-skus",
        )
    trend_start, trend_end = (
        trend_dates
        if isinstance(trend_dates, tuple) and len(trend_dates) == 2
        else (trend_min_date, trend_max_date)
    )
    trend_filtered = filtered[filtered["date"].dt.date.between(trend_start, trend_end)].copy()
    if trend_sku_labels:
        trend_sku_ids = set(
            trend_sku_options.loc[trend_sku_options["label"].isin(trend_sku_labels), "sku_id"]
        )
        trend_filtered = trend_filtered[trend_filtered["sku_id"].isin(trend_sku_ids)]
    elif trend_filtered["sku_id"].nunique() > 8:
        top_trend_skus = (
            trend_filtered.groupby("sku_id")[trend_column].sum().sort_values(ascending=False).head(8).index
        )
        trend_filtered = trend_filtered[trend_filtered["sku_id"].isin(top_trend_skus)]
        st.caption("SKU 数量较多，左右图表默认展示所选日期范围内销量前 8 个 SKU。")

    chart_frame = trend_filtered
    if dimension == "sku_name" and trend_filtered["sku_name"].nunique() > 8:
        top_skus = (
            trend_filtered.groupby("sku_name")[trend_column].sum().sort_values(ascending=False).head(8).index
        )
        chart_frame = trend_filtered[trend_filtered["sku_name"].isin(top_skus)]
    selected_sales_qty = pd.to_numeric(trend_filtered["sales_qty"], errors="coerce").fillna(0).sum()
    selected_purchase_qty = pd.to_numeric(trend_filtered["purchase_qty"], errors="coerce").fillna(0).sum()
    left, right = st.columns([1.65, .95])
    with left:
        st.markdown("**所选范围趋势**")
        render_trend(chart_frame, dimension, trend_column, 360)
    with right:
        st.markdown(
            f"""
            <div class="trend-summary-grid">
              <div class="trend-summary-card"><div class="label">销量</div><div class="value">{selected_sales_qty:,.0f}</div></div>
              <div class="trend-summary-card"><div class="label">销售额</div><div class="value">{amount_display(trend_filtered)}</div></div>
              <div class="trend-summary-card"><div class="label">采购量</div><div class="value">{selected_purchase_qty:,.0f}</div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(f"**所选 SKU 合计{trend_metric or '销量'}**")
        render_bar(
            trend_filtered,
            "sku_name",
            trend_column,
            260,
            limit=7,
            drop_zero=True,
            compact=True,
        )
    detail_left, detail_right = st.columns([1.15, 1])
    with detail_left:
        st.subheader("渠道表现")
        render_table(summaries, "当前筛选条件下暂无渠道表现数据。")
    with detail_right:
        st.subheader("高优先级异常")
        render_table(anomalies.head(15), "当前没有识别到需要立即跟进的高优先级异常。")

elif active_module == "渠道对比":
    if not selected_channels:
        st.info("请至少选择一个渠道。")
    else:
        channel_tabs = st.tabs(selected_channels)
        for channel_name, tab in zip(selected_channels, channel_tabs):
            with tab:
                channel_data = filtered[filtered["channel"] == channel_name]
                channel_kpis = calculate_kpis(channel_data)
                c1, c2, c3, c4, c5 = st.columns(5)
                c1.metric("销量", f"{channel_kpis['sales_qty']:,.0f}")
                c2.metric("销售额", amount_display(channel_data))
                c3.metric("采购数量", f"{channel_kpis['purchase_qty']:,.0f}")
                c4.metric("SKU", channel_kpis["sku_count"])
                c5.metric("最新库存", f"{channel_kpis['latest_stock']:,.0f}")
                render_trend(channel_data, "sku_name", "sales_qty", 280)
                left, right = st.columns(2)
                with left:
                    st.subheader("SKU 销量排名")
                    render_bar(channel_data, "sku_name", "sales_qty", 240)
                    st.subheader("SKU 采购数量排名")
                    render_bar(channel_data, "sku_name", "purchase_qty", 240)
                with right:
                    st.subheader("区域销售表现")
                    city = (
                        channel_data.groupby("city", as_index=False)
                        .agg(sales_qty=("sales_qty", "sum"), sales_amount=("sales_amount", "sum"))
                        .sort_values("sales_qty", ascending=False)
                    )
                    render_bar(channel_data, "city", "sales_qty", 300)
                render_table(
                    sku_summary(channel_data).sort_values("sales_qty", ascending=False)
                    if not channel_data.empty else sku_summary(channel_data),
                    "当前渠道暂无可展示的 SKU 明细。",
                )

elif active_module == "SKU 分析":
    sku_data = sku_summary(filtered)
    if not sku_data.empty:
        sku_data = sku_data.sort_values("sales_qty", ascending=False)
    st.subheader("跨渠道 SKU 表现")
    st.dataframe(format_table(sku_data), width="stretch", hide_index=True)
    if not sku_data.empty:
        selected_sku = st.selectbox(
            "选择 SKU 下钻",
            sku_data["sku_id"].drop_duplicates().tolist(),
            format_func=lambda sku: f"{sku_data.loc[sku_data['sku_id'] == sku, 'sku_name'].iloc[0]} · {sku}",
        )
        detail = filtered[filtered["sku_id"] == selected_sku]
        render_trend(detail, "channel", "sales_qty", 320)
        region_sales = (
            detail.groupby(["channel", "city"], as_index=False)
            .agg(sales_qty=("sales_qty", "sum"), sales_amount=("sales_amount", "sum"))
        )
        region_stock = (
            latest_inventory_rows(detail)
            .groupby(["channel", "city"], as_index=False)["stock_qty"]
            .sum()
            .rename(columns={"stock_qty": "latest_stock"})
        )
        st.dataframe(
            format_table(
                region_sales.merge(region_stock, on=["channel", "city"], how="left")
                .fillna({"latest_stock": 0})
                .sort_values("sales_qty", ascending=False)
            ),
            width="stretch",
            hide_index=True,
        )

elif active_module == "销售 Pipeline":
    render_pipeline_module(current_user)

elif active_module == "报告中心":
    st.subheader("经营报告中心")
    report_type_label = st.segmented_control(
        "报告类型",
        ["日报", "周报", "月报"],
        default="日报",
        selection_mode="single",
    )
    report_type = {"日报": "daily", "周报": "weekly", "月报": "monthly"}[report_type_label or "日报"]
    available_periods = report_period_options(filtered, report_type)
    report_date = st.selectbox(
        {"daily": "选择日期", "weekly": "选择自然周", "monthly": "选择自然月"}[report_type],
        available_periods,
        format_func=lambda value: format_report_period_option(value, report_type),
        key=f"report-period-{report_type}",
    )
    period_start, period_end, previous_start, previous_end = report_period(report_type, report_date)
    yoy_start = period_start - pd.DateOffset(years=1)
    yoy_end = period_end - pd.DateOffset(years=1)
    period_data = filtered[(filtered["date"] >= period_start) & (filtered["date"] <= period_end)]
    covered_days = period_data["date"].nunique()
    expected_days = (period_end - period_start).days + 1
    st.caption(
        f"当前周期：{period_start:%Y-%m-%d} 至 {period_end:%Y-%m-%d}｜"
        f"上一同期：{previous_start:%Y-%m-%d} 至 {previous_end:%Y-%m-%d}｜"
        f"去年同期：{yoy_start:%Y-%m-%d} 至 {yoy_end:%Y-%m-%d}"
    )
    if covered_days < expected_days:
        st.warning(f"该周期共 {expected_days} 天，当前数据仅覆盖 {covered_days} 天，报告将明确标注数据缺口。")
    include_key = _user_state_key("include_pipeline_in_reports", current_user)
    if include_key not in st.session_state:
        st.session_state[include_key] = get_include_pipeline_setting(current_user)
    include_pipeline = st.toggle(
        "将销售 Pipeline 写入本次报告",
        key=include_key,
        help="关闭后，Word 和页面报告不会出现 Pipeline 章节。",
    )
    persist_include_pipeline_setting(current_user, bool(include_pipeline))
    weather_rows, weather_errors = cached_regional_weather()
    automatic_weather_note = format_weather_note(weather_rows)
    st.markdown("**上海 / 苏州自动天气**")
    st.dataframe(pd.DataFrame(weather_rows), width="stretch", hide_index=True)
    for weather_error in weather_errors:
        st.warning(weather_error)
    st.caption("自动天气每 30 分钟更新，并写入报告；强风/台风风险仅作经营提示，需以气象部门预警为准。")
    with st.form("report-context-form", clear_on_submit=False):
        context_left, context_right = st.columns(2)
        with context_left:
            weather_note = st.text_input(
                "天气 / 温度 / 履约影响",
                value=automatic_weather_note,
                placeholder="例如：上海高温 32°C；华北暴雨，可能影响即时零售履约",
                key="report_weather_note",
            )
            holiday_note = st.text_input(
                "节假日 / 特殊日期",
                placeholder="例如：端午前备货期、618 大促、周末、发薪日",
                key="report_holiday_note",
            )
        with context_right:
            activity_note = st.text_input(
                "最近渠道活动 / 价格 / 上架变化",
                placeholder="例如：盒马 6.8-6.10 有满减；小象本周新增城市前置仓；叮咚部分 SKU 下架",
                key="report_activity_note",
            )
        st.form_submit_button("应用报告上下文")
    report_context = {
        "weather_note": weather_note,
        "holiday_note": holiday_note,
        "activity_note": activity_note,
        "include_pipeline": include_pipeline,
    }
    if include_pipeline:
        report_context["pipeline_records"] = pipeline_report_records(current_user)
    report_text = generate_period_report(filtered, report_type, report_date, report_context)
    word_bytes = export_period_report_docx(filtered, report_type, report_date, report_context)
    report_tables = period_report_tables(filtered, report_type, report_date)
    st.download_button(
        f"下载 Word {REPORT_TYPE_LABELS[report_type]}",
        word_bytes,
        file_name=f"渠道销售{REPORT_TYPE_LABELS[report_type]}_{period_start:%Y%m%d}-{period_end:%Y%m%d}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        type="primary",
    )
    st.markdown(
        f"""
        <div>
          <span class="context-chip">报告类型：{REPORT_TYPE_LABELS[report_type]}</span>
          <span class="context-chip">报告周期：{period_start:%Y-%m-%d} 至 {period_end:%Y-%m-%d}</span>
          <span class="context-chip">天气：{weather_note or "未提供"}</span>
          <span class="context-chip">节假日：{holiday_note or "自动识别"}</span>
          <span class="context-chip">渠道活动：{"已填写" if activity_note.strip() else "未提供"}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    previous_data = filtered[(filtered["date"] >= previous_start) & (filtered["date"] <= previous_end)]
    yoy_data = filtered[(filtered["date"] >= yoy_start) & (filtered["date"] <= yoy_end)]
    period_qty = period_data["sales_qty"].sum()
    previous_qty = previous_data["sales_qty"].sum()
    yoy_qty = yoy_data["sales_qty"].sum()
    change_text = f"{(period_qty - previous_qty) / previous_qty:+.1%}" if previous_qty else "无基线"
    yoy_change_text = f"{(period_qty - yoy_qty) / yoy_qty:+.1%}" if yoy_qty else "数据不足"
    report_kpis = st.columns(5)
    report_kpis[0].metric("本期销量", f"{period_qty:,.0f}", change_text)
    report_kpis[1].metric("同比销量", f"{yoy_qty:,.0f}" if yoy_qty else "未提供", yoy_change_text)
    report_kpis[2].metric("本期销售额", amount_display(period_data))
    report_kpis[3].metric("数据覆盖", f"{covered_days}/{expected_days} 天")
    report_kpis[4].metric("待跟进行动", len(report_tables["actions"]))
    report_left, report_right = st.columns([1.35, 1])
    with report_left:
        st.subheader("本期每日走势")
        render_trend(period_data, "channel", "sales_qty", 300)
    with report_right:
        st.subheader("渠道销量对比")
        render_bar(period_data, "channel", "sales_qty", 300)
    st.subheader("行动跟进表")
    st.caption("下载后的 Word 报告已按商务简报格式整理，可直接发给业务方复盘。")
    render_table(report_tables["actions"], "本期没有自动识别到需要跟进的异常动作。")
    with st.expander("查看完整经营分析正文", expanded=False):
        st.markdown('<div class="report-panel">', unsafe_allow_html=True)
        st.markdown(report_text)
        st.markdown("</div>", unsafe_allow_html=True)
    with st.expander("查看报告数据明细"):
        st.markdown("**销量预测**")
        st.dataframe(format_table(report_tables["forecast"]), width="stretch", hide_index=True)
        st.markdown("**渠道对比**")
        st.dataframe(format_table(report_tables["channel"]), width="stretch", hide_index=True)
        st.markdown("**SKU 贡献**")
        st.dataframe(format_table(report_tables["sku"]), width="stretch", hide_index=True)
        st.markdown("**库存风险**")
        st.dataframe(format_table(report_tables["inventory"]), width="stretch", hide_index=True)

elif active_module == "数据质量":
    st.subheader("文件识别结果")
    quality_rows = []
    for profile in profiles:
        quality_rows.append({
            "文件": profile["filename"],
            "上传入口": profile.get("upload_label", "自动识别"),
            "渠道": profile["channel"],
            "类型": profile["data_type"],
            "原始行数": profile["rows"],
            "自动映射字段": profile["mapped_count"],
            "缺失必要字段": "、".join(profile["missing"]) or "无",
        })
    st.dataframe(pd.DataFrame(quality_rows), width="stretch", hide_index=True)
    st.subheader("标准化数据来源")
    source_stats = (
        data.groupby(["source_file", "channel", "data_type"], as_index=False)
        .agg(
            标准化行数=("sku_id", "size"),
            最早日期=("date", "min"),
            最晚日期=("date", "max"),
            SKU数=("sku_id", "nunique"),
        )
    )
    st.dataframe(format_table(source_stats), width="stretch", hide_index=True)
    st.subheader("来源文件与 SKU 覆盖")
    file_sku = (
        data.groupby(["source_file", "channel", "sku_name"], as_index=False)
        .agg(记录数=("sku_id", "size"), 销量=("sales_qty", "sum"), 销售额=("sales_amount", "sum"))
        .sort_values(["source_file", "销量"], ascending=[True, False])
    )
    st.dataframe(file_sku.rename(columns={"source_file": "来源文件", "channel": "渠道", "sku_name": "商品名称"}), width="stretch", hide_index=True)
    st.subheader("标准化数据预览")
    st.dataframe(format_table(data.head(500)), width="stretch", hide_index=True)
    st.download_button(
        "下载全部标准化数据",
        data.to_csv(index=False).encode("utf-8-sig"),
        file_name="normalized_retail_channel_data.csv",
        mime="text/csv",
    )
