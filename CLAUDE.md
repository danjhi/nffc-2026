# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

NFFC 2026 — A draft strategy and exploration tool for the NFFC (National Fantasy Football Championship), focused on the **Rotowire Online Championship (OC)**. Historical draft data (2018-2025), ADP trends, and league outcomes are stored in Supabase. The end goal is a web-based tool to replace existing Shiny apps and eliminate Posit hosting costs.

## Environment & Config

- **Python 3.9** (system) — no pandas/numpy; scripts use stdlib only (`csv`, `json`, `urllib`)
- **R** — nflreadr, nflfastR, nflplotR ecosystem for player/team enrichment
- **Secrets** in `.env` (gitignored): `NFFC_API_KEY`, `SUPABASE_ACCESS_TOKEN` (PAT), `SUPABASE_ANON_KEY`
- **Supabase MCP** configured via PAT in `.claude.json` (HTTP transport + `Authorization: Bearer` header)

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/pull_draft_results.py` | Pull raw NFFC API data (all contest types, 2018-2025) into `data/raw/` |
| `scripts/build_clean_dataset.py` | Filter to Rotowire OC, enrich via nflreadr, output CSVs to `data/clean/` |
| `scripts/load_to_supabase.py` | Load clean CSVs into Supabase via REST API (reads `.env` for anon key) |

## Apps

| App | Purpose | Run Command |
|-----|---------|-------------|
| `app/draft_board.py` | Streamlit draft board viewer | `streamlit run app/draft_board.py` |

## Data Pipeline

```
NFFC API → data/raw/ (JSON) → build_clean_dataset.py → data/clean/ (CSV) → load_to_supabase.py → Supabase
                                       ↑
                              data/nflreadr/ (R enrichment)
```

---

## Supabase

- **Project ref:** `twfzcrodldvhpfaykasj`
- **URL:** `https://twfzcrodldvhpfaykasj.supabase.co`
- **RLS:** Enabled on all tables with `public read` SELECT policy (no write via API)
- **Data scope:** Rotowire Online Championship only, 2018-2025

### Tables

