"""Trek Health — Payer Performance, Fee Schedule Validation & AI ROI Engine.

Two ways to present the same live engine:
  🎞️ Live Slides  - 9 clickable slides for a 5–10 minute screen-share (PageUp / PageDown to navigate)
  🧰 Workbench    - all five analysis tabs at once, for when the interviewer wants to drive

Run:  streamlit run app.py
"""
from __future__ import annotations

import io

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.agent import PRESET_PROMPTS, ask_benchmark_agent, load_skill, policy_risk_table
from src.data_generator import PROSPECT_NAME, PROSPECT_PATH
from src.demo_script import SCRIPT_PATH, SLIDES, build_facts
from src.engine import (FLAG_ORDER, TARGET_FLOOR, TARGET_OPTIONS, TARGET_P50, TARGET_P75, TrekValidationEngine,
                        compute_kpis, load_prospect_csv, pareto_table, sensitivity_matrix)
from src.excel_exporter import SHEET_BENCH, SHEET_DNF, SHEET_EXEC, count_formulas, formula_preview, generate_roi_workbook
from src.formula_audit import WorkbookEvaluator

TEAL = "#0F766E"
TEAL_DARK = "#0A4F4A"
INK = "#10161D"
MUTED = "#5B6670"
GRID = "#E5E9EB"
SEQ_TEAL = ["#EAF6F3", "#B9E1D9", "#6FC0B1", "#2A9787", "#0F766E", "#0A4F4A"]

FLAG_META = {
    "CRITICAL_UNDER_MARKET": {"label": "Critical under (≤ −20%)", "color": "#d03b3b", "symbol": "triangle-down", "icon": "🔻"},
    "MODERATE_UNDER_MARKET": {"label": "Moderate under (−20% to −5%)", "color": "#ec835a", "symbol": "circle", "icon": "🔸"},
    "COMPETITIVE_BAND": {"label": "Competitive (±5%)", "color": TEAL, "symbol": "square", "icon": "⚖️"},
    "ABOVE_MARKET": {"label": "Above market (> +5%)", "color": "#0ca30c", "symbol": "triangle-up", "icon": "🔺"},
}

st.set_page_config(page_title="Trek Health · Validation & ROI Engine", page_icon="🩺", layout="wide",
                   initial_sidebar_state="collapsed")

CSS = f"""
<style>
html, body, [class*="css"], .stMarkdown, .stText {{
  font-family: "IBM Plex Sans", "Inter", "Segoe UI", system-ui, -apple-system, sans-serif;
}}
code, pre {{ font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace; }}
.block-container {{ padding-top: 3.4rem; padding-bottom: 2rem; max-width: 1500px; }}
#MainMenu, footer, [data-testid="stAppDeployButton"] {{ visibility: hidden; display: none; }}
.trek-kicker {{ color: {TEAL}; font-weight: 700; letter-spacing: .12em; font-size: .78rem; text-transform: uppercase; }}
.trek-title {{ color: {INK}; font-size: 2.05rem; font-weight: 700; line-height: 1.2; margin: .15rem 0 .5rem 0; }}
.trek-takeaway {{ background: #EAF6F3; border-left: 5px solid {TEAL}; color: {INK}; padding: .65rem 1rem;
  border-radius: 6px; font-size: 1.05rem; margin-bottom: 1rem; }}
.trek-hero {{ background: linear-gradient(120deg, {TEAL_DARK} 0%, {TEAL} 70%); color: #fff; border-radius: 12px;
  padding: 1.1rem 1.4rem; margin-bottom: 1rem; }}
.trek-hero h2 {{ color: #fff; margin: 0 0 .3rem 0; font-size: 1.45rem; }}
.trek-hero p {{ color: #E6F4F1; margin: 0; font-size: 1rem; }}
.kpi {{ background: #fff; border: 1px solid {GRID}; border-radius: 10px; padding: .75rem .9rem; height: 100%; }}
.kpi .lbl {{ color: {MUTED}; font-size: .78rem; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; }}
.kpi .val {{ color: {INK}; font-size: 1.65rem; font-weight: 700; line-height: 1.25; margin-top: .15rem; }}
.kpi .sub {{ color: {MUTED}; font-size: .82rem; margin-top: .1rem; }}
.kpi.accent {{ border-top: 4px solid {TEAL}; }}
.step-row {{ display: flex; gap: .6rem; align-items: stretch; margin: .4rem 0 1rem 0; }}
.step {{ flex: 1; background: #fff; border: 1px solid {GRID}; border-top: 4px solid {TEAL}; border-radius: 10px; padding: .8rem; }}
.step .n {{ color: {TEAL}; font-weight: 700; font-size: .8rem; }}
.step .t {{ color: {INK}; font-weight: 700; font-size: 1.05rem; margin: .1rem 0 .3rem 0; }}
.step .d {{ color: {MUTED}; font-size: .86rem; }}
.step .w {{ color: {TEAL_DARK}; font-size: .8rem; margin-top: .4rem; font-weight: 600; }}
.arrow {{ align-self: center; color: {TEAL}; font-size: 1.4rem; }}
.notes {{ background: #FFF9EB; border: 1px dashed #E2B54A; border-radius: 8px; padding: .8rem 1rem; margin-top: 1rem; }}
.badge {{ display: inline-block; padding: .15rem .55rem; border-radius: 999px; font-size: .78rem; font-weight: 600; }}
.badge.ok {{ background: #E3F5E3; color: #075E07; }}
.badge.live {{ background: #E6F0FF; color: #123E8C; }}
.badge.off {{ background: #F1F3F4; color: #3C4650; }}
.arch {{ background: #F7FAF9; border: 1px solid {GRID}; border-radius: 10px; padding: .9rem; }}
.arch .layer {{ display: flex; gap: .7rem; align-items: center; background: #fff; border: 1px solid {GRID};
  border-left: 4px solid {TEAL}; border-radius: 8px; padding: .5rem .7rem; flex: 1; }}
.arch .tag {{ background: {TEAL}; color: #fff; font-weight: 700; border-radius: 6px; padding: .2rem .45rem; font-size: .8rem; }}
.arch .lt {{ font-weight: 700; color: {INK}; }}
.arch .lb {{ color: {MUTED}; font-size: .86rem; }}
.arch .split {{ display: flex; gap: .6rem; }}
.arch .down {{ text-align: center; color: {TEAL}; font-size: .8rem; line-height: 1.1rem; }}
.arch .foot {{ color: {MUTED}; font-size: .8rem; margin-top: .6rem; text-align: center; }}
.slide-counter {{ color: {MUTED}; font-size: .85rem; text-align: center; }}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# =========================================================================== formatting helpers
def usd(x: float) -> str:
    return f"${x:,.0f}"


def usd_short(x: float) -> str:
    if abs(x) >= 1_000_000:
        return f"${x / 1_000_000:.2f}M"
    if abs(x) >= 1_000:
        return f"${x / 1_000:.0f}K"
    return f"${x:,.0f}"


def short_payer(p: str) -> str:
    return "UHC" if str(p).startswith("UnitedHealthcare") else str(p)


def flag_label(flag: str) -> str:
    m = FLAG_META.get(flag)
    return f"{m['icon']} {m['label']}" if m else flag


def esc(text: str) -> str:
    """Escape $ so Streamlit markdown doesn't render dollar pairs as LaTeX."""
    return text.replace("$", "\\$")


