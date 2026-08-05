"""Interactive Grant Intelligence Platform dashboard."""

from __future__ import annotations

import io
import json
import re
import sys
from html import escape
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from grant_intelligence.config import PlatformConfig, load_config  # noqa: E402
from grant_intelligence.constants import PALETTE, VALID_STATE_CODES  # noqa: E402
from grant_intelligence.export import Exporter  # noqa: E402
from grant_intelligence.pipeline import GrantIntelligencePipeline, PipelineResult  # noqa: E402
from grant_intelligence.scoring import COMPONENTS  # noqa: E402
from grant_intelligence.visualization import (  # noqa: E402
    asset_distribution,
    category_distribution,
    funders_by_state,
    keyword_frequency,
    priority_breakdown,
)

st.set_page_config(
    page_title="Grant Intelligence Platform",
    page_icon="◎",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      .stApp { background: #F7F9FA; }
      .block-container { padding-top: 2rem; padding-bottom: 4rem; max-width: 1500px; }
      [data-testid="stSidebar"] { background: #EEF3F4; border-right: 1px solid #D7E0E3; }
      [data-testid="stMetric"] {
        background: white; border: 1px solid #DCE4E7; border-radius: 12px;
        padding: 16px 18px; min-height: 118px;
      }
      [data-testid="stMetricLabel"] { color: #51636D; font-weight: 600; }
      [data-testid="stMetricValue"] { color: #18242C; font-variant-numeric: tabular-nums; }
      .hero {
        background: #173E4D; color: white; border-radius: 18px;
        padding: 28px 34px; margin-bottom: 18px;
      }
      .hero h1 { margin: 0 0 8px 0; font-size: 2.25rem; letter-spacing: -0.03em; }
      .hero p { margin: 0; color: #D8E7EC; max-width: 920px; font-size: 1.02rem; }
      .eyebrow { color: #E6BE72; text-transform: uppercase; font-size: .76rem; letter-spacing: .13em; font-weight: 700; }
      .detail-card { background: white; border: 1px solid #DCE4E7; border-radius: 12px; padding: 18px; }
      .small-note { color: #677780; font-size: .84rem; }
      .stTabs [data-baseweb="tab-list"] { gap: 8px; }
      .stTabs [data-baseweb="tab"] { background: white; border-radius: 8px 8px 0 0; padding: 10px 16px; }
    </style>
    """,
    unsafe_allow_html=True,
)

BASE_CONFIG = load_config(ROOT / "config")
EXPORTER = Exporter()
WEIGHT_LABELS = {
    "organization_type": "Organization type",
    "mission_alignment": "Mission alignment",
    "geography": "Geography",
    "asset_size": "Asset size",
    "ntee_alignment": "NTEE alignment",
    "organization_characteristics": "Organization characteristics",
    "semantic_similarity": "Semantic similarity",
}


@st.cache_data(show_spinner=False, max_entries=8)
def run_cached(payloads: tuple[tuple[str, bytes], ...], config_json: str) -> PipelineResult:
    config = PlatformConfig.from_dict(json.loads(config_json))
    sources: list[io.BytesIO] = []
    for name, payload in payloads:
        buffer = io.BytesIO(payload)
        buffer.name = name
        sources.append(buffer)
    return GrantIntelligencePipeline(config).run(sources)


def parse_keywords(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,\n]", value) if part.strip()]


def money(value: float) -> str:
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"${value / 1_000:.0f}K"
    return f"${value:,.0f}"


def config_controls() -> tuple[list[object], PlatformConfig, bool]:
    base_filter = BASE_CONFIG.section("funder_identification")
    base_scoring = BASE_CONFIG.section("scoring")
    base_nlp = BASE_CONFIG.section("nlp")

    st.sidebar.markdown("## Analysis controls")
    st.sidebar.caption("Upload IRS BMF CSVs or explore the packaged synthetic sample.")
    with st.sidebar.form("analysis_controls", clear_on_submit=False):
        uploads = st.file_uploader(
            "IRS BMF CSV files",
            type=["csv"],
            accept_multiple_files=True,
            help="Files are processed in memory and combined before EIN deduplication.",
        )
        use_sample = st.checkbox("Use sample data when no files are uploaded", value=True)

        st.markdown("#### Funder identification")
        minimum_assets = st.number_input(
            "Minimum reported assets ($)",
            min_value=0,
            value=int(base_filter.get("minimum_assets", 0)),
            step=100_000,
        )
        minimum_income = st.number_input(
            "Minimum reported income ($)",
            min_value=0,
            value=int(base_filter.get("minimum_income", 0)),
            step=100_000,
        )
        keyword_text = st.text_area(
            "Funder name keywords",
            value=", ".join(base_filter.get("name_keywords", [])),
            height=112,
            help="Comma- or line-separated. Matching is case-insensitive and uses word boundaries.",
        )

        target_states = st.multiselect(
            "Priority states",
            options=sorted(VALID_STATE_CODES),
            default=base_scoring.get("target_states", []),
        )

        with st.expander("Scoring weights", expanded=False):
            st.caption("Weights are normalized to 100 points automatically.")
            weights: dict[str, float] = {}
            for component in COMPONENTS:
                weights[component] = float(
                    st.slider(
                        WEIGHT_LABELS[component],
                        min_value=0,
                        max_value=40,
                        value=int(base_scoring["weights"].get(component, 0)),
                        step=1,
                    )
                )
        enable_nlp = st.checkbox(
            "Enable TF-IDF mission similarity", value=bool(base_nlp.get("enabled", True))
        )
        submitted = st.form_submit_button("Run analysis", type="primary", width="stretch")

    sources: list[object] = list(uploads or [])
    if not sources and use_sample:
        sources = [ROOT / "examples" / "sample_bmf.csv"]

    overrides = {
        "funder_identification": {
            "minimum_assets": float(minimum_assets),
            "minimum_income": float(minimum_income),
            "name_keywords": parse_keywords(keyword_text),
        },
        "scoring": {"weights": weights, "target_states": target_states},
        "nlp": {"enabled": enable_nlp},
    }
    return sources, BASE_CONFIG.with_overrides(overrides), submitted


def payloads_from_sources(sources: list[object]) -> tuple[tuple[str, bytes], ...]:
    payloads: list[tuple[str, bytes]] = []
    for source in sources:
        if isinstance(source, Path):
            payloads.append((source.name, source.read_bytes()))
        else:
            payloads.append((getattr(source, "name", "uploaded.csv"), source.getvalue()))
    return tuple(payloads)


def apply_view_filters(frame: pd.DataFrame) -> pd.DataFrame:
    st.markdown("### Explore the ranked pipeline output")
    column_search, column_state, column_category, column_priority = st.columns([1.5, 1, 1.2, 1])
    with column_search:
        query = st.text_input("Search organization", placeholder="Name or EIN")
    with column_state:
        states = sorted(value for value in frame["state"].dropna().unique() if value)
        selected_states = st.multiselect("State", states)
    with column_category:
        categories = sorted(frame["primary_mission_category"].dropna().unique())
        selected_categories = st.multiselect("Mission category", categories)
    with column_priority:
        selected_priorities = st.multiselect(
            "Priority", [value for value in ["High", "Medium", "Low", "Reject"] if value in set(frame["priority_level"])]
        )

    filtered = frame.copy()
    if query:
        query_normalized = query.strip().lower()
        filtered = filtered.loc[
            filtered["organization_name"].str.lower().str.contains(query_normalized, regex=False)
            | filtered["ein"].str.contains(query_normalized, regex=False)
        ]
    if selected_states:
        filtered = filtered.loc[filtered["state"].isin(selected_states)]
    if selected_categories:
        filtered = filtered.loc[filtered["primary_mission_category"].isin(selected_categories)]
    if selected_priorities:
        filtered = filtered.loc[filtered["priority_level"].isin(selected_priorities)]
    return filtered


def score_breakdown_figure(record: pd.Series, weights: dict[str, float]) -> go.Figure:
    labels = [WEIGHT_LABELS[component] for component in COMPONENTS]
    values = [float(record.get(f"score_{component}", 0)) for component in COMPONENTS]
    maxima = [float(weights.get(component, 0)) for component in COMPONENTS]
    figure = go.Figure()
    figure.add_trace(
        go.Bar(
            x=maxima,
            y=labels,
            orientation="h",
            marker={"color": "#E2EAED"},
            hovertemplate="Maximum: %{x:.1f}<extra></extra>",
            name="Available points",
        )
    )
    figure.add_trace(
        go.Bar(
            x=values,
            y=labels,
            orientation="h",
            marker={"color": PALETTE["blue"]},
            text=[f"{value:.1f}" for value in values],
            textposition="inside",
            hovertemplate="Awarded: %{x:.2f}<extra></extra>",
            name="Awarded points",
        )
    )
    figure.update_layout(
        barmode="overlay",
        title={"text": "Scoring breakdown<br><sup>Awarded points within each normalized component weight</sup>", "x": 0.01},
        height=380,
        margin={"l": 20, "r": 20, "t": 70, "b": 35},
        paper_bgcolor="white",
        plot_bgcolor="white",
        font={"family": "Inter, Arial, sans-serif", "color": PALETTE["ink"]},
        legend={"orientation": "h", "y": -0.15},
        xaxis={"title": "Points", "range": [0, max(maxima or [1]) * 1.08], "gridcolor": PALETTE["grid"]},
        yaxis={"autorange": "reversed"},
    )
    return figure


st.markdown(
    """
    <div class="hero">
      <div class="eyebrow">Decision support for nonprofit development teams</div>
      <h1>Grant Intelligence Platform</h1>
      <p>Turn raw IRS Business Master File extracts into a transparent, prioritized foundation research queue—without hiding the rules behind the ranking.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

sources, runtime_config, submitted = config_controls()
if not sources:
    st.info("Upload at least one IRS BMF CSV or enable the sample dataset to begin.")
    st.stop()

should_run = submitted or "analysis_result" not in st.session_state
if should_run:
    try:
        with st.spinner("Cleaning, classifying, and ranking organizations…"):
            payloads = payloads_from_sources(sources)
            config_json = json.dumps(runtime_config.to_dict(), sort_keys=True)
            st.session_state.analysis_result = run_cached(payloads, config_json)
            st.session_state.analysis_config = runtime_config.to_dict()
            st.session_state.analysis_sources = [name for name, _ in payloads]
    except Exception as exc:
        st.error(f"The analysis could not be completed: {exc}")
        st.exception(exc)
        st.stop()

result: PipelineResult = st.session_state.analysis_result
ranked = result.ranked_funders
summary = result.summary

filtered = apply_view_filters(ranked)
headline = summary["headline"]
visible_assets = pd.to_numeric(filtered.get("asset_amount", pd.Series(dtype=float)), errors="coerce").sum()

metric_columns = st.columns(5)
metric_columns[0].metric("Organizations processed", f"{headline['organizations_processed']:,}")
metric_columns[1].metric("Likely funders", f"{headline['likely_funders_identified']:,}", f"{headline['qualification_rate']:.1%} qualified")
metric_columns[2].metric("Visible High priority", f"{filtered['priority_level'].eq('High').sum():,}")
metric_columns[3].metric("Visible median score", f"{filtered['final_score'].median():.1f}" if not filtered.empty else "—")
metric_columns[4].metric("Visible reported assets", money(float(visible_assets)))
st.caption(
    f"Run {result.metadata['run_id']} · Sources: {', '.join(st.session_state.analysis_sources)} · "
    f"{len(filtered):,} of {len(ranked):,} ranked funders visible after view filters"
)

overview_tab, ranked_tab, inspector_tab, report_tab = st.tabs(
    ["Overview", "Ranked funders", "Prospect inspector", "Report & export"]
)

with overview_tab:
    chart_left, chart_right = st.columns(2)
    with chart_left:
        st.plotly_chart(funders_by_state(filtered), width="stretch", config={"displayModeBar": False})
    with chart_right:
        st.plotly_chart(priority_breakdown(filtered), width="stretch", config={"displayModeBar": False})
    chart_left, chart_right = st.columns(2)
    with chart_left:
        st.plotly_chart(
            category_distribution(filtered, "primary_mission_category", "Primary mission category"),
            width="stretch",
            config={"displayModeBar": False},
        )
    with chart_right:
        st.plotly_chart(asset_distribution(filtered), width="stretch", config={"displayModeBar": False})
    chart_left, chart_right = st.columns(2)
    with chart_left:
        st.plotly_chart(keyword_frequency(filtered), width="stretch", config={"displayModeBar": False})
    with chart_right:
        st.plotly_chart(
            category_distribution(filtered, "organization_type", "Organization type"),
            width="stretch",
            config={"displayModeBar": False},
        )
    st.plotly_chart(
        category_distribution(filtered, "ntee_code", "NTEE code distribution", top_n=15),
        width="stretch",
        config={"displayModeBar": False},
    )

with ranked_tab:
    st.markdown("#### Ranked research queue")
    st.caption("Exact lookup view; sort columns or select rows for downstream prospect research.")
    display_columns = [
        "rank",
        "organization_name",
        "ein",
        "state",
        "organization_type",
        "primary_mission_category",
        "ntee_code",
        "asset_amount",
        "income_amount",
        "semantic_similarity",
        "final_score",
        "priority_level",
    ]
    st.dataframe(
        filtered.reindex(columns=display_columns),
        width="stretch",
        hide_index=True,
        height=520,
        column_config={
            "asset_amount": st.column_config.NumberColumn("Assets", format="$%,.0f"),
            "income_amount": st.column_config.NumberColumn("Income", format="$%,.0f"),
            "semantic_similarity": st.column_config.NumberColumn("Semantic fit", format="%.3f"),
            "final_score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.1f"),
        },
    )

with inspector_tab:
    if filtered.empty:
        st.info("No prospect is available for inspection under the current filters.")
    else:
        choices = {
            f"#{int(row['rank'])} · {row['organization_name']} · {row['ein']}": index
            for index, row in filtered.iterrows()
        }
        selected_label = st.selectbox("Select a prospect", choices.keys())
        record = filtered.loc[choices[selected_label]]
        display_name = escape(str(record["organization_name"]))
        display_city = escape(str(record["city"]))
        display_state = escape(str(record["state"]))
        display_zip = escape(str(record["zip_code"]))
        display_type = escape(str(record["organization_type"]))
        display_category = escape(str(record["primary_mission_category"]))
        display_ntee = escape(str(record["ntee_code"] or "Not reported"))
        display_reasons = escape(str(record["filter_reasons"])).replace("|", ", ")
        display_terms = escape(str(record["mission_keyword_hits"])).replace("|", ", ") or "None"
        display_quality = escape(str(record["data_quality_flags"])).replace("|", ", ") or "None"
        detail_left, detail_right = st.columns([1, 1.45])
        with detail_left:
            st.markdown(
                f"""
                <div class="detail-card">
                  <div class="eyebrow">{record['priority_level']} priority · Score {record['final_score']:.1f}</div>
                  <h3>{display_name}</h3>
                  <p><strong>EIN</strong> {record['ein']}<br>
                  <strong>Location</strong> {display_city}, {display_state} {display_zip}<br>
                  <strong>Organization type</strong> {display_type}<br>
                  <strong>Mission category</strong> {display_category}<br>
                  <strong>NTEE</strong> {display_ntee}<br>
                  <strong>Assets</strong> {money(float(record['asset_amount'])) if pd.notna(record['asset_amount']) else 'Not reported'}<br>
                  <strong>Income</strong> {money(float(record['income_amount'])) if pd.notna(record['income_amount']) else 'Not reported'}</p>
                  <p class="small-note"><strong>Identification evidence:</strong> {display_reasons}<br>
                  <strong>Matched mission terms:</strong> {display_terms}<br>
                  <strong>Quality flags:</strong> {display_quality}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with detail_right:
            st.plotly_chart(
                score_breakdown_figure(record, result.metadata["effective_weights"]),
                width="stretch",
                config={"displayModeBar": False},
            )
        with st.expander("Raw scoring and classification evidence"):
            evidence_columns = [
                "funder_keyword_hits",
                "mission_keyword_hits",
                "mission_category_scores",
                "semantic_similarity",
                "nlp_method",
                "filter_reasons",
                "score_breakdown",
                "source_file",
                "source_row_number",
            ]
            st.json({column: record.get(column, "") for column in evidence_columns})

with report_tab:
    export_left, export_right = st.columns([1.5, 1])
    with export_left:
        st.markdown(result.report_markdown)
    with export_right:
        st.markdown("#### Download artifacts")
        st.caption("Exports retain score components, evidence columns, source file, and source row number.")
        st.download_button(
            "Download visible ranked funders",
            EXPORTER.csv_bytes(filtered),
            file_name=f"ranked_funders_{result.metadata['run_id']}.csv",
            mime="text/csv",
            width="stretch",
        )
        st.download_button(
            "Download all reviewed organizations",
            EXPORTER.csv_bytes(result.all_records),
            file_name=f"reviewed_organizations_{result.metadata['run_id']}.csv",
            mime="text/csv",
            width="stretch",
        )
        st.download_button(
            "Download analysis report",
            result.report_markdown.encode("utf-8"),
            file_name=f"grant_intelligence_report_{result.metadata['run_id']}.md",
            mime="text/markdown",
            width="stretch",
        )
        st.download_button(
            "Download summary JSON",
            EXPORTER.json_text(result.summary).encode("utf-8"),
            file_name=f"analysis_summary_{result.metadata['run_id']}.json",
            mime="application/json",
            width="stretch",
        )
        st.markdown("#### Scoring contract")
        for component, weight in result.metadata["effective_weights"].items():
            st.write(f"{WEIGHT_LABELS[component]}: **{weight:.1f} points**")
        st.caption("Relative user weights are normalized to exactly 100 points for every run.")