#### `players` — 1,634 rows
Master player reference. Player IDs are Sportradar UUIDs (same as NFFC API).

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| **player_id** | text PK | NO | Sportradar UUID (e.g., `fa99e984-...` = Ja'Marr Chase) |
| first_name | text | YES | |
| last_name | text | YES | |
| position | text | YES | QB, RB, WR, TE, K, DEF, TK, TDSP |
| birth_date | date | YES | Some originally "0000-00-00" → stored as NULL |
| gsis_id | text | YES | NFL official ID (NULL for TK/TDSP entries) |
| espn_id | text | YES | |
| yahoo_id | text | YES | |
| sleeper_id | text | YES | |
| pfr_id | text | YES | Pro Football Reference ID |
| rotowire_id | text | YES | |
| headshot_url | text | YES | NFL.com headshot URL |
| college | text | YES | |
| draft_year | smallint | YES | NFL draft year |
| draft_round | smallint | YES | NFL draft round |
| draft_pick | smallint | YES | NFL draft overall pick |
| latest_team | text | YES | Most recent NFL team abbreviation |
| status | text | YES | ACT, RES, DEV, CUT |

**Cross-platform ID mapping:** Players are enriched via nflreadr's `load_ff_playerids()` joined on `sportradar_id`. 1,505/1,634 matched; 130 unmatched are mostly TK/TDSP (team kicker/defense) entries.

#### `leagues` — 2,629 rows
NFFC Rotowire OC league metadata.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| **league_id** | integer PK | NO | NFFC internal league ID |
| year | smallint | NO | Season year (2018-2025) |
| name | text | YES | e.g., "Rotowire Online Championship #2102" |
| num_teams | smallint | YES | Typically 12 |
| third_round_reversal | boolean | YES | 3RR draft snake rule |
| draft_date | timestamptz | YES | NULL for most 2018 leagues |
| draft_completed_date | timestamptz | YES | NULL for most 2018 leagues |

#### `league_teams` — 31,548 rows
Team entries per league with season outcome data.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| **league_id** | integer PK, FK → leagues | NO | |
| **team_id** | integer PK | NO | NFFC internal team ID |
| year | smallint | NO | |
| draft_order | smallint | YES | Draft position (1-12) |
| league_rank | smallint | YES | Final standing (1 = winner). **NULL for 2018 and 2025** |
| league_points | numeric(8,2) | YES | Total season points in league. **NULL for 2018 and 2025** |
| overall_rank | integer | YES | Rank across all OC entries. **NULL for 2018 and 2025** |
| overall_points | numeric(8,2) | YES | Overall season points. **NULL for 2018 and 2025** |

**Note:** 2,760 entries for 2018 were backfilled from draft_picks data with NULL outcomes (2018 API didn't return team standings). 2025 outcomes not yet available.

#### `draft_picks` — 621,356 rows
Pick-by-pick draft history. **Core table for exploration.**

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| **league_id** | integer PK, FK → leagues | NO | |
| **overall_pick** | smallint PK | NO | 1-240 (overall position in draft) |
| year | smallint | NO | |
| round | smallint | NO | 1-20 |
| pick_in_round | smallint | NO | 1-12 (derived: `overall_pick - (round-1)*12`) |
| team_id | integer, FK → league_teams | NO | |
| player_id | text, FK → players | NO | |
| picked_at | timestamptz | YES | Pick timestamp (mostly NULL for 2018-2019) |
| pick_duration | integer | YES | Seconds to make pick. Can exceed 32K (slow email drafts) |

**Note:** 9,124 picks (~1.4%) from the source CSV had empty player_ids and were skipped during load.

#### `adp` — 5,339 rows
Rotowire OC average draft position by player and year.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| **player_id** | text PK, FK → players | NO | |
| **year** | smallint PK | NO | |
| adp | numeric(6,2) | YES | Average draft position (e.g., 1.24) |
| min_pick | smallint | YES | Earliest pick |
| max_pick | smallint | YES | Latest pick |
| times_drafted | integer | YES | Number of times drafted that year |

### Relationships (Foreign Keys)

```
players ←── draft_picks.player_id
players ←── adp.player_id
leagues ←── league_teams.league_id
leagues ←── draft_picks.league_id
league_teams(league_id, team_id) ←── draft_picks(league_id, team_id)
```

### Indexes

| Index | Table | Columns | Purpose |
|-------|-------|---------|---------|
| `draft_picks_pkey` | draft_picks | (league_id, overall_pick) | PK |
| `idx_draft_picks_year_round` | draft_picks | (year, round) | Filter picks by season + round |
| `idx_draft_picks_player_id` | draft_picks | (player_id) | Join to players |
| `idx_draft_picks_league_team` | draft_picks | (league_id, team_id) | FK covering index |
| `league_teams_pkey` | league_teams | (league_id, team_id) | PK |
| `idx_league_teams_league_rank` | league_teams | (league_rank) WHERE NOT NULL | Filter by outcome |
| `idx_leagues_year` | leagues | (year) | Filter leagues by season |
| `idx_players_position` | players | (position) | Filter by position |
| `adp_pkey` | adp | (player_id, year) | PK |
| `idx_adp_player_id` | adp | (player_id) | Player ADP lookups |

### RLS Policies

All tables: RLS enabled, single `"public read"` policy allowing `SELECT` for all roles. No INSERT/UPDATE/DELETE via API.

### Views

#### `view_draft_board`
Pre-joined view used by the Streamlit draft board app. Single query returns everything needed to render a league's draft grid.

```sql
CREATE VIEW view_draft_board AS
SELECT dp.league_id, dp.round, dp.pick_in_round, dp.overall_pick, dp.year,
       p.first_name, p.last_name, p.position, p.latest_team, p.headshot_url,
       lt.team_id, lt.draft_order, lt.league_rank, lt.league_points
FROM draft_picks dp
JOIN players p ON dp.player_id = p.player_id
JOIN league_teams lt ON dp.league_id = lt.league_id AND dp.team_id = lt.team_id;
```

### Migrations Applied

1. `create_tables` — All 5 tables with PKs and FKs
2. `create_indexes` — 6 custom indexes
3. `fix_pick_duration_type` — `pick_duration` smallint → integer (values exceed 32K)
4. `add_missing_fk_index` — Covering index on `draft_picks(league_id, team_id)`
5. `enable_rls_with_read_policy` — RLS + public SELECT policy on all tables
6. `create_view_draft_board` — Pre-joined view for draft board rendering

### Example Queries

```sql
-- Who went #1 overall each year?
SELECT dp.year, p.first_name || ' ' || p.last_name AS player, p.position, count(*) AS times
FROM draft_picks dp
JOIN players p ON dp.player_id = p.player_id
WHERE dp.overall_pick = 1
GROUP BY dp.year, p.first_name, p.last_name, p.position
ORDER BY dp.year, times DESC;

-- ADP vs actual draft position for a player across years
SELECT a.year, a.adp, a.min_pick, a.max_pick, a.times_drafted
FROM adp a
JOIN players p ON a.player_id = p.player_id
WHERE p.last_name = 'Chase' AND p.first_name = 'Ja''Marr'
ORDER BY a.year;

-- What positions did league winners draft in round 1?
SELECT p.position, count(*) AS times
FROM draft_picks dp
JOIN players p ON dp.player_id = p.player_id
JOIN league_teams lt ON dp.league_id = lt.league_id AND dp.team_id = lt.team_id
WHERE dp.round = 1 AND lt.league_rank = 1
GROUP BY p.position
ORDER BY times DESC;
```

---

## Key Queries the Tool Should Support

1. "Who went in round 3 of OC drafts in 2025?" — filter `draft_picks` by year + round, join `players`
2. "What is the ADP range for Player X across years?" — filter `adp` by player
3. "Show me all QBs drafted in rounds 5-8 and their season finish" — join `draft_picks` → `players` (position) + `league_teams` (outcome)
4. "What roster constructions won contests?" — join `draft_picks` → `players` (position) + `league_teams` (league_rank = 1)
5. "Where can I find value vs ADP?" — compare `adp.adp` to actual `draft_picks.overall_pick`

---

## NFFC API Reference

- **Base URL:** `https://nfc.shgn.com/api/public/`
- **Auth:** API key in `.env` (`NFFC_API_KEY`)
- **IMPORTANT:** Python `urllib` requires custom User-Agent header (`NFFC-Draft-Explorer/1.0`) — server returns 403 for default Python UA

### Current Season Endpoints (2025)

| Endpoint | Description |
|----------|-------------|
| `publicleagues/football` | List leagues (filterable by `game_style_id`, `num_teams`) |
| `publicleagues/football/{id}` | League detail (roster positions, scoring, 3RR, draft dates, teams) |
| `publicdraftresults/football/{id}` | Draft picks (`round`, `pick`, `team`, `player` UUID, `timestamp`, `pick_duration`) |
| `adp/football` | ADP + inline player_info (filterable by `game_style_id`, `num_teams`, date range) |

### Historical Endpoints (2018-2024)

| Endpoint | Description |
|----------|-------------|
| `historicalleagues/football/{year}` | All leagues for a year |
| `historicalleagues/football/{year}/{id}` | League detail + team outcomes (`league_rank`, `league_points`, `overall_rank`, `overall_points`) |
| `historicaldraftresults/football/{year}/{id}` | Draft picks (`round`, `pick`, `team`, `player` UUID, `bid`) |
| `historicaladp/football/{year}` | ADP + player_info |

### 2025 game_style_ids

517 Auction, 518 Classic, 519 Cutline, 520 Best Ball Overall, 521 High Stakes, **522 Rotowire Online**, 523 Primetime, 524 Stand Alone, 525 Best Ball 25s/50s, 526 Silver Bullet, 531 Guillotine, 535 Qualifiers, 537 Keeper, 539 Other Live, 540 Best Ball, 541 Weekly, 543 SuperFlex, 545 MFL100s, 546 Gladiator

**Notes:**
- Player IDs are Sportradar UUIDs (e.g., `fa99e984-d63b-4ef4-a164-407f68a7eeaf` = Ja'Marr Chase)
- `game_style_id` values change each year — not available in historical data; filter by league name instead
- API `pick` field is already overall pick (1-240), NOT within-round

---

## Data Inventory

### Raw Data (`data/raw/`) — All Contest Types, 2018-2025

| Dataset | Location | Records |
|---------|----------|---------|
| Draft picks | `data/raw/drafts/drafts_{year}.json` | 11,557 leagues, 3.4M picks (~350MB) |
| League details | `data/raw/league_details/league_details_{year}.json` | 12,205 leagues (~67MB) |
| ADP | `data/raw/adp/adp_{year}.json` | 5,339 player-year records |
| Player lookup | `data/raw/players_lookup.json` | 1,634 unique players |

### Clean Data (`data/clean/`) — Rotowire OC Only

| File | Rows | Size |
|------|------|------|
| `players.csv` | 1,635 | 335 KB |
| `leagues.csv` | 2,629 | 167 KB |
| `league_teams.csv` | 28,788 | 1.1 MB |
| `adp.csv` | 5,339 | 307 KB |
| `draft_picks.csv` | 630,480 | 41 MB |

### nflreadr Reference (`data/nflreadr/`)

| File | Rows | Key Join Field |
|------|------|----------------|
| `ff_playerids.csv` | ~15K | `sportradar_id` = NFFC `player_id` |
| `players.csv` | ~36K | `gsis_id` |
| `teams.csv` | ~32 | NFL team reference |

---

---

## Streamlit Draft Board (`app/draft_board.py`)

Visual draft board for browsing historical Rotowire OC drafts. Renders a 20-row × 12-column pivoted grid with position-colored cells and rank-colored column headers.

### Running

```bash
# Activate venv (streamlit, supabase, pandas installed)
source venv/bin/activate
streamlit run app/draft_board.py
```

Opens at `http://localhost:8501`.

### Architecture

- **Single-file app** — depends on `streamlit`, `supabase`, `pandas`
- **Supabase client** — `create_client()` with anon key from `.env`, cached with `@st.cache_resource`
- **Rendering** — Pandas `df.pivot()` → `Styler` → `st.table()` (static HTML table, supports multi-line cells + CSS)
- **Data query** — `view_draft_board` SQL view, max 240 picks via `.range(0, 239)`

### UI Layout

- **Sidebar:** Year dropdown → League dropdown (filtered by year) → **Load Board** button
  - Dropdowns write to `pending_*` session state; button copies to `selected_*` and calls `st.rerun(scope="app")`
  - This prevents the board from re-rendering while the user is still picking a league
- **Main area:** Position color legend + pivoted draft grid via `st.table(styled)`

### Draft Grid (Pandas Pivot + Styler)

- **Columns:** One per draft slot (1-12), ordered by `draft_order`
- **Rows:** One per round (1-20)
- **Cell content:** Full name on line 1, `"POS · TEAM (overall)"` on line 2 (via `\n` + `white-space: pre-line`)
- **Column headers:** `"Slot N"` on line 1, `"#rank · pts"` on line 2
- **Cell coloring:** Position-based background via `Styler.apply()` — per-cell CSS
- **Header coloring:** Rank-based HSL gradient via `Styler.set_table_styles()` — green (#1) → yellow (mid) → red (#12), neutral gray for 2018/2025 (no rank data)
- **No headshots** — removed for performance (240 HTTP requests caused significant lag)

### Position Colors

| Position | Color | Hex |
|----------|-------|-----|
| QB | Gold | `#FFD700` |
| RB | Light Blue | `#ADD8E6` |
| WR | Light Green | `#90EE90` |
| TE | Pink | `#FFB6C1` |
| K / TK | Lavender | `#E6E6FA` |
| TDSP / DEF | Gray | `#D3D3D3` |

### Performance Notes

- `@st.cache_data(ttl=3600)` on all data-fetching functions (1-hour cache)
- `@st.cache_resource` on Supabase client
- `@st.fragment` on sidebar and draft board to isolate reruns
- `view_draft_board` SQL view eliminates client-side joins
- `st.table` with Pandas Styler for styled HTML (not `st.dataframe`)
- Hidden Streamlit chrome (menu, footer, header) via CSS
- `table-layout: fixed` for consistent column widths
- Paginated fetch helper (`_paginated_fetch`) for queries that exceed 1000 rows

### Key Gotchas

- **`st.dataframe` vs `st.table`:** `st.dataframe` (Glide Data Grid) does NOT support multi-line cell content or Styler CSS. Use `st.table` for styled HTML tables with `white-space: pre-line`.
- **`@st.fragment` and buttons:** A button click inside a fragment only reruns that fragment. To update another fragment, must call `st.rerun(scope="app")`.
- **supabase-py pagination:** `.limit()` does NOT override the 1000-row server default. Must use `.range(offset, offset + page_size - 1)` and loop.
- **2018 / 2025 data:** `league_rank` and `league_points` are NULL — headers render in neutral gray.

---

## Project Phases

1. ~~**Data ingestion**~~ — NFFC API data pulled for all contest types, 2018-2025 ✓
2. ~~**Data cleaning & enrichment**~~ — Rotowire OC filtered, nflreadr enrichment applied ✓
3. ~~**Supabase schema & loading**~~ — 5 tables created, indexed, loaded, RLS enabled ✓
4. **Tool migration** — Rebuild existing Shiny tools as web apps to eliminate Posit hosting costs ($120/mo)
   - ~~Draft board~~ ✓ (`app/draft_board.py` — Streamlit)