def esc_html(text: str) -> str:
    """Same as esc() for raw-HTML blocks, where a backslash would render literally."""
    return text.replace("$", "&#36;")


def kpi_tile(label: str, value: str, sub: str = "", accent: bool = False) -> str:
    return esc_html(f'<div class="kpi{" accent" if accent else ""}"><div class="lbl">{label}</div>'
               f'<div class="val">{value}</div><div class="sub">{sub}</div></div>')


def base_layout(fig: go.Figure, height: int = 420, **kw) -> go.Figure:
    fig.update_layout(
        height=height, paper_bgcolor="white", plot_bgcolor="white",
        font=dict(family="IBM Plex Sans, Inter, Segoe UI, sans-serif", color=INK, size=13),
        margin=dict(l=10, r=10, t=40, b=10), hoverlabel=dict(bgcolor="white", font_size=13),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, font=dict(size=12)),
        **kw,
    )
    fig.update_xaxes(gridcolor=GRID, zerolinecolor=GRID, linecolor="#C9D1D5")
    fig.update_yaxes(gridcolor=GRID, zerolinecolor=GRID, linecolor="#C9D1D5")
    return fig


PLOTLY_CONFIG = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]}


# =========================================================================== state
def init_state() -> None:
    ss = st.session_state
    ss.setdefault("cfg", {
        "target": TARGET_P50, "realization": 0.50, "include_dnf": True, "subscription": 85_000.0,
        "floor_pct": 195.0, "payers": None, "service_lines": None,
    })
    ss.setdefault("dnf_overrides", {})
    ss.setdefault("agent_last", None)
    ss.setdefault("agent_history", [])
    if "slide_nav" not in ss:
        labels = [s["nav"] for s in SLIDES]
        try:
            idx = int(st.query_params.get("slide", 1)) - 1
        except ValueError:
            idx = 0
        ss["slide_nav"] = labels[min(max(idx, 0), len(labels) - 1)]


@st.cache_resource(show_spinner=False)
def get_engine() -> TrekValidationEngine:
    return TrekValidationEngine()


@st.cache_data(show_spinner=False)
def run_validation_cached(csv_bytes: bytes | None):
    eng = get_engine()
    prospect = eng.default_prospect() if csv_bytes is None else load_prospect_csv(io.BytesIO(csv_bytes))
    res = eng.run_validation(prospect)
    base_cols = list(prospect.columns)
    return res.validated_df, res.dnf_df[base_cols].copy(), res.total_lines, res.query_ms


def sync_cfg(field: str, widget_key: str) -> None:
    st.session_state.cfg[field] = st.session_state[widget_key]


# =========================================================================== sidebar
def render_sidebar(v_all: pd.DataFrame, d_all: pd.DataFrame) -> dict:
    sb = st.sidebar
    sb.markdown("### 🩺 Trek Validation POC")
    mode = sb.radio("Presentation mode", ["🎞️ Live Slides", "🧰 Workbench"], key="mode",
                    help="Live Slides = guided 9-slide walkthrough. Workbench = every tab at once.")
    if mode.startswith("🎞️"):
        sb.toggle("🎤 Presenter notes", key="show_notes", value=False,
                  help="Shows the talk track under each slide (visible to the audience if you share this tab).")
        sb.caption("Navigate with **PageDown / PageUp** (works with presentation clickers) or the buttons.")

    sb.divider()
    sb.markdown("**Data source**")
    sb.radio("Prospect fee schedule", ["Summit Regional (built-in 60-line synthetic CSV)", "Upload custom CSV"],
             key="data_source", label_visibility="collapsed")
    sb.download_button("⬇️ Download sample prospect CSV", PROSPECT_PATH.read_bytes(),
                       file_name="sample_prospect_fee_schedule.csv", mime="text/csv", width="stretch")
    if st.session_state.data_source.startswith("Upload"):
        sb.file_uploader("Upload prospect CSV", type=["csv"], key="upload",
                         help="Columns: prospect_row_id, payer_name, cpt_code, modifier, description, service_line, "
                              "prospect_rate, annual_volume")

    sb.divider()
    sb.markdown("**Scope filters**")
    cfg = st.session_state.cfg
    payers = sorted(set(v_all["payer_name"]) | set(d_all["payer_name"]))
    lines = sorted(set(v_all["service_line"]) | set(d_all["service_line"]))
    sel_p = sb.multiselect("Payer", payers, default=payers, key="f_payers")
    sel_l = sb.multiselect("Service line", lines, default=lines, key="f_lines")
    cfg["payers"], cfg["service_lines"] = sel_p or payers, sel_l or lines

    if mode.startswith("🧰"):
        sb.divider()
        sb.markdown("**Deal & ROI levers**")
        render_levers(sb, "sb")

    sb.divider()
    sb.markdown("**AI agent runtime**")
    meta, _ = load_skill()
    sb.markdown(f'<span class="badge ok">✓ Skill active: {meta["name"]} v{meta["version"]}</span>', unsafe_allow_html=True)
    sb.text_input("Anthropic API key (optional)", type="password", key="api_key",
                  help="Leave empty for the offline deterministic cited engine. With a key, the same skill file drives Claude.")
    if st.session_state.get("api_key"):
        sb.markdown('<span class="badge live">● Live Claude mode</span>', unsafe_allow_html=True)
    else:
        sb.markdown('<span class="badge off">● Offline deterministic cited mode</span>', unsafe_allow_html=True)
    return {"mode": "slides" if mode.startswith("🎞️") else "workbench"}


def render_levers(container, loc: str) -> None:
    cfg = st.session_state.cfg
    c = container
    c.selectbox("Target benchmark tier", TARGET_OPTIONS, index=TARGET_OPTIONS.index(cfg["target"]),
                key=f"{loc}_target", on_change=sync_cfg, args=("target", f"{loc}_target"))
    if cfg["target"] == TARGET_FLOOR:
        c.number_input("Medicare floor (%)", min_value=100.0, max_value=400.0, step=5.0, value=float(cfg["floor_pct"]),
                       key=f"{loc}_floor", on_change=sync_cfg, args=("floor_pct", f"{loc}_floor"))
    c.slider("Negotiation realization %", min_value=0.10, max_value=1.00, step=0.05, value=float(cfg["realization"]),
             format="%.2f", key=f"{loc}_real", on_change=sync_cfg, args=("realization", f"{loc}_real"),
             help="Share of the identified gap the hospital actually wins at renewal. 0.50 = 50%.")
    c.checkbox("Include DNF recovery in ROI", value=bool(cfg["include_dnf"]), key=f"{loc}_dnf",
               on_change=sync_cfg, args=("include_dnf", f"{loc}_dnf"))
    c.number_input("Trek annual platform investment ($)", min_value=0.0, step=5_000.0, value=float(cfg["subscription"]),
                   key=f"{loc}_sub", on_change=sync_cfg, args=("subscription", f"{loc}_sub"))


