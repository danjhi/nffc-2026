"""NFFC Draft Board — Streamlit app for exploring historical Rotowire OC drafts."""

import os
import re
from datetime import datetime

import pandas as pd
import streamlit as st
from supabase import create_client

# ── Config ──────────────────────────────────────────────────────────────────
_env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

SUPABASE_URL = "https://twfzcrodldvhpfaykasj.supabase.co"
SUPABASE_KEY = os.environ["SUPABASE_ANON_KEY"]

POSITION_COLORS = {
    "QB": "#FFF0B3",
    "RB": "#D1EAF5",
    "WR": "#D4F0D4",
    "TE": "#FFD9E2",
    "K": "#E6E6FA",
    "TK": "#E6E6FA",
    "TDSP": "#E0E0E0",
    "DEF": "#E0E0E0",
}
DEFAULT_COLOR = "#FFFFFF"

# ── Page Config ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="NFFC Draft Board", layout="wide", menu_items={})
st.markdown(
    """<style>
    #MainMenu,footer,header {visibility:hidden;}
    .block-container {padding-top:1rem;}
    /* Draft board table styling */
    .stTable table {border-collapse:collapse; width:100%; table-layout:fixed; font-size:11px;}
    .stTable th {white-space:pre-line; text-align:center; padding:6px 4px; font-size:10px; border:1px solid #dee2e6;}
    .stTable td {white-space:pre-line; text-align:center; padding:4px 3px; border:1px solid #dee2e6; vertical-align:middle; overflow:hidden;}
    .stTable {overflow-x:auto;}
    </style>""",
    unsafe_allow_html=True,
)


# ── Supabase Client ─────────────────────────────────────────────────────────
@st.cache_resource
def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ── Data Fetching ───────────────────────────────────────────────────────────
def _paginated_fetch(query_builder, page_size=1000):
    all_rows = []
    offset = 0
    while True:
        resp = query_builder.range(offset, offset + page_size - 1).execute()
        all_rows.extend(resp.data)
        if len(resp.data) < page_size:
            break
        offset += page_size
    return all_rows


@st.cache_data(ttl=3600)
def fetch_years():
    sb = get_supabase()
    rows = _paginated_fetch(sb.table("leagues").select("year"))
    return sorted({r["year"] for r in rows}, reverse=True)


@st.cache_data(ttl=3600)
def fetch_leagues(year):
    sb = get_supabase()
    return _paginated_fetch(
        sb.table("leagues").select("league_id, name, draft_date").eq("year", year).order("name")
    )


def _league_display_name(lg):
    """Format league for dropdown: '#1036 (July 23)' instead of full name."""
    name = lg.get("name") or ""
    # Extract number from name like "$350 Rotowire Online Championship #1036"
    m = re.search(r"#(\d+)", name)
    label = f"#{m.group(1)}" if m else name
    # Append draft date if available
    draft_date = lg.get("draft_date")
    if draft_date:
        try:
            dt = datetime.strptime(draft_date[:10], "%Y-%m-%d")
            label += f" ({dt.strftime('%B')} {dt.day})"
        except (ValueError, TypeError):
            pass
    return label


@st.cache_data(ttl=3600)
def fetch_draft(league_id):
    sb = get_supabase()
    rows = (
        sb.table("view_draft_board")
        .select(
            "round, pick_in_round, overall_pick, team_id, draft_order, "
            "league_rank, league_points, first_name, last_name, "
            "position, team, headshot_url"
        )
        .eq("league_id", league_id)
        .order("overall_pick")
        .range(0, 239)
        .execute()
    )
    return rows.data or []


# ── Build Pivoted Board ────────────────────────────────────────────────────
def build_board(picks_data):
    """Build a 20×12 pivoted grid + position grid + header info from raw picks."""
    df = pd.DataFrame(picks_data)

    # 2018 has NULL draft_order — derive from round 1 pick order
    if df["draft_order"].isna().all():
        r1 = df[df["round"] == 1].sort_values("pick_in_round")
        team_to_slot = {tid: i + 1 for i, tid in enumerate(r1["team_id"])}
        df["draft_order"] = df["team_id"].map(team_to_slot)

    num_slots = int(df["draft_order"].max())
    max_round = int(df["round"].max())

    # Display text per cell: "First Last\nPOS · TEAM (overall)"
    def _safe(val):
        return "" if pd.isna(val) else str(val)

    def cell_text(r):
        fn = _safe(r["first_name"])
        ln = _safe(r["last_name"])
        name = f"{fn} {ln}".strip() or "—"
        pos = _safe(r["position"])
        team = _safe(r["team"])
        ovr = int(r["overall_pick"])
        return f"{name}\n{pos} · {team} ({ovr})"

    df["cell"] = df.apply(cell_text, axis=1)

    # Pivot text grid: rows = round, columns = draft_order
    text_grid = df.pivot(index="round", columns="draft_order", values="cell")
    text_grid = text_grid.reindex(
        index=range(1, max_round + 1),
        columns=range(1, num_slots + 1),
    ).fillna("")

    # Pivot position grid (same shape) for coloring
    pos_grid = df.pivot(index="round", columns="draft_order", values="position")
    pos_grid = pos_grid.reindex(
        index=range(1, max_round + 1),
        columns=range(1, num_slots + 1),
    ).fillna("")

    # Build column headers: "Slot N\n#rank · pts"
    team_info = (
        df[["draft_order", "league_rank", "league_points"]]
        .drop_duplicates(subset="draft_order")
        .set_index("draft_order")
    )
    col_labels = {}
    for slot in range(1, num_slots + 1):
        line1 = f"Slot {slot}"
        line2_parts = []
        if slot in team_info.index:
            info = team_info.loc[slot]
            rank = info["league_rank"]
            pts = info["league_points"]
            if rank and not pd.isna(rank):
                line2_parts.append(f"#{int(rank)}")
            if pts and not pd.isna(pts):
                line2_parts.append(f"{pts:.0f}pts")
        col_labels[slot] = f"{line1}\n{' · '.join(line2_parts)}" if line2_parts else line1

    # Build rank lookup: col_label → league_rank (or None)
    col_ranks = {}
    for slot in range(1, num_slots + 1):
        rank = None
        if slot in team_info.index:
            r = team_info.loc[slot, "league_rank"]
            if r and not pd.isna(r):
                rank = int(r)
        col_ranks[col_labels[slot]] = rank

    text_grid.columns = [col_labels[c] for c in text_grid.columns]
    pos_grid.columns = text_grid.columns
    text_grid.index.name = "Rd"

    return text_grid, pos_grid, col_ranks, num_slots


