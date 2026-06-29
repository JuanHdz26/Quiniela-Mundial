#!/usr/bin/env python3
"""
Quiniela S&D Mundial 2026 - Auto-updater
Fetches results from football-data.org and regenerates index.html
"""

import json
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
import os
import sys

# ─── CONFIG ────────────────────────────────────────────────────────────────────
API_KEY = os.environ.get("FOOTBALL_API_KEY", "")
API_BASE = "https://api.football-data.org/v4"
WC_ID = 2000  # FIFA World Cup 2026 competition ID

# CDMX timezone (UTC-6, permanente desde que México eliminó horario de verano)
CDMX = timezone(timedelta(hours=-6))

# ─── QUINIELA DATA ─────────────────────────────────────────────────────────────
PLAYERS = {
    "LIMON":  {"T1":"Argentina","T2":"México",      "T3":"Ecuador",       "T4":"Noruega",          "T5":"Qatar",      "T6":"Jordania"},
    "BRUNO":  {"T1":"España",   "T2":"Colombia",    "T3":"Australia",     "T4":"Canadá",           "T5":"Túnez",      "T6":"Nueva Zelanda"},
    "RAMI":   {"T1":"Francia",  "T2":"Japón",       "T3":"Corea del Sur", "T4":"Suecia",           "T5":"Sudáfrica",  "T6":"Curazao"},
    "FIRE":   {"T1":"Inglaterra","T2":"Bélgica",    "T3":"USA",           "T4":"Costa de Marfil",  "T5":"Escocia",    "T6":"Bosnia"},
    "ALEX":   {"T1":"Portugal", "T2":"Uruguay",     "T3":"Suiza",         "T4":"Argelia",          "T5":"Iraq",       "T6":"Arabia"},
    "JORGE":  {"T1":"Brasil",   "T2":"Croacia",     "T3":"Turquía",       "T4":"Rep. Checa",       "T5":"Paraguay",   "T6":"Cabo Verde"},
    "BOB":    {"T1":"Países Bajos","T2":"Senegal",  "T3":"Irán",          "T4":"Panamá",           "T5":"Congo",      "T6":"Ghana"},
    "ALFARO": {"T1":"Alemania", "T2":"Marruecos",   "T3":"Austria",       "T4":"Egipto",           "T5":"Uzbekistán", "T6":"Haití"},
}

MULT = {"T1":1.0,"T2":1.25,"T3":1.5,"T4":2.0,"T5":3.0,"T6":4.0}

# Map API team code (TLA, 3 letras) → quiniela name.
# Los TLA son estables y únicos; evita fallos por variantes de nombre
# (ej. "South Korea" vs "Korea Republic", "Bosnia-Herzegovina" vs "Bosnia and Herzegovina").
TEAM_MAP_TLA = {
    "ARG":"Argentina","ESP":"España","FRA":"Francia","ENG":"Inglaterra",
    "POR":"Portugal","BRA":"Brasil","NED":"Países Bajos","GER":"Alemania",
    "MEX":"México","COL":"Colombia","JPN":"Japón","BEL":"Bélgica",
    "URY":"Uruguay","URU":"Uruguay","CRO":"Croacia","SEN":"Senegal","MAR":"Marruecos",
    "ECU":"Ecuador","AUS":"Australia","KOR":"Corea del Sur","USA":"USA",
    "SUI":"Suiza","IRN":"Irán","AUT":"Austria","NOR":"Noruega",
    "CAN":"Canadá","SWE":"Suecia","CIV":"Costa de Marfil","ALG":"Argelia",
    "CZE":"Rep. Checa","PAN":"Panamá","EGY":"Egipto","QAT":"Qatar",
    "TUN":"Túnez","RSA":"Sudáfrica","SCO":"Escocia","IRQ":"Iraq",
    "PAR":"Paraguay","COD":"Congo","UZB":"Uzbekistán","HAI":"Haití",
    "JOR":"Jordania","NZL":"Nueva Zelanda","GHA":"Ghana","CPV":"Cabo Verde",
    "KSA":"Arabia","BIH":"Bosnia","CUW":"Curazao","TUR":"Turquía",
}

# Fallback por nombre, por si algún equipo viniera sin TLA.
TEAM_MAP_NAME = {
    "Argentina":"Argentina","Spain":"España","France":"Francia","England":"Inglaterra",
    "Portugal":"Portugal","Brazil":"Brasil","Netherlands":"Países Bajos","Germany":"Alemania",
    "Mexico":"México","Colombia":"Colombia","Japan":"Japón","Belgium":"Bélgica",
    "Uruguay":"Uruguay","Croatia":"Croacia","Senegal":"Senegal","Morocco":"Marruecos",
    "Ecuador":"Ecuador","Australia":"Australia","South Korea":"Corea del Sur",
    "Korea Republic":"Corea del Sur","United States":"USA","USA":"USA",
    "Switzerland":"Suiza","Iran":"Irán","Austria":"Austria","Norway":"Noruega",
    "Canada":"Canadá","Sweden":"Suecia","Ivory Coast":"Costa de Marfil","Algeria":"Argelia",
    "Czechia":"Rep. Checa","Panama":"Panamá","Egypt":"Egipto","Qatar":"Qatar",
    "Tunisia":"Túnez","South Africa":"Sudáfrica","Scotland":"Escocia","Iraq":"Iraq",
    "Paraguay":"Paraguay","Congo DR":"Congo","Uzbekistan":"Uzbekistán","Haiti":"Haití",
    "Jordan":"Jordania","New Zealand":"Nueva Zelanda","Ghana":"Ghana",
    "Cape Verde Islands":"Cabo Verde","Saudi Arabia":"Arabia",
    "Bosnia-Herzegovina":"Bosnia","Curaçao":"Curazao","Turkey":"Turquía",
}