# =========================================================================== context
def build_context() -> dict:
    eng = get_engine()
    csv_bytes = None
    upload_error = None
    if st.session_state.get("data_source", "").startswith("Upload") and st.session_state.get("upload") is not None:
        csv_bytes = st.session_state.upload.getvalue()
    try:
        v_all, dnf_base, total_all, query_ms = run_validation_cached(csv_bytes)
    except Exception as exc:  # bad upload: show error, fall back to built-in file
        upload_error = f"Could not validate uploaded file — {exc}"
        v_all, dnf_base, total_all, query_ms = run_validation_cached(None)
        csv_bytes = None
    overrides = {k: v for k, v in st.session_state.dnf_overrides.items() if k in set(dnf_base["prospect_row_id"])}
    d_all = eng.resolve_dnf_queue(dnf_base, overrides)
    return {"engine": eng, "v_all": v_all, "d_all": d_all, "dnf_base": dnf_base, "total_all": total_all,
            "query_ms": query_ms, "upload_error": upload_error, "custom": csv_bytes is not None}


def apply_scope(ctx: dict) -> dict:
    cfg = st.session_state.cfg
    v_all, d_all = ctx["v_all"], ctx["d_all"]
    payers = cfg["payers"] or sorted(v_all["payer_name"].unique())
    lines = cfg["service_lines"] or sorted(v_all["service_line"].unique())
    v = v_all[v_all["payer_name"].isin(payers) & v_all["service_line"].isin(lines)].reset_index(drop=True)
    d = d_all[d_all["payer_name"].isin(payers) & d_all["service_line"].isin(lines)].reset_index(drop=True)
    kpis = compute_kpis(v, d, cfg["target"], cfg["realization"], cfg["include_dnf"], cfg["subscription"],
                        cfg["floor_pct"])
    v = v.assign(scenario_gap=TrekValidationEngine.scenario_gap(v, cfg["target"], cfg["floor_pct"]) if len(v) else [])
    eng = ctx["engine"]
    facts = build_facts(v, d, kpis, eng.policies, eng.warehouse_row_count(), eng.mrf_df["hospital_name"].nunique())
    ctx.update(v=v, d=d, kpis=kpis, facts=facts, policies=eng.policies)
    return ctx


# =========================================================================== shared components
def render_hero(ctx: dict) -> None:
    name = "Custom uploaded prospect" if ctx["custom"] else PROSPECT_NAME
    st.markdown(esc_html(
        f'<div class="trek-hero"><h2>"We found {usd_short(ctx["kpis"]["total_addressable"])}/yr you are leaving on the table '
        f'— and every dollar is traceable to a published payer rate."</h2>'
        f'<p>{name} · UHC & Aetna · validated against a normalized Transparency-in-Coverage MRF warehouse (synthetic demo data)</p></div>'),
        unsafe_allow_html=True)


def render_hud(ctx: dict) -> None:
    k = ctx["kpis"]
    cols = st.columns(6)
    pts = k["prospect_pct_medicare"] - k["market_pct_medicare"]
    target_short = {TARGET_P50: "P50", TARGET_P75: "P75", TARGET_FLOOR: f"{k['floor_pct']:.0f}% Mcare floor"}[k["target_benchmark"]]
    payback = "—" if not np.isfinite(k["payback_months"]) else f"{k['payback_months']:.1f} mo"
    payback_sub = "" if not np.isfinite(k["payback_months"]) else f"≈ {k['payback_months'] * 30.4:.0f} days"
    tiles = [
        kpi_tile("Total addressable gap", f"{usd_short(k['total_addressable'])}/yr",
                 f"to {target_short}{' + DNF' if k['include_dnf_recovery'] else ''}", accent=True),
        kpi_tile(f"Realized uplift @ {k['realization_rate']:.0%}", f"{usd_short(k['realized_uplift'])}/yr",
                 "conservative capture assumption", accent=True),
        kpi_tile("% of Medicare: prospect vs market", f"{k['prospect_pct_medicare']:.0f}% vs {k['market_pct_medicare']:.0f}%",
                 f"{pts:+.0f} pts (volume-weighted)"),
        kpi_tile("Warehouse match rate", f"{k['match_rate_pct']:.1f}%",
                 f"{k['matched_lines']}/{k['total_lines']} direct · {k['coverage_with_dnf_pct']:.0f}% w/ DNF proxy"),
        kpi_tile("First-year ROI", f"{k['roi_multiple']:.1f}x", f"on {usd_short(k['annual_trek_subscription'])} platform fee"),
        kpi_tile("Payback period", payback, payback_sub),
    ]
    for c, t in zip(cols, tiles):
        c.markdown(t, unsafe_allow_html=True)


def chart_heatmap(ctx: dict) -> go.Figure:
    v = ctx["v"]
    piv = v.pivot_table(index="service_line", columns="payer_name", values="scenario_gap", aggfunc="sum", fill_value=0)
    piv = piv.loc[piv.sum(axis=1).sort_values(ascending=True).index]
    text = [[usd_short(x) for x in row] for row in piv.values]
    fig = go.Figure(go.Heatmap(
        z=piv.values, x=[short_payer(c) for c in piv.columns], y=list(piv.index), text=text, texttemplate="%{text}",
        textfont=dict(size=14), colorscale=[[i / (len(SEQ_TEAL) - 1), c] for i, c in enumerate(SEQ_TEAL)],
        xgap=3, ygap=3, showscale=False,
        hovertemplate="%{y} · %{x}<br>Annual gap: %{z:$,.0f}<extra></extra>",
    ))
    base_layout(fig, 400, title=dict(text="Annual gap by service line × payer", x=0, font=dict(size=15)))
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=False)
    return fig


def chart_scatter(ctx: dict) -> go.Figure:
    v = ctx["v"]
    fig = go.Figure()
    lo = float(min(v["market_p50_pct_medicare"].min(), v["prospect_pct_medicare"].min())) - 10
    hi = float(max(v["market_p50_pct_medicare"].max(), v["prospect_pct_medicare"].max())) + 10
    fig.add_trace(go.Scatter(x=[lo, hi], y=[lo, hi], mode="lines", line=dict(color="#8A949B", dash="dash", width=1.5),
                             name="Parity (prospect = market)", hoverinfo="skip"))
    max_vol = float(v["annual_volume"].max())
    for flag in FLAG_ORDER:
        sub = v[v["variance_flag"] == flag]
        if sub.empty:
            continue
        m = FLAG_META[flag]
        fig.add_trace(go.Scatter(
            x=sub["market_p50_pct_medicare"], y=sub["prospect_pct_medicare"], mode="markers", name=m["label"],
            marker=dict(size=10 + 30 * np.sqrt(sub["annual_volume"] / max_vol), color=m["color"], symbol=m["symbol"],
                        opacity=0.85, line=dict(color="white", width=1.5)),
            customdata=np.stack([sub["cpt_code"], sub["description"], sub["payer_name"].map(short_payer),
                                 sub["annual_volume"], sub["scenario_gap"], sub["raw_variance_pct"]], axis=-1),
            hovertemplate=("<b>CPT %{customdata[0]}</b> %{customdata[1]} · %{customdata[2]}<br>"
                           "Prospect %{y:.0f}% vs market %{x:.0f}% of Medicare (%{customdata[5]:+.1f}%)<br>"
                           "Volume %{customdata[3]:,} · gap %{customdata[4]:$,.0f}/yr<extra></extra>"),
        ))
    base_layout(fig, 400, title=dict(text="Prospect vs market (% of Medicare) · bubble = annual volume", x=0, font=dict(size=15)))
    fig.update_xaxes(title="Market P50, % of Medicare", range=[lo, hi], ticksuffix="%")
    fig.update_yaxes(title="Prospect rate, % of Medicare", range=[lo, hi], ticksuffix="%")
    fig.update_layout(legend=dict(y=-0.32, yanchor="top"), margin=dict(b=90))
    fig.add_annotation(x=hi - 5, y=lo + 8, text="below the line = paid under market", showarrow=False,
                       font=dict(color=MUTED, size=11), xanchor="right")
    return fig


