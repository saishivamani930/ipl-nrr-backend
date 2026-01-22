# ipl_api/state_from_standings.py
from __future__ import annotations

from typing import Dict
import os
import re

from ipl_api.nrr_math import TeamAggregate
from ipl_api.points_table import TeamRow

BALLS_PER_MATCH = 120
DEBUG_STATE_BUILD = os.getenv("IPL_DEBUG_STATE_BUILD", "0") == "1"

# Accept codes like: GG, UPW, RCB-W, DC-W, MI-W etc.
_CODE_RE = re.compile(r"^[A-Z]{2,5}(?:-[A-Z])?$")


def normalize_team_code(team_raw: str) -> str:
    """
    WPL-only:
    - Prefer trailing short code if present in the raw string (supports DC-W style).
    - Else attempt to find an end-code via regex.
    - Else return cleaned uppercase string.
    """
    if team_raw is None:
        return ""

    s = str(team_raw).strip()
    if not s:
        return ""

    # Remove leading digits (rank)
    s = re.sub(r"^\d+", "", s).strip()
    s = re.sub(r"\s+", " ", s).strip()

    # Try trailing token as code
    tokens = s.split()
    if tokens:
        last = tokens[-1].strip().upper()
        if _CODE_RE.fullmatch(last):
            return last

    # Try regex at end
    m = re.search(r"([A-Z]{2,5}(?:-[A-Z])?)\s*$", s)
    if m:
        code = m.group(1).upper()
        if _CODE_RE.fullmatch(code):
            return code

    return s.strip().upper()


def _safe_int(x: object, default: int = 0) -> int:
    try:
        if x is None:
            return default
        sx = str(x).strip()
        if not sx or sx.lower() == "nan":
            return default
        return int(float(sx))
    except Exception:
        return default


def build_state_from_standings(standings: dict) -> Dict[str, TeamRow]:
    """
    Convert ESPN standings JSON -> internal state (WPL-only).

    Rules:
      - Prefer `code` from ESPN scraper if present.
      - Else derive code from team display string.
      - Prefer true aggregates (runs/balls for & against) if present.
      - Fallback to approximate reconstruction ONLY if aggregates missing.
    """
    state: Dict[str, TeamRow] = {}
    teams = standings.get("teams", []) or []

    for t in teams:
        raw_code = (t.get("code") or "").strip()
        raw_team = (t.get("team") or "").strip()

        team_code = raw_code.upper() if raw_code else normalize_team_code(raw_team)
        team_code = team_code.strip().upper()
        if not team_code:
            continue

        matches = _safe_int(t.get("matches", 0), 0)
        won = _safe_int(t.get("won", 0), 0)
        lost = _safe_int(t.get("lost", 0), 0)
        nr = _safe_int(t.get("nr", 0), 0)
        tied = _safe_int(t.get("tied", 0), 0)
        points = _safe_int(t.get("points", 0), 0)

        runs_for = t.get("runs_for")
        balls_for = t.get("balls_for")
        runs_against = t.get("runs_against")
        balls_against = t.get("balls_against")

        if DEBUG_STATE_BUILD:
            print(
                "[STATE_BUILD]",
                "team_code=", team_code,
                "raw_team=", raw_team,
                "rf/bf=", runs_for, balls_for,
                "ra/ba=", runs_against, balls_against,
                "nrr=", t.get("nrr"),
            )

        # Prefer real aggregates if available
        if all(v is not None for v in [runs_for, balls_for, runs_against, balls_against]):
            agg = TeamAggregate(
                team=team_code,
                runs_for=int(runs_for),
                balls_for=int(balls_for),
                runs_against=int(runs_against),
                balls_against=int(balls_against),
            )
        else:
            # Fallback reconstruction using matches + NRR (approx)
            balls = int(matches) * BALLS_PER_MATCH
            if balls <= 0:
                rf = 0.0
                ra = 0.0
            else:
                nrr_val = t.get("nrr")
                if nrr_val is None:
                    rf = float(balls)
                    ra = float(balls)
                else:
                    delta = float(nrr_val) * float(balls)
                    rf = float(balls) + delta / 2.0
                    ra = float(balls) - delta / 2.0
                    rf = max(0.0, rf)
                    ra = max(0.0, ra)

            agg = TeamAggregate(
                team=team_code,
                runs_for=int(rf),
                balls_for=int(balls),
                runs_against=int(ra),
                balls_against=int(balls),
            )

        state[team_code] = TeamRow(
            team=team_code,
            played=matches,
            won=won,
            lost=lost,
            nr=nr,
            tied=tied,
            points=points,
            agg=agg,
        )

    return state