def map_team(team):
    """Recibe el dict del equipo de la API y devuelve el nombre de la quiniela."""
    tla = team.get("tla")
    if tla and tla in TEAM_MAP_TLA:
        return TEAM_MAP_TLA[tla]
    name = team.get("name", "")
    return TEAM_MAP_NAME.get(name, name)

def get_tier(team):
    for player, teams in PLAYERS.items():
        for tier, t in teams.items():
            if t == team:
                return tier
    return None

def get_owner(team):
    for player, teams in PLAYERS.items():
        for t in teams.values():
            if t == team:
                return player
    return None

def fmt_pts(n):
    if n == int(n):
        return str(int(n))
    s = f"{n:.2f}".rstrip("0").rstrip(".")
    return s

# ─── API CALLS ─────────────────────────────────────────────────────────────────
def api_get(path):
    url = f"{API_BASE}{path}"
    req = urllib.request.Request(url, headers={"X-Auth-Token": API_KEY})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} for {url}: {e.reason}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error fetching {url}: {e}", file=sys.stderr)
        return None

def fetch_matches():
    """Devuelve TODOS los partidos del torneo, o None si la API falló.
    De aquí se derivan tanto los resultados (finalizados) como el calendario."""
    data = api_get(f"/competitions/{WC_ID}/matches")
    if data is None:
        return None  # error real de la API → no tocar el index.html existente
    return data.get("matches", [])

# Etiqueta de ronda para el calendario (los knockouts no tienen "grupo")
STAGE_META = {
    "LAST_32": "16avos",
    "LAST_16": "Octavos",
    "QUARTER_FINALS": "Cuartos",
    "SEMI_FINALS": "Semifinal",
    "THIRD_PLACE": "3er lugar",
    "FINAL": "Final",
}

def build_schedule(matches):
    """Construye el calendario desde la API, en hora CDMX. Incluye fase de grupos
    y knockouts en cuanto ambos equipos están definidos. Siempre refleja el fixture
    real (fechas, horas, rondas, reprogramaciones)."""
    rows = []
    for m in matches:
        home = m.get("homeTeam") or {}
        away = m.get("awayTeam") or {}
        if not home.get("name") or not away.get("name"):
            continue  # knockouts con equipos TBD aún no se muestran
        try:
            dt = datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00")).astimezone(CDMX)
        except Exception:
            continue
        stage = m.get("stage", "")
        if stage == "GROUP_STAGE":
            meta = "Grupo " + (m.get("group") or "").replace("GROUP_", "")
        else:
            meta = STAGE_META.get(stage, stage.replace("_", " ").title())
        rows.append([
            dt.strftime("%Y-%m-%d"),
            map_team(home),
            map_team(away),
            meta,
            dt.strftime("%H:%M"),
        ])
    rows.sort(key=lambda r: (r[0], r[4]))
    return rows

def fetch_scorers():
    """Top goleadores del torneo. Devuelve [] si la API falla (no es crítico)."""
    data = api_get(f"/competitions/{WC_ID}/scorers?limit=15")
    if data is None:
        return []
    return data.get("scorers", [])

# ─── SCORE CALCULATION ─────────────────────────────────────────────────────────
# Mapeo stage de la API → ronda interna. OJO: el Mundial 2026 es de 48 equipos,
# así que LAST_32 (Ronda de 32) son los "16avos"; LAST_16 son octavos, etc.
STAGE_ROUND = {
    "GROUP_STAGE": "groups",
    "LAST_32": "r32",   # 16avos
    "LAST_16": "r16",   # octavos
    "QUARTER_FINALS": "qf",  # cuartos
    "SEMI_FINALS": "sf",     # semifinal
    "FINAL": "final",
    # THIRD_PLACE → None (la quiniela no otorga puntos por 3er lugar)
}

def determine_round(match):
    return STAGE_ROUND.get(match.get("stage", ""))

def match_winner(home, away, score):
    """Ganador del partido. En knockouts puede definirse por penales → usa score.winner."""
    wf = score.get("winner")
    if wf == "HOME_TEAM":
        return home
    if wf == "AWAY_TEAM":
        return away
    ft = score.get("fullTime", {})
    hg, ag = ft.get("home"), ft.get("away")
    if hg is None or ag is None:
        return None
    return home if hg > ag else away if ag > hg else None