def chart_peer_box(ctx: dict, cpt: str) -> go.Figure:
    eng = ctx["engine"]
    v = ctx["v"]
    rows = v[v["cpt_code"] == cpt]
    payers = list(rows["payer_name"]) or list(ctx["v_all"]["payer_name"].unique())
    peers = eng.peer_rates(cpt)
    peers = peers[peers["payer_name"].isin(payers)]
    fig = go.Figure()
    for payer in payers:
        p = peers[peers["payer_name"] == payer]
        fig.add_trace(go.Box(
            x=p["negotiated_rate"], y=[short_payer(payer)] * len(p), orientation="h", name=f"Peers · {short_payer(payer)}",
            boxpoints="all", jitter=0.35, pointpos=0, fillcolor="rgba(15,118,110,0.12)", line=dict(color=TEAL, width=2),
            marker=dict(color=TEAL, size=9, line=dict(color="white", width=1)), showlegend=False,
            customdata=np.stack([p["hospital_name"], p["mrf_record_id"], p["plan_type"], p["pct_of_medicare"]], axis=-1),
            hovertemplate="%{customdata[0]} (%{customdata[2]})<br>%{x:$,.2f} · %{customdata[3]:.0f}% of Medicare<br>%{customdata[1]}<extra></extra>",
        ))
    if len(rows):
        fig.add_trace(go.Scatter(
            x=rows["prospect_rate"], y=rows["payer_name"].map(short_payer), mode="markers+text", name="Summit (prospect)",
            marker=dict(symbol="diamond", size=18, color=INK, line=dict(color="white", width=2)),
            text=[f"Summit {usd(x)}" for x in rows["prospect_rate"]], textposition="top center", showlegend=False,
            textfont=dict(color=INK, size=12),
            hovertemplate="Summit (prospect)<br>%{x:$,.2f}<extra></extra>",
        ))
    desc = rows["description"].iloc[0] if len(rows) else cpt
    base_layout(fig, 330, title=dict(text=f"CPT {cpt} {desc}: each dot is a cited peer MRF record", x=0, font=dict(size=15)))
    fig.update_xaxes(title="Negotiated rate ($)", tickprefix="$", tickformat=",.0f")
    fig.update_layout(boxgap=0.45)
    return fig


def chart_pareto(ctx: dict, top_n: int = 15) -> tuple[go.Figure, pd.DataFrame, int]:
    v = ctx["v"]
    par = pareto_table(v, v["scenario_gap"])
    if par.empty:
        return go.Figure(), par, 0
    n70 = min(int((par["cumulative_share_pct"] < 70).sum()) + 1, len(par))
    show = par.head(top_n)
    colors = [TEAL if r <= n70 else "#B9E1D9" for r in show["rank"]]
    labels = [usd_short(g) if r <= n70 else "" for g, r in zip(show["annual_gap"], show["rank"])]
    fig = go.Figure(go.Bar(
        x=show["cpt_code"].astype(str), y=show["annual_gap"], marker=dict(color=colors, cornerradius=4),
        text=labels, textposition="outside", textfont=dict(color=INK, size=12), cliponaxis=False,
        customdata=np.stack([show["description"], show["cumulative_share_pct"], show["rank"]], axis=-1),
        hovertemplate="#%{customdata[2]} CPT %{x} %{customdata[0]}<br>%{y:$,.0f}/yr · cumulative %{customdata[1]:.0f}%<extra></extra>",
    ))
    base_layout(fig, 360, title=dict(
        text=f"Redline targets: top {n70} codes = {par['cumulative_share_pct'].iloc[n70 - 1]:.0f}% of the gap (dark bars)",
        x=0, font=dict(size=15)), bargap=0.25)
    fig.update_xaxes(type="category", title="CPT (payers combined)")
    fig.update_yaxes(title="Annual gap ($)", tickprefix="$", tickformat=",.0s")
    return fig, par, n70


def benchmark_table(v: pd.DataFrame) -> pd.DataFrame:
    t = v[["prospect_row_id", "payer_name", "cpt_code", "description", "service_line", "prospect_rate", "market_p25",
           "market_p50", "market_p75", "prospect_pct_medicare", "market_p50_pct_medicare", "raw_variance_pct",
           "market_percentile_rank", "variance_flag", "annual_volume", "scenario_gap", "sample_mrf_citation",
           "citation_hospital"]].copy()
    t["payer_name"] = t["payer_name"].map(short_payer)
    t["variance_flag"] = t["variance_flag"].map(flag_label)
    return t.sort_values("scenario_gap", ascending=False)


BENCH_COLCFG = {
    "prospect_row_id": st.column_config.TextColumn("Row"),
    "payer_name": st.column_config.TextColumn("Payer"),
    "cpt_code": st.column_config.TextColumn("CPT"),
    "description": st.column_config.TextColumn("Description", width="medium"),
    "service_line": st.column_config.TextColumn("Service line"),
    "prospect_rate": st.column_config.NumberColumn("Prospect $", format="dollar"),
    "market_p25": st.column_config.NumberColumn("Mkt P25", format="dollar"),
    "market_p50": st.column_config.NumberColumn("Mkt P50", format="dollar"),
    "market_p75": st.column_config.NumberColumn("Mkt P75", format="dollar"),
    "prospect_pct_medicare": st.column_config.NumberColumn("Prospect % Mcare", format="%.0f%%"),
    "market_p50_pct_medicare": st.column_config.NumberColumn("Mkt % Mcare", format="%.0f%%"),
    "raw_variance_pct": st.column_config.NumberColumn("Variance", format="%+.1f%%"),
    "market_percentile_rank": st.column_config.ProgressColumn("Pctile rank", min_value=0, max_value=100, format="P%.0f"),
    "variance_flag": st.column_config.TextColumn("Flag"),
    "annual_volume": st.column_config.NumberColumn("Volume", format="localized"),
    "scenario_gap": st.column_config.NumberColumn("Annual gap $", format="$%,.0f"),
    "sample_mrf_citation": st.column_config.TextColumn("Peer MRF cite"),
    "citation_hospital": st.column_config.TextColumn("Cited peer"),
}


# =========================================================================== sections
def section_market(ctx: dict) -> None:
    if ctx["v"].empty:
        st.info("No validated lines in scope — widen the sidebar filters.")
        return
    c1, c2 = st.columns([1, 1.25])
    c1.plotly_chart(chart_heatmap(ctx), width="stretch", config=PLOTLY_CONFIG, key="heatmap")
    c2.plotly_chart(chart_scatter(ctx), width="stretch", config=PLOTLY_CONFIG, key="scatter")