# ── Color Helpers ───────────────────────────────────────────────────────────
def rank_color(rank, total=12):
    """Green (#1) → Yellow (mid) → Red (#12). Returns (bg, text_color)."""
    if rank is None:
        return "#6c757d", "#fff"  # neutral gray
    t = (rank - 1) / max(total - 1, 1)
    # Hue: 120 (green) → 60 (yellow) → 0 (red)
    hue = 120 * (1 - t)
    # Darker saturation/lightness for readability
    bg = f"hsl({hue:.0f}, 75%, 38%)"
    return bg, "#fff"


# ── Styler: position cells + rank-colored headers ──────────────────────────
def style_board(text_grid, pos_grid, col_ranks, num_slots):
    """Apply position-based cell colors and rank-based header colors."""
    def _apply_cell_colors(col):
        pos_col = pos_grid[col.name]
        return [
            f"background-color: {POSITION_COLORS.get(p, DEFAULT_COLOR)}; "
            f"color: #333; font-size: 11px; white-space: pre-line;"
            if p else ""
            for p in pos_col
        ]

    styler = text_grid.style.apply(_apply_cell_colors, axis=0)

    # Color each column header based on league_rank
    header_styles = {}
    for col_name, rank in col_ranks.items():
        bg, fg = rank_color(rank, num_slots)
        header_styles[col_name] = [
            {"selector": "th", "props": [
                ("background-color", bg),
                ("color", fg),
                ("white-space", "pre-line"),
                ("text-align", "center"),
                ("font-size", "10px"),
                ("padding", "6px 4px"),
            ]}
        ]

    styler.set_table_styles(header_styles, overwrite=False)

    return styler


# ── Position Legend ─────────────────────────────────────────────────────────
LEGEND_HTML = " ".join(
    f'<span style="background:{c};color:#333;padding:2px 8px;border-radius:3px;'
    f'margin:0 2px;font-size:11px;">{p}</span>'
    for p, c in POSITION_COLORS.items()
    if p != "DEF"
)


# ── Streamlit App ───────────────────────────────────────────────────────────
st.title("NFFC Draft Board")


@st.fragment
def sidebar_filters():
    st.header("Filters")
    years = fetch_years()
    selected_year = st.selectbox("Year", years, key="year_select")

    if "leagues_year" not in st.session_state or st.session_state.leagues_year != selected_year:
        st.session_state.leagues_year = selected_year
        st.session_state.leagues_data = fetch_leagues(selected_year)

    leagues_data = st.session_state.leagues_data
    display_names = [_league_display_name(lg) for lg in leagues_data]
    selected_display = st.selectbox("League", display_names, key="league_select")

    if selected_display:
        idx = display_names.index(selected_display)
        lg = leagues_data[idx]
        st.session_state.pending_league_id = lg["league_id"]
        st.session_state.pending_league_name = lg["name"]
        st.session_state.pending_year = selected_year

    if st.button("Load Board", type="primary", use_container_width=True):
        st.session_state.selected_league_id = st.session_state.get("pending_league_id")
        st.session_state.selected_league_name = st.session_state.get("pending_league_name")
        st.session_state.selected_year = st.session_state.get("pending_year")
        st.rerun(scope="app")

    st.caption(f"League ID: {st.session_state.get('pending_league_id', '—')}")


with st.sidebar:
    sidebar_filters()


@st.fragment
def draft_board():
    lid = st.session_state.get("selected_league_id")
    name = st.session_state.get("selected_league_name")
    year = st.session_state.get("selected_year")

    if not lid:
        st.info("Select a year and league from the sidebar, then click **Load Board**.")
        return

    with st.spinner("Loading draft board..."):
        picks = fetch_draft(lid)

    if not picks:
        st.warning("No draft data found for this league.")
        return

    st.markdown(f"**{name}** — {year}")
    st.markdown(LEGEND_HTML, unsafe_allow_html=True)

    text_grid, pos_grid, col_ranks, num_slots = build_board(picks)

    styled = style_board(text_grid, pos_grid, col_ranks, num_slots)

    st.table(styled)


draft_board()