def build_scores(matches):
    scores = {}       # team -> raw points
    log = []          # list of match dicts for display
    qualified = set() # equipos que clasificaron a 16avos (5 pts c/u)
    months = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]

    def add(team, pts):
        scores[team] = scores.get(team, 0) + pts

    # 1) Bono "clasifica 16avos" (5 pts) a TODO equipo presente en la Ronda de 32,
    #    aunque su partido aún no se juegue: por estar en el bracket ya clasificaron.
    for m in matches:
        if m.get("stage") != "LAST_32":
            continue
        for side in ("homeTeam", "awayTeam"):
            t = m.get(side) or {}
            if not t.get("name"):
                continue
            team = map_team(t)
            if team not in qualified:
                qualified.add(team)
                add(team, 5)

    # 2) Puntos por resultados de partidos FINALIZADOS
    finished = sorted(
        [m for m in matches if m.get("status") == "FINISHED"],
        key=lambda m: m.get("utcDate", "")
    )
    for m in finished:
        rnd = determine_round(m)
        if not rnd:
            continue

        home = map_team(m["homeTeam"])
        away = map_team(m["awayTeam"])
        score = m.get("score", {})
        ft = score.get("fullTime", {})
        home_g, away_g = ft.get("home"), ft.get("away")
        if home_g is None or away_g is None:
            continue
        winner = match_winner(home, away, score)

        entries = []
        date_str = m.get("utcDate", "")[:10]
        try:
            dt = datetime.fromisoformat(date_str)
            display_date = f"{dt.day} {months[dt.month-1]}"
        except Exception:
            display_date = date_str

        if rnd == "groups":
            if winner:
                add(winner, 3)
                entries.append({"team": winner, "pts": 3, "label": "victoria"})
            else:
                add(home, 1); add(away, 1)
                entries.append({"team": home, "pts": 1, "label": "empate"})
                entries.append({"team": away, "pts": 1, "label": "empate"})

        elif rnd == "r32":
            # El bono de 5 ya se sumó arriba; aquí solo se muestra en el historial
            # y se añade la victoria de 8.
            entries.append({"team": home, "pts": 5, "label": "clasifica 16avos"})
            entries.append({"team": away, "pts": 5, "label": "clasifica 16avos"})
            if winner:
                add(winner, 8)
                entries.append({"team": winner, "pts": 8, "label": "gana 16avos"})

        elif rnd == "r16":
            if winner:
                add(winner, 12)
                entries.append({"team": winner, "pts": 12, "label": "gana octavos"})

        elif rnd == "qf":
            if winner:
                add(winner, 20)
                entries.append({"team": winner, "pts": 20, "label": "gana cuartos"})

        elif rnd == "sf":
            if winner:
                add(winner, 30)
                entries.append({"team": winner, "pts": 30, "label": "gana semifinal"})

        elif rnd == "final":
            loser = away if winner == home else home if winner else None
            if winner:
                add(winner, 50)
                entries.append({"team": winner, "pts": 50, "label": "campeón"})
            if loser:
                add(loser, 20)
                entries.append({"team": loser, "pts": 20, "label": "subcampeón"})

        if entries:
            log.append({
                "t1": home, "s1": home_g, "t2": away, "s2": away_g,
                "round": rnd, "date": display_date, "entries": entries
            })

    return scores, log

def compute_totals(scores):
    totals = {p: 0.0 for p in PLAYERS}
    for team, raw in scores.items():
        tier = get_tier(team)
        owner = get_owner(team)
        if tier and owner:
            totals[owner] += raw * MULT[tier]
    return totals