def section_deepdive(ctx: dict, show_grid: bool = True) -> None:
    v = ctx["v"]
    if v.empty:
        st.info("No validated lines in scope — widen the sidebar filters.")
        return
    options = sorted(v["cpt_code"].unique(), key=lambda c: -v[v["cpt_code"] == c]["scenario_gap"].sum())
    desc = v.drop_duplicates("cpt_code").set_index("cpt_code")["description"].to_dict()
    default = options.index("27447") if "27447" in options else 0
    c1, c2 = st.columns([2.2, 1])
    with c1:
        cpt = st.selectbox("CPT deep-dive", options, index=default, format_func=lambda c: f"{c} · {desc[c]}", key="deep_cpt")
        st.plotly_chart(chart_peer_box(ctx, cpt), width="stretch", config=PLOTLY_CONFIG, key="peerbox")
    with c2:
        for _, r in v[v["cpt_code"] == cpt].iterrows():
            st.markdown(kpi_tile(
                f"{short_payer(r['payer_name'])} · {flag_label(r['variance_flag'])}",
                f"{r['prospect_pct_medicare']:.0f}% → {r['market_p50_pct_medicare']:.0f}%",
                f"of Medicare (prospect → peer P50) · P{r['market_percentile_rank']:.0f} rank · "
                f"gap {usd(r['scenario_gap'])}/yr · cite {r['sample_mrf_citation']}"), unsafe_allow_html=True)
            st.write("")
    with st.expander("🔎 View the DuckDB SQL behind every benchmark"):
        st.code(ctx["engine"].get_sql_query_preview(), language="sql")
        st.caption(f"In-memory DuckDB over {ctx['engine'].warehouse_row_count():,} normalized MRF rows · "
                   f"validation pipeline {ctx['query_ms']:.0f} ms (cached after first run).")
    if show_grid:
        with st.expander(f"📋 Auditable benchmark grid ({len(v)} validated lines)"):
            st.dataframe(benchmark_table(v), hide_index=True, width="stretch", column_config=BENCH_COLCFG, height=420)


def section_dnf(ctx: dict) -> None:
    d = ctx["d"]
    k = ctx["kpis"]
    c = st.columns(4)
    c[0].markdown(kpi_tile("Unmatched lines isolated", f"{len(d)}", "zero dropped"), unsafe_allow_html=True)
    c[1].markdown(kpi_tile("Distinct root causes", f"{d['dnf_reason_code'].nunique() if len(d) else 0}", "reason-coded"),
                  unsafe_allow_html=True)
    c[2].markdown(kpi_tile("Resolved via crosswalk", f"{k['dnf_resolved']}/{len(d)}", "documented, editable"),
                  unsafe_allow_html=True)
    c[3].markdown(kpi_tile("Quantified recovery added", f"{usd_short(k['dnf_recovery'])}/yr",
                           "a match-only analysis drops this", accent=True), unsafe_allow_html=True)
    st.write("")
    if d.empty:
        st.success("Every line in scope matched the warehouse directly.")
        return
    t = d[["prospect_row_id", "payer_name", "cpt_code", "modifier", "dnf_reason_code", "proxy_cpt", "proxy_market_p50",
           "adjustment_factor", "estimated_market_rate", "prospect_rate", "annual_volume", "annual_dnf_recovery",
           "confidence_tier", "proxy_mrf_citation"]].copy()
    t["payer_name"] = t["payer_name"].map(short_payer)
    st.dataframe(t, hide_index=True, width="stretch", column_config={
        "prospect_row_id": "Row", "payer_name": "Payer", "cpt_code": "CPT", "modifier": "Mod",
        "dnf_reason_code": st.column_config.TextColumn("DNF reason code", width="medium"),
        "proxy_cpt": "Proxy CPT",
        "proxy_market_p50": st.column_config.NumberColumn("Proxy P50", format="dollar"),
        "adjustment_factor": st.column_config.NumberColumn("Multiplier", format="%.2fx"),
        "estimated_market_rate": st.column_config.NumberColumn("Est. benchmark", format="dollar"),
        "prospect_rate": st.column_config.NumberColumn("Prospect $", format="dollar"),
        "annual_volume": st.column_config.NumberColumn("Volume", format="localized"),
        "annual_dnf_recovery": st.column_config.NumberColumn("Annual recovery", format="$%,.0f"),
        "confidence_tier": "Confidence", "proxy_mrf_citation": "Proxy MRF cite",
    })

    left, right = st.columns([1.3, 1])
    with left:
        st.markdown("##### 🧪 Crosswalk sandbox: stress-test any assumption live")
        resolved = d[d["proxy_cpt"].astype(bool)]
        if resolved.empty:
            st.caption("No resolvable DNF rows in scope.")
        else:
            labels = {r["prospect_row_id"]: f"{r['cpt_code']}{'-' + r['modifier'] if r['modifier'] != 'None' else ''} · "
                                            f"{short_payer(r['payer_name'])} · {r['dnf_reason_code']}"
                      for _, r in resolved.iterrows()}
            rid = st.selectbox("DNF line", list(labels), format_func=labels.get, key="sandbox_row")
            row = resolved[resolved["prospect_row_id"] == rid].iloc[0]
            key = f"dnf_factor_{rid}"

            def _store(rid=rid, key=key):
                st.session_state.dnf_overrides[rid] = st.session_state[key]

            st.slider(f"Adjustment multiplier ({row['factor_basis']}; playbook default {row['default_adjustment_factor']:.2f})",
                      min_value=0.30, max_value=1.60, step=0.01, value=float(row["adjustment_factor"]), key=key,
                      on_change=_store)
            default_est = row["proxy_market_p50"] * row["default_adjustment_factor"]
            default_rec = max(0.0, default_est - row["prospect_rate"]) * row["annual_volume"]
            m = st.columns(3)
            m[0].metric("Estimated benchmark", usd(row["estimated_market_rate"]),
                        f"{row['estimated_market_rate'] - default_est:+,.0f} vs default")
            m[1].metric("Prospect rate", usd(row["prospect_rate"]))
            m[2].metric("Annual recovery", usd(row["annual_dnf_recovery"]),
                        f"{row['annual_dnf_recovery'] - default_rec:+,.0f} vs default")
            st.caption(esc(f"Formula: {usd(row['proxy_market_p50'])} (CPT {row['proxy_cpt']} P50, cite {row['proxy_mrf_citation']}) "
                       f"× {row['adjustment_factor']:.2f} = {usd(row['estimated_market_rate'])}; recovery = max(0, estimate − "
                       f"prospect) × {int(row['annual_volume'])}."))
            if st.session_state.dnf_overrides:
                if st.button("↺ Reset all multipliers to playbook defaults", key="dnf_reset"):
                    for k_ in [k_ for k_ in st.session_state if str(k_).startswith("dnf_factor_")]:
                        del st.session_state[k_]
                    st.session_state.dnf_overrides = {}
                    st.rerun()
    with right:
        st.markdown("##### Why each line didn't match")
        for cpt, g in d.groupby("cpt_code", sort=False):
            r = g.iloc[0]
            st.markdown(f"**{cpt}{'-' + r['modifier'] if r['modifier'] != 'None' else ''}** · `{r['dnf_reason_code']}`  \n"
                        f"{r['diagnostic_explanation']}  \n*{r['resolution_methodology']}* · {r['confidence_tier']}")
    with st.expander("📘 SE playbook: preventing future DNF gaps"):
        st.markdown(
            "1. **Tag**: every unmatched line gets a reason code (absent code, modifier split, suppressed cell, Cat III), "
            "never a silent drop.\n"
            "2. **Resolve**: apply a documented crosswalk (RVU ratio, professional split, complexity, specialty index) with "
            "a confidence tier, and let the analyst edit the factor.\n"
            "3. **Feed back**: log the pattern to data engineering (e.g. *ingest modifier-26 professional rates*, "
            "*lower cell-size threshold for GI*), so the next prospect gets a direct match.")


def section_roi(ctx: dict, inline_levers: bool) -> None:
    k = ctx["kpis"]
    if inline_levers:
        with st.container(border=True):
            st.markdown("**Deal & ROI levers**: drag these live")
            lc = st.columns([1.3, 1.6, 1, 1.2])
            cfg = st.session_state.cfg
            lc[0].selectbox("Target benchmark", TARGET_OPTIONS, index=TARGET_OPTIONS.index(cfg["target"]),
                            key="in_target", on_change=sync_cfg, args=("target", "in_target"))
            lc[1].slider("Negotiation realization", min_value=0.10, max_value=1.00, step=0.05,
                         value=float(cfg["realization"]), format="%.2f", key="in_real",
                         on_change=sync_cfg, args=("realization", "in_real"))
            lc[2].checkbox("Include DNF recovery", value=bool(cfg["include_dnf"]), key="in_dnf",
                           on_change=sync_cfg, args=("include_dnf", "in_dnf"))
            lc[3].number_input("Platform fee ($/yr)", min_value=0.0, step=5_000.0, value=float(cfg["subscription"]),
                               key="in_sub", on_change=sync_cfg, args=("subscription", "in_sub"))
            if cfg["target"] == TARGET_FLOOR:
                lc[0].number_input("Medicare floor (%)", min_value=100.0, max_value=400.0, step=5.0,
                                   value=float(cfg["floor_pct"]), key="in_floor", on_change=sync_cfg,
                                   args=("floor_pct", "in_floor"))
    c = st.columns(4)
    payback = "—" if not np.isfinite(k["payback_months"]) else f"{k['payback_months']:.1f} months"
    c[0].markdown(kpi_tile(f"Realized uplift @ {k['realization_rate']:.0%}", f"{usd_short(k['realized_uplift'])}/yr",
                           f"of {usd_short(k['total_addressable'])} addressable", accent=True), unsafe_allow_html=True)
    c[1].markdown(kpi_tile("Year-1 net benefit", usd_short(k["year1_net_benefit"]),
                           f"after {usd_short(k['annual_trek_subscription'])} fee"), unsafe_allow_html=True)
    c[2].markdown(kpi_tile("ROI · payback", f"{k['roi_multiple']:.1f}x", payback), unsafe_allow_html=True)
    c[3].markdown(kpi_tile("3-year net value", usd_short(k["three_year_net_value"]), "uplift × 3 − fee × 3"),
                  unsafe_allow_html=True)
    st.write("")
    if ctx["v"].empty:
        return
    left, right = st.columns([1.05, 1])
    with left:
        st.markdown("##### Sensitivity matrix: realization × target")
        sm = sensitivity_matrix(ctx["v"], ctx["d"], k["annual_trek_subscription"], k["include_dnf_recovery"])
        cur = {TARGET_P50: "Market P50", TARGET_P75: "Market P75"}.get(k["target_benchmark"])
        st.dataframe(sm, hide_index=True, width="stretch", height=460, column_config={
            "Annual Uplift ($)": st.column_config.NumberColumn(format="$%,.0f"),
            "Net Year-1 Benefit ($)": st.column_config.NumberColumn(format="$%,.0f"),
            "ROI Multiple (x)": st.column_config.NumberColumn(format="%.1fx"),
            "Payback (months)": st.column_config.NumberColumn(format="%.1f"),
            "3-Year Net Value ($)": st.column_config.NumberColumn(format="$%,.0f"),
        })
        st.caption(f"Current scenario: {cur or k['target_benchmark']} @ {k['realization_rate']:.0%}. "
                   "Floor scenario uses 190% of Medicare.")
    with right:
        fig, par, n70 = chart_pareto(ctx)
        st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG, key="pareto")
        if len(par):
            st.caption(esc("Redline list: " + " · ".join(f"**{r.cpt_code}** {usd_short(r.annual_gap)}"
                                                         for r in par.head(n70).itertuples())))