# ─── HTML GENERATION ───────────────────────────────────────────────────────────
def generate_html(scores, log, totals, match_count, updated_str, scorers=None, schedule=None):
    sorted_players = sorted(totals.items(), key=lambda x: x[1], reverse=True)
    max_pts = sorted_players[0][1] if sorted_players else 1

    # Leaderboard HTML
    lb_html = ""
    for i, (p, pts) in enumerate(sorted_players):
        rc = "gold" if i==0 else "silver" if i==1 else "bronze" if i==2 else ""
        pct = int((pts/max_pts)*100) if max_pts > 0 else 0
        team_names = ", ".join(PLAYERS[p].values())
        lb_html += f'''<div class="p-row{' top1' if i==0 else ''}">
      <div class="rank {rc}">{i+1}</div>
      <div class="p-info"><div class="p-name">{p}</div><div class="p-teams">{team_names}</div></div>
      <div class="bar-bg"><div class="bar-fill" style="width:{pct}%"></div></div>
      <div class="p-score">{fmt_pts(pts)}<br><span class="lbl">pts</span></div>
    </div>'''

    # Teams HTML per player
    TIER_C = {"T1":"t1t","T2":"t2t","T3":"t3t","T4":"t4t","T5":"t5t","T6":"t6t"}
    TIER_CSS = {"T1":"var(--t1)","T2":"var(--t2)","T3":"var(--t3)","T4":"var(--t4)","T5":"var(--t5)","T6":"var(--t6)"}
    teams_html = ""
    for p, _ in sorted_players:
        p_pts = totals[p]
        tags = ""
        for tier, team in PLAYERS[p].items():
            raw = scores.get(team, 0)
            tp = raw * MULT[tier]
            pts_badge = f'<span class="tpts">{fmt_pts(tp)}pts</span>' if raw > 0 else ""
            tags += f'<div class="ttag {TIER_C[tier]}"><span class="dot" style="background:{TIER_CSS[tier]}"></span>{team}{pts_badge}</div>'
        teams_html += f'''<div class="p-block">
      <div class="p-block-name">{p}<span class="p-badge">{fmt_pts(p_pts)} pts</span></div>
      <div class="teams-row">{tags}</div>
    </div>'''

    # Historial HTML
    ROUND_LABELS = {
        "groups":"Fase de grupos","r32":"16avos","r16":"Octavos",
        "qf":"Cuartos","sf":"Semifinal","final":"Final"
    }
    hist_html = ""
    if not log:
        hist_html = '<p style="color:var(--muted);font-size:13px;">Sin resultados aún.</p>'
    else:
        for m in reversed(log):
            w1 = m["s1"] > m["s2"]
            w2 = m["s2"] > m["s1"]
            e_html = ""
            for e in m["entries"]:
                tier = get_tier(e["team"])
                owner = get_owner(e["team"])
                mult = MULT[tier] if tier else 1
                final = fmt_pts(e["pts"] * mult)
                lbl = f' ({e["label"]})' if e.get("label") else ""
                e_html += f'<div class="m-entry"><span>{e["team"]}</span> · {owner} · +{e["pts"]}{lbl} × {mult} = <span>{final} pts</span></div>'
            rl = ROUND_LABELS.get(m["round"], m["round"])
            hist_html += f'''<div class="m-card">
      <div class="m-header"><span class="m-date">{m["date"]}</span><span class="m-round">{rl}</span></div>
      <div class="m-score">
        <span class="m-team{'  w' if w1 else ''}">{m["t1"]}</span>
        <span class="m-num">{m["s1"]} – {m["s2"]}</span>
        <span class="m-team r{'  w' if w2 else ''}">{m["t2"]}</span>
      </div>
      {f'<div class="m-entries">{e_html}</div>' if e_html else ""}
    </div>'''

    # Tier list for reglas
    tier_list_html = ""
    for i, tier in enumerate(["T1","T2","T3","T4","T5","T6"]):
        tteams = " · ".join(PLAYERS[p][tier] for p in PLAYERS)
        tier_list_html += f'<div class="r-row"><span class="r-lbl"><span class="tdot" style="background:{TIER_CSS[tier]}"></span>Tier {i+1}</span><span style="font-size:11px;color:var(--muted);text-align:right;flex:1;padding-left:8px">{tteams}</span></div>'

    # Goleadores HTML (top 15, solo goles, con dueño de la quiniela)
    scorers_html = ""
    if not scorers:
        scorers_html = '<p style="color:var(--muted);font-size:13px;">Aún no hay goleadores registrados.</p>'
    else:
        for i, s in enumerate(scorers[:15]):
            pl = s.get("player", {}) or {}
            tm = s.get("team", {}) or {}
            goals = s.get("goals", 0) or 0
            name = pl.get("name", "?")
            team_es = map_team(tm)
            owner = get_owner(team_es)
            team_line = team_es + (f' · <span style="color:var(--accent)">{owner}</span>' if owner else "")
            scorers_html += f'''<div class="sc-row">
      <div class="sc-rank">{i+1}</div>
      <div class="sc-goals">{goals}</div>
      <div class="sc-info"><div class="sc-name">{name}</div><div class="sc-team">{team_line}</div></div>
    </div>'''

    # Schedule JS array — generado desde la API (siempre refleja el fixture real)
    schedule_js = "var SCHEDULE = " + json.dumps(schedule or [], ensure_ascii=False) + ";"

    players_js = "var PLAYERS = " + json.dumps(PLAYERS, ensure_ascii=False) + ";"
    mult_js = "var MULT = " + json.dumps(MULT) + ";"
    scores_js = "var SCORES = " + json.dumps(scores, ensure_ascii=False) + ";"
    totals_js = "var TOTALS = " + json.dumps({p: round(v, 4) for p,v in totals.items()}, ensure_ascii=False) + ";"
    sorted_js = "var SORTED = " + json.dumps([[p, round(v,4)] for p,v in sorted_players], ensure_ascii=False) + ";"

    html = f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Quiniela S&D Mundial 2026</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#0e1117;--surface:#161b25;--surface2:#1e2535;
  --border:rgba(255,255,255,0.08);--border2:rgba(255,255,255,0.14);
  --text:#f0f2f7;--muted:#8b93a7;--accent:#00c87a;--accent-dim:rgba(0,200,122,0.12);
  --gold:#f5c842;--silver:#b0bec5;--bronze:#cd7c50;
  --t1:#7c6ff7;--t2:#00c87a;--t3:#3b9eff;--t4:#f0803c;--t5:#f5c842;--t6:#e060a0;
}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;padding-bottom:60px}}
.header{{background:var(--surface);border-bottom:1px solid var(--border);padding:28px 20px 20px;text-align:center}}
.eyebrow{{font-size:11px;font-weight:600;letter-spacing:.12em;color:var(--accent);text-transform:uppercase;margin-bottom:6px}}
.title{{font-size:clamp(32px,8vw,52px);font-weight:700;line-height:1;margin-bottom:10px}}
.meta-pills{{display:flex;justify-content:center;gap:8px;flex-wrap:wrap;margin-top:12px}}
.pill{{font-size:12px;background:var(--surface2);border:1px solid var(--border);border-radius:20px;padding:4px 12px;color:var(--muted)}}
.pill strong{{color:var(--text)}}
.update-tag{{display:inline-block;font-size:11px;background:var(--accent-dim);color:var(--accent);border:1px solid rgba(0,200,122,0.25);border-radius:20px;padding:3px 10px;margin-top:10px}}
.nav{{display:flex;justify-content:center;gap:2px;padding:0 16px;border-bottom:1px solid var(--border);overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:none}}
.nav::-webkit-scrollbar{{display:none}}
.nav-tab{{font-size:13px;font-weight:500;color:var(--muted);background:none;border:none;border-bottom:2px solid transparent;cursor:pointer;padding:12px 14px;white-space:nowrap;-webkit-tap-highlight-color:transparent}}
.nav-tab.active{{color:var(--accent);border-bottom-color:var(--accent)}}
.section{{display:none;padding:24px 16px;max-width:760px;margin:0 auto}}
.section.active{{display:block}}
.sec-heading{{font-size:11px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-bottom:16px}}
.lb{{display:flex;flex-direction:column;gap:8px}}
.p-row{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:14px 16px;display:grid;grid-template-columns:36px 1fr auto auto;align-items:center;gap:10px}}
.p-row.top1{{border-color:rgba(245,200,66,0.3);background:linear-gradient(90deg,rgba(245,200,66,0.05) 0%,var(--surface) 60%)}}
.rank{{font-size:22px;font-weight:700;text-align:center;color:var(--muted)}}
.rank.gold{{color:var(--gold)}}.rank.silver{{color:var(--silver)}}.rank.bronze{{color:var(--bronze)}}
.p-info{{min-width:0}}
.p-name{{font-size:15px;font-weight:600;margin-bottom:3px}}
.p-teams{{font-size:11px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.bar-bg{{width:70px;height:5px;background:var(--surface2);border-radius:3px;overflow:hidden}}
.bar-fill{{height:100%;background:var(--accent);border-radius:3px}}
.p-score{{font-size:26px;font-weight:700;text-align:right;min-width:48px;line-height:1}}
.p-score .lbl{{font-size:10px;color:var(--muted);font-weight:400}}
.filter-bar{{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:18px}}
.fbtn{{font-size:12px;font-weight:500;padding:5px 12px;border-radius:20px;border:1px solid var(--border);background:none;color:var(--muted);cursor:pointer;-webkit-tap-highlight-color:transparent}}
.fbtn.active,.fbtn:hover{{background:var(--surface2);color:var(--text);border-color:var(--border2)}}
.p-block{{margin-bottom:26px}}
.p-block-name{{font-size:18px;font-weight:700;margin-bottom:10px;display:flex;align-items:center;gap:8px}}
.p-badge{{font-size:12px;font-weight:500;background:var(--accent-dim);color:var(--accent);border-radius:6px;padding:2px 8px}}
.teams-row{{display:flex;flex-wrap:wrap;gap:6px}}
.ttag{{font-size:12px;font-weight:500;padding:5px 10px;border-radius:7px;border:1px solid;display:inline-flex;align-items:center;gap:6px}}
.ttag .dot{{width:6px;height:6px;border-radius:50%;flex-shrink:0}}
.ttag .tpts{{font-size:10px;opacity:.7}}
.t1t{{background:rgba(124,111,247,.1);border-color:rgba(124,111,247,.3);color:#a99fff}}
.t2t{{background:rgba(0,200,122,.1);border-color:rgba(0,200,122,.3);color:#4ddfaa}}
.t3t{{background:rgba(59,158,255,.1);border-color:rgba(59,158,255,.3);color:#7bbeff}}
.t4t{{background:rgba(240,128,60,.1);border-color:rgba(240,128,60,.3);color:#f5a472}}
.t5t{{background:rgba(245,200,66,.1);border-color:rgba(245,200,66,.3);color:#f5d072}}
.t6t{{background:rgba(224,96,160,.1);border-color:rgba(224,96,160,.3);color:#ee88c4}}
.m-card{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:14px 16px;margin-bottom:8px}}
.m-header{{display:flex;align-items:center;gap:8px;margin-bottom:8px}}
.m-date{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}}
.m-round{{font-size:10px;background:var(--surface2);color:var(--muted);border-radius:4px;padding:2px 7px}}
.m-score{{font-size:20px;font-weight:700;display:flex;align-items:center;gap:10px;margin-bottom:8px}}
.m-team{{flex:1}}.m-team.w{{color:var(--accent)}}.m-team.r{{text-align:right}}
.m-num{{font-size:24px;font-weight:700;color:var(--muted)}}
.m-entries{{border-top:1px solid var(--border);padding-top:8px;display:flex;flex-direction:column;gap:3px}}
.m-entry{{font-size:11px;color:var(--muted)}}
.m-entry span{{color:var(--accent);font-weight:500}}
.today-hdr{{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:6px}}
.today-dt{{font-size:22px;font-weight:700}}
.today-tz{{font-size:11px;color:var(--muted);background:var(--surface2);border-radius:4px;padding:3px 8px}}
.day-group{{font-size:11px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin:22px 0 12px}}
#fixtures-list .day-group:first-child{{margin-top:4px}}
.fix-card{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:14px 16px;margin-bottom:8px;display:grid;grid-template-columns:58px 1fr;align-items:start;gap:12px}}
.fix-card.live{{border-color:rgba(0,200,122,.4)}}.fix-card.done{{opacity:.55}}
.fix-hour{{font-size:22px;font-weight:700;line-height:1;text-align:center}}
.fix-status{{font-size:10px;margin-top:3px;text-align:center}}
.s-live{{color:var(--accent);font-weight:600}}.s-soon{{color:var(--gold);font-weight:600}}.s-done{{color:var(--muted)}}
.fix-matchup{{font-size:14px;font-weight:600;margin-bottom:3px}}
.fix-vs{{color:var(--muted);font-weight:400;font-size:12px}}
.fix-meta{{font-size:11px;color:var(--muted);margin-bottom:6px}}
.fix-badges{{display:flex;flex-wrap:wrap;gap:4px;margin-top:5px}}
.fbadge{{font-size:10px;font-weight:600;padding:2px 8px;border-radius:5px;display:inline-block}}
.no-matches{{text-align:center;padding:48px 20px;color:var(--muted);font-size:14px}}
.sc-row{{display:grid;grid-template-columns:28px 40px 1fr;align-items:center;gap:10px;background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:10px 14px;margin-bottom:6px}}
.sc-row.top1{{border-color:rgba(245,200,66,0.3)}}
.sc-rank{{font-size:14px;font-weight:700;color:var(--muted);text-align:center}}
.sc-goals{{font-size:22px;font-weight:700;color:var(--accent);text-align:center;line-height:1}}
.sc-info{{min-width:0}}
.sc-name{{font-size:14px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.sc-team{{font-size:11px;color:var(--muted);margin-top:2px}}
.rules-grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}
@media(max-width:480px){{.rules-grid{{grid-template-columns:1fr}}}}
.r-card{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px}}
.r-card h3{{font-size:11px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;margin-bottom:12px}}
.r-row{{display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid var(--border)}}
.r-row:last-child{{border-bottom:none}}
.r-lbl{{font-size:13px;color:var(--muted)}}
.r-val{{font-size:13px;font-weight:600}}
.tdot{{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}}
</style>
</head>
<body>
<div class="header">
  <div class="eyebrow">⚽ Quiniela S&D</div>
  <div class="title">MUNDIAL 2026</div>
  <div class="meta-pills">
    <div class="pill">Entrada: <strong>$1,000</strong></div>
    <div class="pill">1er lugar: <strong>$6,000</strong></div>
    <div class="pill">2do lugar: <strong>$2,000</strong></div>
    <div class="pill">8 participantes</div>
  </div>
  <div class="update-tag">{updated_str} · {match_count} partidos</div>
</div>
<div class="nav">
  <button class="nav-tab active" onclick="showTab('tabla')">Tabla</button>
  <button class="nav-tab" onclick="showTab('hoy')">Próximos partidos</button>
  <button class="nav-tab" onclick="showTab('equipos')">Equipos</button>
  <button class="nav-tab" onclick="showTab('goleadores')">Goleadores</button>
  <button class="nav-tab" onclick="showTab('historial')">Historial</button>
  <button class="nav-tab" onclick="showTab('reglas')">Reglas</button>
</div>
<div id="tabla" class="section active">
  <div class="sec-heading">Clasificación general</div>
  <div class="lb">{lb_html}</div>
</div>
<div id="hoy" class="section">
  <div class="today-hdr">
    <span class="today-dt">Próximos partidos</span>
    <span class="today-tz">Hora CDMX (UTC−6)</span>
  </div>
  <div id="fixtures-list"></div>
</div>
<div id="equipos" class="section">
  <div class="sec-heading">Equipos por participante</div>
  <div class="filter-bar" id="filter-bar"></div>
  <div id="teams-container">{teams_html}</div>
</div>
<div id="goleadores" class="section">
  <div class="sec-heading">Tabla de goleadores</div>
  <div id="scorers-list">{scorers_html}</div>
</div>
<div id="historial" class="section">
  <div class="sec-heading">Resultados registrados</div>
  <div id="match-log">{hist_html}</div>
</div>
<div id="reglas" class="section">
  <div class="sec-heading">Sistema de puntos</div>
  <div class="rules-grid">
    <div class="r-card">
      <h3>Puntos por ronda</h3>
      <div class="r-row"><span class="r-lbl">Victoria (fase grupos)</span><span class="r-val">3 pts</span></div>
      <div class="r-row"><span class="r-lbl">Empate (fase grupos)</span><span class="r-val">1 pt</span></div>
      <div class="r-row"><span class="r-lbl">Clasificar a 16avos</span><span class="r-val">5 pts</span></div>
      <div class="r-row"><span class="r-lbl">Ganar 16avos</span><span class="r-val">8 pts</span></div>
      <div class="r-row"><span class="r-lbl">Ganar octavos</span><span class="r-val">12 pts</span></div>
      <div class="r-row"><span class="r-lbl">Ganar cuartos</span><span class="r-val">20 pts</span></div>
      <div class="r-row"><span class="r-lbl">Ganar semifinal</span><span class="r-val">30 pts</span></div>
      <div class="r-row"><span class="r-lbl">Subcampeón</span><span class="r-val">20 pts</span></div>
      <div class="r-row"><span class="r-lbl">Campeón</span><span class="r-val">50 pts</span></div>
    </div>
    <div class="r-card">
      <h3>Multiplicadores por Tier</h3>
      <div class="r-row"><span class="r-lbl"><span class="tdot" style="background:var(--t1)"></span>Tier 1</span><span class="r-val">×1.0</span></div>
      <div class="r-row"><span class="r-lbl"><span class="tdot" style="background:var(--t2)"></span>Tier 2</span><span class="r-val">×1.25</span></div>
      <div class="r-row"><span class="r-lbl"><span class="tdot" style="background:var(--t3)"></span>Tier 3</span><span class="r-val">×1.5</span></div>
      <div class="r-row"><span class="r-lbl"><span class="tdot" style="background:var(--t4)"></span>Tier 4</span><span class="r-val">×2.0</span></div>
      <div class="r-row"><span class="r-lbl"><span class="tdot" style="background:var(--t5)"></span>Tier 5</span><span class="r-val">×3.0</span></div>
      <div class="r-row"><span class="r-lbl"><span class="tdot" style="background:var(--t6)"></span>Tier 6</span><span class="r-val">×4.0</span></div>
    </div>
  </div>
  <div class="r-card" style="margin-top:14px">
    <h3>Equipos por Tier</h3>
    <div id="tier-list">{tier_list_html}</div>
  </div>
</div>
<script>
{players_js}
{mult_js}
{scores_js}
{totals_js}
{sorted_js}
{schedule_js}

function getOwner(team) {{
  var ps = Object.keys(PLAYERS);
  for (var i=0;i<ps.length;i++) {{
    var ts = Object.values(PLAYERS[ps[i]]);
    for (var j=0;j<ts.length;j++) if (ts[j]===team) return ps[i];
  }}
  return null;
}}

function renderFilterBar() {{
  var fb = document.getElementById('filter-bar');
  if (!fb) return;
  var html = '<button class="fbtn active" onclick="filterTeams(\\'ALL\\',this)">Todos</button>';
  var ps = Object.keys(PLAYERS);
  for (var i=0;i<ps.length;i++) html += '<button class="fbtn" onclick="filterTeams(\\''+ps[i]+'\\',this)">'+ps[i]+'</button>';
  fb.innerHTML = html;
}}

var activeFilter = 'ALL';
window.filterTeams = function(name, btn) {{
  activeFilter = name;
  var btns = document.querySelectorAll('.fbtn');
  for (var i=0;i<btns.length;i++) btns[i].classList.remove('active');
  btn.classList.add('active');
  renderTeams();
}};

function renderTeams() {{
  var tc = document.getElementById('teams-container');
  if (!tc) return;
  var TIER_C = {{T1:'t1t',T2:'t2t',T3:'t3t',T4:'t4t',T5:'t5t',T6:'t6t'}};
  var TIER_CSS = {{T1:'var(--t1)',T2:'var(--t2)',T3:'var(--t3)',T4:'var(--t4)',T5:'var(--t5)',T6:'var(--t6)'}};
  var html = '';
  for (var si=0;si<SORTED.length;si++) {{
    var player = SORTED[si][0], pPts = SORTED[si][1];
    if (activeFilter !== 'ALL' && activeFilter !== player) continue;
    var tkeys = Object.keys(PLAYERS[player]);
    var tags = '';
    for (var ti=0;ti<tkeys.length;ti++) {{
      var tier = tkeys[ti], team = PLAYERS[player][tier];
      var raw = SCORES[team]||0, tp = raw*MULT[tier];
      var ptsB = raw>0 ? '<span class="tpts">'+tp+'pts</span>' : '';
      tags += '<div class="ttag '+TIER_C[tier]+'"><span class="dot" style="background:'+TIER_CSS[tier]+'"></span>'+team+ptsB+'</div>';
    }}
    html += '<div class="p-block"><div class="p-block-name">'+player+'<span class="p-badge">'+pPts+' pts</span></div><div class="teams-row">'+tags+'</div></div>';
  }}
  tc.innerHTML = html;
}}

function renderToday() {{
  var now = new Date();
  var cdmxMs = now.getTime() + (now.getTimezoneOffset() + (-6*60))*60000;
  var cn = new Date(cdmxMs);
  var nowMins = cn.getHours()*60+cn.getMinutes();
  var days=['domingo','lunes','martes','miércoles','jueves','viernes','sábado'];
  var months=['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'];
  function dstr(d) {{
    var m=(d.getMonth()+1<10?'0':'')+(d.getMonth()+1);
    var dd=(d.getDate()<10?'0':'')+d.getDate();
    return d.getFullYear()+'-'+m+'-'+dd;
  }}
  var fc = document.getElementById('fixtures-list');
  if (!fc) return;
  var html = '', total = 0;
  // Hoy + los siguientes 2 días
  for (var k=0;k<3;k++) {{
    var d = new Date(cn.getTime() + k*86400000);
    var key = dstr(d);
    var dayMatches = [];
    for (var i=0;i<SCHEDULE.length;i++) if (SCHEDULE[i][0]===key) dayMatches.push(SCHEDULE[i]);
    if (!dayMatches.length) continue;
    total += dayMatches.length;
    var label = days[d.getDay()]+' '+d.getDate()+' de '+months[d.getMonth()];
    if (k===0) label = 'Hoy · '+label;
    html += '<div class="day-group">'+label+'</div>';
    for (var fi=0;fi<dayMatches.length;fi++) {{
      var fx=dayMatches[fi], ft1=fx[1], ft2=fx[2], fmeta=fx[3], ftime=fx[4];
      var sClass='',sLabel='',cClass='';
      if (k===0) {{
        var fh=parseInt(ftime.split(':')[0]), fm2=parseInt(ftime.split(':')[1]);
        var fmins=fh*60+fm2, diff=fmins-nowMins;
        if (diff<-105){{sClass='s-done';sLabel='Finalizado';cClass='done';}}
        else if (diff<0){{sClass='s-live';sLabel='🔴 En vivo';cClass='live';}}
        else if (diff<60){{sClass='s-soon';sLabel='En '+diff+' min';}}
      }}
      var o1=getOwner(ft1), o2=getOwner(ft2);
      var badges='';
      if (o1) badges+='<span class="fbadge" style="background:rgba(0,200,122,.12);color:#4ddfaa">'+o1+' — '+ft1+'</span> ';
      if (o2) badges+='<span class="fbadge" style="background:rgba(124,111,247,.12);color:#a99fff">'+o2+' — '+ft2+'</span>';
      html+='<div class="fix-card '+cClass+'"><div class="fix-time"><div class="fix-hour">'+ftime+'</div>'+(sLabel?'<div class="fix-status '+sClass+'">'+sLabel+'</div>':'')+'</div><div><div class="fix-matchup">'+ft1+' <span class="fix-vs">vs</span> '+ft2+'</div><div class="fix-meta">'+fmeta+'</div>'+(badges?'<div class="fix-badges">'+badges+'</div>':'')+'</div></div>';
    }}
  }}
  if (!total) {{ fc.innerHTML='<div class="no-matches"><div style="font-size:32px;margin-bottom:10px">📅</div>No hay partidos en los próximos 3 días.</div>'; return; }}
  fc.innerHTML = html;
}}

window.showTab = function(name) {{
  var tabs = document.querySelectorAll('.nav-tab');
  var names = ['tabla','hoy','equipos','goleadores','historial','reglas'];
  for (var i=0;i<tabs.length;i++) tabs[i].classList.toggle('active', names[i]===name);
  var secs = document.querySelectorAll('.section');
  for (var i=0;i<secs.length;i++) secs[i].classList.toggle('active', secs[i].id===name);
}};

renderFilterBar();
renderToday();
</script>
</body>
</html>'''
    return html

# ─── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    print("Fetching World Cup results...")
    matches = fetch_matches()

    # Si la API falló (None), no regeneramos: conservamos el index.html actual
    # para no borrar resultados ya cargados con datos vacíos.
    if matches is None:
        print("⚠️  La API no respondió correctamente. Se conserva el index.html existente.", file=sys.stderr)
        sys.exit(0)

    print(f"Found {len(matches)} matches total")
    finished_count = sum(1 for m in matches if m.get("status") == "FINISHED")
    print(f"  {finished_count} finished")

    # build_scores recibe TODOS los partidos: filtra finalizados para puntos de
    # resultados, y usa el bracket de LAST_32 para el bono de clasificación.
    scores, log = build_scores(matches)
    totals = compute_totals(scores)

    schedule = build_schedule(matches)
    print(f"Built schedule with {len(schedule)} fixtures")

    scorers = fetch_scorers()
    print(f"Found {len(scorers)} scorers")

    now_cdmx = datetime.now(CDMX)
    months = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]
    updated_str = f"Actualizado: {now_cdmx.day} {months[now_cdmx.month-1]} {now_cdmx.year}"

    html = generate_html(scores, log, totals, len(log), updated_str, scorers, schedule)

    out_path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Generated {out_path} ({len(html)} bytes)")

if __name__ == "__main__":
    main()