def section_excel(ctx: dict) -> None:
    k = ctx["kpis"]
    params = {"annual_subscription_cost": k["annual_trek_subscription"], "realization_factor": k["realization_rate"],
              "include_dnf": k["include_dnf_recovery"], "term_years": 3,
              "prospect_name": "Custom uploaded prospect" if ctx["custom"] else PROSPECT_NAME}
    xlsx = generate_roi_workbook(ctx["v"], ctx["d"], params)
    ev = WorkbookEvaluator(xlsx)
    n_formulas = count_formulas(xlsx)
    left, right = st.columns([1, 2])
    with left:
        st.download_button("📥 Download CFO ROI Business Case (.xlsx, 100% live formulas)", xlsx,
                           file_name="Trek_Health_ROI_Business_Case.xlsx", type="primary", width="stretch",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        st.markdown(kpi_tile("Live formulas in workbook", f"{n_formulas}", "0 hard-coded outputs"), unsafe_allow_html=True)
        st.write("")
        st.markdown(
            f"**Tab 1 · {SHEET_EXEC}**: yellow assumption cells C6:C9 drive the summary in C12:C21.  \n"
            f"**Tab 2 · {SHEET_BENCH}**: {len(ctx['v'])} validated lines; revenue, uplift, and % of Medicare are formulas.  \n"
            f"**Tab 3 · {SHEET_DNF}**: {len(ctx['d'])} DNF lines; the multiplier (col L) is editable.")
        st.caption("Opens in Excel, Google Sheets, and LibreOffice. Formulas recalculate on open.")
    with right:
        st.markdown("##### Live formula transparency: exact strings inside the file, evaluated")
        prev = formula_preview(xlsx)
        prev["Evaluated value"] = [
            _fmt_eval(ev.value(r.Sheet, r.Cell), r.Cell, r.Sheet) for r in prev.itertuples()]
        st.dataframe(prev, hide_index=True, width="stretch", height=460,
                     column_order=["Cell", "Label", "Formula", "Evaluated value", "Sheet"], column_config={
                         "Cell": st.column_config.TextColumn(width="small"),
                         "Formula": st.column_config.TextColumn(width="large"),
                         "Label": st.column_config.TextColumn(width="medium"),
                         "Evaluated value": st.column_config.TextColumn(width="small"),
                     })


def _fmt_eval(val, cell: str, sheet: str) -> str:
    if not isinstance(val, (int, float)):
        return str(val)
    if sheet == SHEET_EXEC and cell == "C19":
        return f"{val:.1f}x"
    if sheet == SHEET_EXEC and cell == "C20":
        return f"{val:.2f} months"
    if sheet == SHEET_BENCH and cell[0] in ("O", "P"):
        return f"{val:.1%}"
    return f"${val:,.2f}"


def section_agent(ctx: dict) -> None:
    meta, instructions = load_skill()
    left, right = st.columns([1.9, 1])
    with left:
        cols = st.columns(4)
        clicked = None
        for i, (label, prompt) in enumerate(PRESET_PROMPTS.items()):
            if cols[i].button(label, key=f"preset_{i}", width="stretch", help=prompt):
                clicked = prompt
        with st.form("ask_form", clear_on_submit=True, border=False):
            fc = st.columns([5, 1])
            q = fc[0].text_input("Ask anything", placeholder="e.g. Tell me about 27447 · Compare UHC vs Aetna in Radiology",
                                 label_visibility="collapsed")
            submitted = fc[1].form_submit_button("Ask", width="stretch")
        query = clicked or (q.strip() if submitted and q.strip() else None)
        if query:
            with st.spinner("Querying validated rates, DNF queue and policy cards…"):
                answer, info = ask_benchmark_agent(query, ctx["v"], ctx["d"], ctx["kpis"], ctx["policies"],
                                                   api_key=st.session_state.get("api_key") or None)
            st.session_state.agent_last = (query, answer, info)
            st.session_state.agent_history.insert(0, (query, answer, info))
        if st.session_state.agent_last:
            query, answer, info = st.session_state.agent_last
            mode_badge = ('<span class="badge live">Live Claude</span>' if info["mode_used"] == "live"
                          else '<span class="badge off">Deterministic cited engine</span>')
            st.markdown(f"**Q:** {query}")
            st.markdown(f"{mode_badge} &nbsp; skill `{info['skill_name']}` v{info['skill_version']} · "
                        f"model `{info['model']}` · {info['citations_count']} MRF citations · "
                        f"{info['tokens_or_rows_scanned']:,} {'tokens' if info['mode_used'] == 'live' else 'rows scanned'} · "
                        f"{info['latency_ms']} ms", unsafe_allow_html=True)
            if info.get("fallback_reason"):
                st.caption(f"Live call unavailable ({info['fallback_reason']}); answered by the offline cited engine.")
            with st.container(border=True, height=520):
                st.markdown(esc(answer))
        else:
            st.info("Click a preset or ask a question. Every answer has two parts, an analyst note and a CFO mandate, "
                    "and cites MRF records.")
        if len(st.session_state.agent_history) > 1:
            with st.expander(f"Earlier answers ({len(st.session_state.agent_history) - 1})"):
                for q_, a_, _ in st.session_state.agent_history[1:6]:
                    st.markdown(f"**Q:** {q_}")
                    st.markdown(esc(a_))
                    st.divider()
    with right:
        section_policy(ctx)
        with st.expander("🧠 Skill file inspector: skills/benchmark_analyst_skill.md"):
            st.markdown("**Parsed YAML configuration**")
            st.json(meta, expanded=False)
            st.markdown("**Markdown instructions (system prompt)**")
            st.code(instructions, language="markdown")


def section_policy(ctx: dict) -> None:
    st.markdown("##### 🛡️ OpenPayer policy explorer *(simulated)*")
    pol = {k: v for k, v in ctx["policies"].items() if not k.startswith("_")}
    names = {**ctx["v_all"].drop_duplicates("cpt_code").set_index("cpt_code")["description"].to_dict(),
             **ctx["d_all"].drop_duplicates("cpt_code").set_index("cpt_code")["description"].to_dict()}
    cpt = st.selectbox("CPT", list(pol), format_func=lambda c: f"{c} · {names.get(c, '')}", key="policy_cpt")
    risk = policy_risk_table(ctx["v"], ctx["d"], ctx["policies"])
    for payer, card in pol[cpt].items():
        r = risk[(risk["cpt_code"] == cpt) & (risk["payer_name"] == payer)]
        score = f"{r.iloc[0]['combined_risk_score']:.0f}/100" if len(r) else "n/a (out of scope)"
        var = f"{r.iloc[0]['variance_pct']:+.1f}% vs market" if len(r) else ""
        icon = {"High": "🔴", "Medium": "🟠", "Low": "🟢"}[card["denial_risk"]]
        with st.container(border=True):
            st.markdown(f"**{short_payer(payer)}** · combined rate + policy risk **{score}** {('· ' + var) if var else ''}  \n"
                        f"Prior auth: **{'Required' if card['prior_auth_required'] else 'Not required'}** · "
                        f"Denial risk: {icon} {card['denial_risk']} ({card['common_denial_code']})  \n"
                        f"<small>2026: {card['policy_change_2026']}</small>", unsafe_allow_html=True)


def arch_html(rows: int, peers: int, matched: int, dnf: int, formulas: int) -> str:
    def box(tag, title, path, body):
        return (f'<div class="layer"><div class="tag">{tag}</div><div><div class="lt">{title} '
                f'<code>{path}</code></div><div class="lb">{body}</div></div></div>')
    return (
        '<div class="arch">'
        + box("L1", "Data", "src/data_generator.py",
              f"Deterministic (seed 42): {rows} MRF rows · {peers} peers · 4 payers · 26 CPTs · 60-line prospect · policy cards")
        + '<div class="down">▼</div>'
        + box("L2", "Engine", "src/engine.py",
              f"In-memory DuckDB: percentiles → validation join → {matched} validated | {dnf} DNF → crosswalks → scenarios")
        + '<div class="down">▼</div><div class="split">'
        + box("L3A", "Excel", "src/excel_exporter.py", f"3 tabs · {formulas} live formulas · independently recomputed")
        + box("L3B", "Agent", "src/agent.py + skills/*.md", "Skill file → system prompt · live Claude | offline cited engine")
        + '</div><div class="down">▼</div>'
        + box("L4", "UI", "app.py", "Streamlit + Plotly · Live Slides | Workbench · runs fully offline")
        + '<div class="foot">tests/verify_poc.py: data · partition · $ math · formula recompute · agent citations · UI</div>'
        + '</div>'
    )


def section_architecture(ctx: dict) -> None:
    eng = ctx["engine"]
    meta, _ = load_skill()
    xlsx = generate_roi_workbook(ctx["v"], ctx["d"], {})
    left, right = st.columns([1.6, 1])
    with left:
        st.markdown(esc_html(arch_html(eng.warehouse_row_count(), eng.mrf_df["hospital_name"].nunique(), len(ctx["v"]),
                                       len(ctx["d"]), count_formulas(xlsx))), unsafe_allow_html=True)
    with right:
        st.markdown("##### Runtime telemetry")
        t = st.columns(2)
        t[0].metric("Rows in DuckDB warehouse", f"{eng.warehouse_row_count():,}")
        t[1].metric("Market cohorts (CPT × payer)", f"{len(eng.cohort_df):,}")
        t[0].metric("Validation pipeline", f"{ctx['query_ms']:.0f} ms")
        t[1].metric("Active skill", f"v{meta['version']}")
        t[0].metric("Formulas in .xlsx", f"{count_formulas(xlsx)}")
        t[1].metric("Agent mode", "Live" if st.session_state.get("api_key") else "Offline")


def render_notes(slide: dict, facts: dict) -> None:
    say = "".join(f"<p>“{p.format(**facts)}”</p>" for p in slide["say"])
    do = "".join(f"<li>{a}</li>" for a in slide["do"])
    st.markdown(esc_html(f'<div class="notes"><b>🎤 Presenter notes · {slide["minutes"]}</b><br><b>Do</b><ul>{do}</ul>'
                         f'<b>Say</b>{say}</div>'), unsafe_allow_html=True)


# =========================================================================== slides
def slide_hook(ctx):
    render_hero(ctx)
    render_hud(ctx)
    st.write("")
    f = ctx["facts"]
    c = st.columns(3)
    c[0].markdown(kpi_tile("The ask", "Where are we underpaid?", "…and can you prove your data is right?"),
                  unsafe_allow_html=True)
    c[1].markdown(kpi_tile("What we did", f"{f['matched']} matched · {f['dnf_n']} resolved",
                           f"against {f['warehouse_rows']} payer-published rates from {f['peer_count']} peers"),
                  unsafe_allow_html=True)
    c[2].markdown(kpi_tile("What it's worth", f"{f['realized']}/yr", f"at {f['realization']} capture · {f['roi']} ROI",
                           accent=True), unsafe_allow_html=True)


def slide_motion(ctx):
    f = ctx["facts"]
    steps = [
        ("01", "Ingest", "Prospect fee schedule CSV: CPT × payer × rate × volume.", f"{f['total_lines']} lines in"),
        ("02", "Benchmark", "DuckDB percentiles over normalized TiC MRF rates from regional peers.", f"{f['warehouse_rows']} rates"),
        ("03", "Resolve DNF", "Reason-code every unmatched line; defensible crosswalks.", f"{f['dnf_n']} lines · 0 dropped"),
        ("04", "Model ROI", "Conservative scenarios → live-formula Excel for the CFO.", f"{f['roi']} ROI"),
        ("05", "Arm the buyer", "Skill-governed agent: cited, two-altitude answers + policy risk.", "analyst + CFO"),
    ]
    html = '<div class="step-row">'
    for i, (n, t, d, w) in enumerate(steps):
        if i:
            html += '<div class="arrow">→</div>'
        html += f'<div class="step"><div class="n">STEP {n}</div><div class="t">{t}</div><div class="d">{d}</div><div class="w">{w}</div></div>'
    st.markdown(html + "</div>", unsafe_allow_html=True)
    c1, c2 = st.columns([1, 1.6])
    with c1:
        st.markdown("##### The problem")
        st.markdown(
            "- Transparency in Coverage forces payers to publish **every negotiated rate**, but as multi-GB MRF files.\n"
            "- Hospitals negotiate largely blind; raw files are unusable without normalization.\n"
            "- The SE's job: turn that into **proof** for one specific hospital, fast, and in a form their analyst *and* CFO trust.")
    with c2:
        st.markdown("##### What one normalized MRF row looks like")
        eng = ctx["engine"]
        st.dataframe(eng.mrf_df[eng.mrf_df["cpt_code"] == "27447"].head(6)[
            ["mrf_record_id", "hospital_name", "payer_name", "plan_type", "cpt_code", "medicare_rate", "negotiated_rate",
             "pct_of_medicare", "mrf_schema_version", "last_updated"]],
            hide_index=True, width="stretch", column_config={
                "medicare_rate": st.column_config.NumberColumn("medicare", format="dollar"),
                "negotiated_rate": st.column_config.NumberColumn("negotiated", format="dollar"),
                "pct_of_medicare": st.column_config.NumberColumn("% Mcare", format="%.0f%%")})
        st.caption("Synthetic, deterministic slice: fictional peer hospitals, 2026-Q3.")


def slide_market(ctx):
    section_market(ctx)


def slide_deepdive(ctx):
    section_deepdive(ctx, show_grid=True)


def slide_dnf(ctx):
    section_dnf(ctx)


def slide_roi(ctx):
    section_roi(ctx, inline_levers=True)


def slide_excel(ctx):
    section_excel(ctx)


def slide_agent(ctx):
    section_agent(ctx)


def slide_close(ctx):
    section_architecture(ctx)
    c = st.columns(2)
    with c[0]:
        st.markdown("##### How I'd run this on day one")
        st.markdown("1. **Discovery**: confirm the prospect's top payers, renewal dates, and the top 50 codes by revenue.\n"
                    "2. **Validation**: run their file within 48 hours; every unmatched line gets a reason code and a crosswalk.\n"
                    "3. **Business case**: live-formula model in their CFO's hands; redline list for the negotiator.\n"
                    "4. **Feedback loop**: send DNF patterns back to data engineering so the next deal matches directly.")
    with c[1]:
        st.markdown("##### Questions for you")
        st.markdown("- How does your team handle Data Not Found lines in live deals today?\n"
                    "- Where do evaluations stall: data access, analyst trust, or CFO sign-off?\n"
                    "- How are agents and skill files used in the SE workflow today?")


SLIDE_RENDERERS = {
    "hook": slide_hook, "motion": slide_motion, "market": slide_market, "deepdive": slide_deepdive, "dnf": slide_dnf,
    "roi": slide_roi, "excel": slide_excel, "agent": slide_agent, "close": slide_close,
}


def _go(delta: int) -> None:
    labels = [s["nav"] for s in SLIDES]
    i = labels.index(st.session_state.slide_nav) if st.session_state.slide_nav in labels else 0
    st.session_state.slide_nav = labels[(i + delta) % len(labels)]


def render_slides(ctx: dict) -> None:
    labels = [s["nav"] for s in SLIDES]
    top = st.columns([6.0, 1.25, 0.55, 1.25], vertical_alignment="center")
    with top[0]:
        st.segmented_control("Slides", labels, key="slide_nav", label_visibility="collapsed", required=True)
    top[1].button("◀ Prev", key="prev_top", on_click=_go, args=(-1,), width="stretch", shortcut="PageUp")
    idx = labels.index(st.session_state.slide_nav) if st.session_state.slide_nav in labels else 0
    top[2].markdown(f'<div class="slide-counter">{idx + 1} / {len(SLIDES)}</div>', unsafe_allow_html=True)
    top[3].button("Next ▶", key="next_top", on_click=_go, args=(1,), width="stretch", type="primary", shortcut="PageDown")
    st.query_params["slide"] = str(idx + 1)

    slide = SLIDES[idx]
    st.markdown(f'<div class="trek-kicker">Trek Health · Fee Schedule Validation & ROI Engine · {slide["nav"]}</div>'
                f'<div class="trek-title">{slide["title"]}</div>'
                f'<div class="trek-takeaway">{esc_html(slide["takeaway"].format(**ctx["facts"]))}</div>', unsafe_allow_html=True)
    SLIDE_RENDERERS[slide["id"]](ctx)
    if st.session_state.get("show_notes"):
        render_notes(slide, ctx["facts"])


def render_workbench(ctx: dict) -> None:
    render_hero(ctx)
    render_hud(ctx)
    st.write("")
    tabs = st.tabs(["01 · Market Intelligence & CMA", "02 · Data Not Found Workbench", "03 · CFO ROI & Excel Export",
                    "04 · Ask Trek Agent & OpenPayer", "05 · Architecture & Talk Track"])
    with tabs[0]:
        section_market(ctx)
        section_deepdive(ctx, show_grid=True)
    with tabs[1]:
        section_dnf(ctx)
    with tabs[2]:
        section_roi(ctx, inline_levers=False)
        st.divider()
        section_excel(ctx)
    with tabs[3]:
        section_agent(ctx)
    with tabs[4]:
        section_architecture(ctx)
        st.divider()
        st.markdown(esc(SCRIPT_PATH.read_text(encoding="utf-8")) if SCRIPT_PATH.exists()
                    else "Run `python -m src.demo_script` to generate DEMO_SCRIPT.md.")


# =========================================================================== main
def main() -> None:
    init_state()
    ctx = build_context()
    ui = render_sidebar(ctx["v_all"], ctx["d_all"])
    if ctx["upload_error"]:
        st.sidebar.error(ctx["upload_error"])
    apply_scope(ctx)
    if ui["mode"] == "slides":
        render_slides(ctx)
    else:
        render_workbench(ctx)


main()
