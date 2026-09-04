"""Valideer een baanschema-uitvoer tegen de planningsregels.

Solver-onafhankelijk: leest de uitvoer van de OR-Tools planner, de heuristiek of
het handmatige gold-schema en toetst die tegen `data/season.tsv` en de spec in
`docs/SPEC.md`.

Twee soorten bevindingen:

  HARD   regels uit `docs/SPEC.md` — een overtreding is een fout.
  MODEL  extra constraints die het CP-SAT model oplegt maar die niet in de spec
         staan. Handig om te zien welke daarvan het handmatige gold-schema
         breekt: dat zijn kandidaten om te versoepelen.

Nog niet getoetst uit `docs/SPEC.md` (2026-08-24): de deadlines voor de eerste
partij per team (sectie 2), de inplan-volgorde (sectie 4), de faseregels voor
5- en 8-partijenteams (sectie 5), het baan-geheugen (sectie 3) en de
waarschuwingstags (sectie 6). Een schoon rapport betekent dus nog niet dat een
schema aan de hele spec voldoet.

Gebruik:
    python scripts/validate_schedule.py docs/ortools_06-04-2026.json
    python scripts/validate_schedule.py docs/gold_result.json --date 06-04-2026
    python scripts/validate_schedule.py docs/result.json --all
    python scripts/validate_schedule.py docs/ortools_*.json --strict --json rapport.json

Exit code 1 bij een HARD-overtreding, 0 anders. Met `--strict` telt MODEL ook mee.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from baanschema.rules import build_parts, player_demand  # noqa: E402
from build_pages import parse_input, short_team_name  # noqa: E402

SEASON_FILES = sorted((ROOT / "data").glob("season*.tsv"))
SEASON_DEFAULT = ROOT / "data" / "season.tsv"

SLOT = 15
COURTS = range(1, 11)
COURT_PAIRS = [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10)]
LAST_START = 19 * 60 + 30
UNPLANNED = "NIET_GELUKT"


# --------------------------------------------------------------------------- #
# bevindingen
# --------------------------------------------------------------------------- #

@dataclass
class Finding:
    rule: str
    severity: str  # HARD | MODEL | INFO
    date: str
    message: str
    subject: str = ""

    def line(self) -> str:
        who = f" [{self.subject}]" if self.subject else ""
        return f"  {self.severity:5s} {self.rule:14s}{who} {self.message}"


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    sources: dict = field(default_factory=dict)  # datum -> gebruikt seizoensbestand

    def add(self, *a, **k) -> None:
        self.findings.append(Finding(*a, **k))

    def by_severity(self, sev: str) -> list[Finding]:
        return [f for f in self.findings if f.severity == sev]

    @property
    def hard(self) -> list[Finding]:
        return self.by_severity("HARD")

    @property
    def model(self) -> list[Finding]:
        return self.by_severity("MODEL")


# --------------------------------------------------------------------------- #
# hulp
# --------------------------------------------------------------------------- #

def hhmm_to_min(hhmm: str) -> int | None:
    """'09:15' -> 555. None voor NIET_GELUKT of onleesbare tijd."""
    s = (hhmm or "").strip()
    if not s or s == UNPLANNED:
        return None
    try:
        h, m = s.split(":")
        return int(h) * 60 + int(m)
    except ValueError:
        return None


def to_hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def slots(start: int, end: int) -> range:
    """Kwartierslots die een partij bezet houdt (start inclusief, eind exclusief)."""
    return range(start, end, SLOT)


# --------------------------------------------------------------------------- #
# verwachting uit season.tsv
# --------------------------------------------------------------------------- #

@dataclass
class ExpectedTeam:
    team_id: str
    date: str
    schema: str
    short: str
    duration: int
    matches: int
    parts: list[tuple[str, str]]
    home: str = ""  # (label, kind)

    @property
    def low(self) -> str:
        return self.schema.lower()

    @property
    def is_mixed(self) -> bool:
        return "gemengd zondag" in self.low

    @property
    def is_jeugd_1317(self) -> bool:
        return "jongens 13 t/m 17" in self.low or "meisjes 13 t/m 17" in self.low

    @property
    def is_youth(self) -> bool:
        return (
            "junioren" in self.low
            or "groen zondag" in self.low
            or self.is_jeugd_1317
        )

    @property
    def is_4p_combo(self) -> bool:
        return "2de-2he-dd-hd-2gd" in self.low

    @property
    def is_junioren(self) -> bool:
        return "junioren" in self.low

    @property
    def is_groen(self) -> bool:
        return "groen zondag" in self.low

    @property
    def phases(self) -> list[set[str]]:
        """Faseordening uit SPEC.md sectie 5, als lijst van soortgroepen.

        Groepen moeten elkaar in deze volgorde opvolgen: alles in groep n is
        afgelopen voordat groep n+1 begint. Binnen een groep mag alles tegelijk.

        - 8-partijenteam: strikte waterval S -> D -> GD.
        - 5-partijenteam: S en GD samen in fase 1, daarna D.
        - overige teams: S -> D (die hebben geen GD).
        """
        if self.matches == 8:
            return [{"S"}, {"D"}, {"M"}]
        if self.matches == 5:
            return [{"S", "M"}, {"D"}]
        return [{"S"}, {"D", "M"}]

    @property
    def first_start_deadline(self) -> tuple[int | None, int | None, str]:
        """(vroegste, laatste, omschrijving) voor de eerste partij, SPEC.md sectie 2."""
        if self.matches == 8:
            return (10 * 60, 11 * 60, "8-partijenteam: tussen 10:00 en 11:00")
        if self.is_junioren:
            return (None, 13 * 60, "Junioren 11-14: uiterlijk 13:00")
        return (None, 15 * 60, "reguliere teams: uiterlijk 15:00")


def team_key_of(team) -> str:
    """Unieke sleutel van een teamdag.

    `ortools_planner.TeamDay` noemt hem `team_key`, `build_pages.TeamDay`
    `team_id`. Zonder een van beide vallen we terug op datum + schema, wat twee
    teams met hetzelfde schema op één dag samenvoegt — precies wat we willen
    kunnen zien.
    """
    return (
        getattr(team, "team_key", "")
        or getattr(team, "team_id", "")
        or f"{team.date}::{team.schema}"
    )


def expected_from_teams(teams) -> list[ExpectedTeam]:
    """Zet teamdag-objecten om in verwachtingen. Accepteert beide TeamDay-vormen."""
    return [
        ExpectedTeam(
            team_id=team_key_of(t),
            date=t.date,
            schema=t.schema,
            short=short_team_name(t.schema, getattr(t, "home_team", "")),
            duration=t.duration_min,
            matches=t.matches,
            parts=build_parts(t),
            home=(getattr(t, "home_team", "") or "").strip(),
        )
        for t in teams
    ]


def find_season(date: str) -> Path | None:
    """Zoek het seizoensbestand dat deze datum bevat.

    De repo heeft meerdere seizoenen naast elkaar (`season.tsv`,
    `season_2026-2027.tsv`). Een schema noemt alleen zijn datum, dus we zoeken
    zelf het bijbehorende programma op. Staat een datum in meer dan één bestand,
    dan is er geen goede keuze te maken en moet de aanroeper `--season` geven.
    """
    hits = []
    for path in SEASON_FILES:
        teams, _ = parse_input(path)
        if any(t.date == date for t in teams):
            hits.append(path)
    if len(hits) == 1:
        return hits[0]
    return None


def expected_for_date(
    date: str, season: Path | None = None
) -> tuple[list[ExpectedTeam], list[str], Path | None]:
    """Verwachte teams en reserveringssoorten voor een datum.

    Zonder `season` wordt het seizoensbestand bij de datum gezocht. Geeft ook
    terug welk bestand gebruikt is, zodat het rapport dat kan vermelden.
    """
    path = season or find_season(date)
    if path is None:
        return [], [], None
    teams, reservations = parse_input(path)
    expected = expected_from_teams([t for t in teams if t.date == date])
    kinds = [r.kind for r in reservations if r.date == date]
    return expected, kinds, path


# --------------------------------------------------------------------------- #
# uitvoer inlezen
# --------------------------------------------------------------------------- #

def load_rows(path: Path) -> dict[str, list[dict]]:
    """Lees een resultaatbestand en geef {datum: rows}.

    Ondersteunt drie vormen:
      {"date": ..., "rows": [...]}      OR-Tools per dag
      {"06-04-2026": [...], ...}        gold / heuristiek, meerdere dagen
      [...]                             losse rijenlijst (datum uit --date)
    """
    data = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(data, dict) and "rows" in data:
        return {str(data.get("date") or "?"): data["rows"]}
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if isinstance(v, list)}
    if isinstance(data, list):
        return {"?": data}
    raise ValueError(f"onbekende structuur in {path}")


def row_team_key(row: dict) -> str:
    for k in ("team_id", "team", "team_short", "schema"):
        v = (row.get(k) or "").strip()
        if v:
            return v
    return "?"


def is_reservation(row: dict) -> bool:
    if (row.get("kind") or "").strip().upper() in {"R", "O"}:
        return True
    return row_team_key(row).upper() in {"ROOD", "ORANJE"}


# --------------------------------------------------------------------------- #
# teams koppelen
# --------------------------------------------------------------------------- #

def row_keys(row: dict) -> list[tuple]:
    """Sleutels waarmee een rij aan een team gekoppeld kan worden, sterkste eerst.

    Schema's uit verschillende bronnen dragen verschillende velden. De sterkste
    koppeling is schema + thuisteam, want die is uniek en staat in de nieuwe
    uitvoer. Daarna vallen we terug op de losse identifiers, die bij twee teams
    met hetzelfde schema op één dag niet meer onderscheidend zijn.
    """
    schema = (row.get("team") or row.get("schema") or "").strip()
    home = (row.get("home_team") or "").strip()
    keys: list[tuple] = []
    if schema and home:
        keys.append(("schema+thuis", schema, home))
    for field_name in ("team_id", "team_key"):
        v = (row.get(field_name) or "").strip()
        if v:
            keys.append(("id", v))
    for field_name in ("team_short", "team", "schema"):
        v = (row.get(field_name) or "").strip()
        if v:
            keys.append(("naam", v))
    return keys


def team_index(expected: list[ExpectedTeam]) -> dict[tuple, list[ExpectedTeam]]:
    """Bouw een index van dezelfde sleutelvormen als `row_keys` produceert."""
    index: dict[tuple, list[ExpectedTeam]] = defaultdict(list)
    for t in expected:
        if t.home:
            index[("schema+thuis", t.schema, t.home)].append(t)
        index[("id", t.team_id)].append(t)
        # ortools_planner schrijft team_key als "<schema> · <thuisteam>".
        if t.home:
            index[("id", f"{t.schema} \u00b7 {t.home}")].append(t)
        index[("naam", t.short)].append(t)
        index[("naam", t.schema)].append(t)
    return index


def group_rows_by_team(
    rows: list[dict], expected: list[ExpectedTeam], rep: Report, date: str
) -> dict[str, tuple[ExpectedTeam | None, list[dict], list[ExpectedTeam]]]:
    """Koppel rijen aan verwachte teams.

    Lukt de koppeling op schema + thuisteam, dan is hij eenduidig. Draagt een
    schema alleen de schemanaam en delen twee teams die naam op één dag, dan zijn
    ze in dat bestand niet te scheiden; dat melden we als `AMBIGU-TEAM`.
    """
    index = team_index(expected)

    buckets: dict[str, list[dict]] = defaultdict(list)
    resolved: dict[str, ExpectedTeam | None] = {}
    sharing: dict[str, list[ExpectedTeam]] = {}

    for row in rows:
        if is_reservation(row):
            continue
        team, group_of = None, []
        for key in row_keys(row):
            hits = index.get(key, [])
            if len(hits) == 1:
                team = hits[0]
                break
            if len(hits) > 1 and not group_of:
                group_of = hits
        label = team.team_id if team else (
            f"AMBIGU::{group_of[0].schema}" if group_of else row_team_key(row)
        )
        buckets[label].append(row)
        resolved[label] = team
        sharing[label] = group_of

    for label, group in buckets.items():
        team = resolved[label]
        if team is not None:
            continue
        if sharing[label]:
            rep.add(
                "AMBIGU-TEAM", "HARD", date,
                f"{len(sharing[label])} teams delen dit schema en het schema draagt "
                f"geen thuisteam, dus ze zijn niet te scheiden. Teamregels worden "
                f"op de samengevoegde groep getoetst en zijn dus te streng.",
                subject=sharing[label][0].schema,
            )
        else:
            rep.add(
                "ONBEKEND-TEAM", "HARD", date,
                "rijen horen bij geen enkel team uit het wedstrijdprogramma",
                subject=row_team_key(group[0]),
            )

    return {k: (resolved[k], v, sharing[k]) for k, v in buckets.items()}


# --------------------------------------------------------------------------- #
# checks
# --------------------------------------------------------------------------- #

def check_rows_wellformed(
    rows: list[dict], rep: Report, date: str
) -> tuple[list[dict], list[dict]]:
    """Basisvorm: leesbare tijden, kwartierraster, baan 1-10.

    Geeft (geplande rijen, niet-geplande rijen) terug. Niet-geplande rijen staan
    wél in de uitvoer — ze houden hun team en partij, alleen geen tijd of baan —
    dus ze doen mee aan de teamkoppeling en aan `check_completeness`.
    """
    ok: list[dict] = []
    unplanned: list[dict] = []
    for row in rows:
        subject = f"{row_team_key(row)} {row.get('part', '?')}"
        start, end = hhmm_to_min(row.get("start")), hhmm_to_min(row.get("end"))

        if (row.get("start") or "") == UNPLANNED:
            unplanned.append(row)
            continue
        if start is None or end is None:
            rep.add("VORM", "HARD", date, f"onleesbare tijd {row.get('start')!r}-{row.get('end')!r}", subject)
            continue
        if end <= start:
            rep.add("VORM", "HARD", date, f"eind {to_hhmm(end)} ligt niet na start {to_hhmm(start)}", subject)
            continue
        if start % SLOT or end % SLOT:
            rep.add("RASTER", "HARD", date, f"{to_hhmm(start)}-{to_hhmm(end)} valt niet op het kwartierraster", subject)

        court = row.get("court")
        if not isinstance(court, int) or court not in COURTS:
            rep.add("BAAN", "HARD", date, f"baan {court!r} bestaat niet (1-10)", subject)
            continue

        if start > LAST_START:
            rep.add("LAATSTE-START", "HARD", date,
                    f"start {to_hhmm(start)} is na 19:30", subject)

        ok.append({**row, "_start": start, "_end": end, "_court": court})
    return ok, unplanned


def check_court_overlap(rows: list[dict], rep: Report, date: str) -> None:
    """Maximaal één partij per baan per tijdslot."""
    occupied: dict[tuple[int, int], dict] = {}
    for row in sorted(rows, key=lambda r: (r["_court"], r["_start"])):
        for t in slots(row["_start"], row["_end"]):
            key = (row["_court"], t)
            other = occupied.get(key)
            if other is not None:
                rep.add(
                    "BAAN-OVERLAP", "HARD", date,
                    f"baan {row['_court']} om {to_hhmm(t)} is dubbel bezet: "
                    f"{row_team_key(other)} {other.get('part')} en "
                    f"{row_team_key(row)} {row.get('part')}",
                )
            else:
                occupied[key] = row


def check_duration(rows: list[dict], team: ExpectedTeam, rep: Report, date: str) -> None:
    for row in rows:
        got = row["_end"] - row["_start"]
        if got != team.duration:
            rep.add("DUUR", "HARD", date,
                    f"{row.get('part')} duurt {got} min, season.tsv zegt {team.duration} min",
                    subject=team.short)


def check_completeness(
    rows: list[dict], team: ExpectedTeam, rep: Report, date: str
) -> None:
    """Elke partij uit season.tsv precies één keer, geen onbekende partijen."""
    want = {label for label, _ in team.parts}
    got = defaultdict(int)
    marked_unplanned = set()
    for row in rows:
        part = (row.get("part") or "?").strip()
        got[part] += 1
        if "_start" not in row:
            marked_unplanned.add(part)

    missing = {p for p in want if got.get(p, 0) == 0} | (marked_unplanned & want)
    if missing:
        rep.add("NIET-GEPLAND", "HARD", date,
                f"{len(missing)} van {len(want)} partijen niet gepland: "
                f"{', '.join(sorted(missing))}", subject=team.short)

    for part, n in sorted(got.items()):
        if n > 1:
            rep.add("DUBBEL-GEPLAND", "HARD", date,
                    f"{part} staat {n}x in het schema", subject=team.short)
        if part not in want:
            rep.add("ONBEKENDE-PARTIJ", "HARD", date,
                    f"{part} komt niet voor in season.tsv "
                    f"(verwacht: {', '.join(sorted(want))})", subject=team.short)


def check_completeness_merged(
    rows: list[dict], teams: list[ExpectedTeam], rep: Report, date: str
) -> None:
    """Volledigheid voor een groep teams die in de uitvoer niet te scheiden zijn.

    De partijlabels van de teams overlappen (allebei S1, D1, ...), dus we kunnen
    ze niet per partij nalopen. We tellen daarom alleen aantallen.
    """
    want = sum(len(t.parts) for t in teams)
    planned = len([r for r in rows if "_start" in r])
    if planned < want:
        rep.add("NIET-GEPLAND", "HARD", date,
                f"{want - planned} van {want} partijen niet gepland "
                f"(samengevoegde groep van {len(teams)} teams)",
                subject=" + ".join(t.short for t in teams))


def team_slot_map(rows: list[dict]) -> dict[int, list[dict]]:
    per_slot = defaultdict(list)
    for row in rows:
        for t in slots(row["_start"], row["_end"]):
            per_slot[t].append(row)
    return per_slot


def merge_slots(times: list[int]) -> str:
    """[555, 570, 585, 660] -> '09:15-10:00, 11:00-11:15' (eind exclusief)."""
    if not times:
        return ""
    spans, lo, prev = [], times[0], times[0]
    for t in times[1:]:
        if t == prev + SLOT:
            prev = t
            continue
        spans.append((lo, prev + SLOT))
        lo = prev = t
    spans.append((lo, prev + SLOT))
    return ", ".join(f"{to_hhmm(a)}-{to_hhmm(b)}" for a, b in spans)


def report_slot_findings(
    hits: dict[str, list[int]], rule: str, severity: str,
    rep: Report, date: str, subject: str,
) -> None:
    """Vouw per-slot overtredingen samen tot één bevinding per oorzaak."""
    for reason, times in sorted(hits.items()):
        rep.add(rule, severity, date,
                f"{reason} ({merge_slots(sorted(times))})", subject=subject)


def check_player_capacity(
    rows: list[dict], team: ExpectedTeam, rep: Report, date: str
) -> None:
    """Een team heeft 4 spelers: nooit meer dan 4 spelers tegelijk in het veld.

    Let op: "maximaal 2 partijen tegelijk" is géén spelersregel — drie singles
    kosten drie spelers en passen dus binnen een team van vier. Die grens volgt
    uit de baanlimiet van het model en staat in `check_concurrent_matches`.
    """
    hits: dict[str, list[int]] = defaultdict(list)
    for t, here in sorted(team_slot_map(rows).items()):
        male = female = total = 0
        for row in here:
            m, f, tot = player_demand(team.schema, row.get("part") or "", row.get("kind") or "")
            male, female, total = male + m, female + f, total + tot
        if total > 4:
            hits[f"{total} spelers nodig, team heeft 4"].append(t)
        if team.is_mixed and male > 2:
            hits[f"{male} heren nodig, max 2"].append(t)
        if team.is_mixed and female > 2:
            hits[f"{female} dames nodig, max 2"].append(t)

    report_slot_findings(hits, "SPELERS", "HARD", rep, date, team.short)


def check_concurrent_matches(
    rows: list[dict], team: ExpectedTeam, rep: Report, date: str
) -> None:
    """MODEL: max 2 partijen tegelijk per team (gevolg van de baanlimiet van 2)."""
    hits: dict[str, list[int]] = defaultdict(list)
    for t, here in sorted(team_slot_map(rows).items()):
        if len(here) > 2:
            parts = ", ".join(sorted(r.get("part", "?") for r in here))
            hits[f"{len(here)} partijen tegelijk ({parts}), model staat 2 toe"].append(t)
    report_slot_findings(hits, "TEGELIJK", "MODEL", rep, date, team.short)


def check_kind_conflicts(
    rows: list[dict], team: ExpectedTeam, rep: Report, date: str
) -> None:
    """S niet tegelijk met D; D niet tegelijk met GD; bij 4-spelersschema S ook niet met GD."""
    forbidden = [("S", "D"), ("D", "M")]
    if team.is_4p_combo:
        forbidden.append(("S", "M"))

    labels = {"S": "singles", "D": "dubbels", "M": "gemengd dubbel"}
    hits: dict[str, list[int]] = defaultdict(list)
    for t, here in sorted(team_slot_map(rows).items()):
        present = {(r.get("kind") or "").strip() for r in here}
        for a, b in forbidden:
            if a in present and b in present:
                hits[f"{labels[a]} en {labels[b]} spelen tegelijk"].append(t)

    report_slot_findings(hits, "SOORT-CONFLICT", "HARD", rep, date, team.short)


def check_phases(
    rows: list[dict], team: ExpectedTeam, rep: Report, date: str
) -> None:
    """SPEC.md sectie 5: de fases van een team moeten elkaar netjes opvolgen.

    Welke soorten in welke fase zitten hangt af van het teamtype; zie
    `ExpectedTeam.phases`. Binnen een fase mag alles tegelijk — dat is juist de
    bedoeling van de breedte-regels.
    """
    groups = []
    for kinds in team.phases:
        here = [r for r in rows if (r.get("kind") or "") in kinds]
        if here:
            groups.append((kinds, here))

    # Oscar, 26-08-2026: de 8-partijenteams spelen landelijke competitie op hoog
    # niveau en zijn strikt in de fasering. Voor de overige teams is het een
    # sterke voorkeur en weegt een beter schema zwaarder.
    severity = "HARD" if team.matches == 8 else "MODEL"

    for (kinds_a, earlier), (kinds_b, later) in zip(groups, groups[1:]):
        latest_end = max(r["_end"] for r in earlier)
        too_early = [r for r in later if r["_start"] < latest_end]
        if too_early:
            rep.add("FASE", severity, date,
                    f"{', '.join(sorted(r.get('part', '?') for r in too_early))} "
                    f"start voor fase {'+'.join(sorted(kinds_a))} klaar is "
                    f"({to_hhmm(latest_end)})", subject=team.short)


def check_first_start(
    rows: list[dict], team: ExpectedTeam, rep: Report, date: str
) -> None:
    """SPEC.md sectie 2: deadline voor de eerste partij van een team.

    Groen heeft in de spec geen eigen deadline. Tot dat is uitgezocht melden we
    Groen apart en als MODEL, zodat de aanname niet als spec-regel telt.
    """
    if not rows:
        return
    first = min(r["_start"] for r in rows)
    earliest, latest, what = team.first_start_deadline

    rule, severity = "EERSTE-START", "HARD"
    if team.is_groen:
        rule, severity = "EERSTE-START-GROEN", "MODEL"
        what += " — aangenomen voor Groen, staat niet in de spec"

    if latest is not None and first > latest:
        rep.add(rule, severity, date,
                f"eerste partij start {to_hhmm(first)}; {what}", subject=team.short)
    if earliest is not None and first < earliest:
        rep.add(rule, severity, date,
                f"eerste partij start {to_hhmm(first)}, te vroeg; {what}",
                subject=team.short)


def check_courts_per_team(
    rows: list[dict], team: ExpectedTeam, rep: Report, date: str
) -> None:
    """MODEL: max 2 banen per team, en alleen binnen één aangrenzend baanpaar."""
    used = sorted({r["_court"] for r in rows})
    if len(used) > 2:
        rep.add("BANEN-PER-TEAM", "MODEL", date,
                f"gebruikt {len(used)} banen ({used}), model staat 2 toe", subject=team.short)
    if used and not any(set(used) <= set(pair) for pair in COURT_PAIRS):
        rep.add("BAANPAAR", "MODEL", date,
                f"banen {used} vormen geen aangrenzend paar "
                f"({', '.join(f'{a}+{b}' for a, b in COURT_PAIRS)})", subject=team.short)


def check_blocks(rows: list[dict], team: ExpectedTeam, rep: Report, date: str) -> None:
    """MODEL: max 2 aaneengesloten speelblokken per team."""
    busy = sorted(team_slot_map(rows))
    if not busy:
        return
    blocks = 1
    gaps = []
    for prev, cur in zip(busy, busy[1:]):
        if cur - prev > SLOT:
            blocks += 1
            gaps.append(f"{to_hhmm(prev + SLOT)}-{to_hhmm(cur)}")
    if blocks > 2:
        rep.add("BLOKKEN", "MODEL", date,
                f"{blocks} speelblokken (gaten: {', '.join(gaps)}), model staat 2 toe",
                subject=team.short)


def check_time_windows(
    rows: list[dict], team: ExpectedTeam, rep: Report, date: str
) -> None:
    """MODEL: leeftijds- en schemavensters zoals het CP-SAT model ze oplegt."""
    for row in rows:
        s, part = row["_start"], row.get("part", "?")
        # Besluit Oscar/Koen 2026-08-27 (commit 5f00463): "Gemengd niet voor
        # 10:00" is alleen nog HARD voor 8-partijenteams (landelijke
        # competitie, reistijd). Overige Gemengd-teams (5-partijenteams e.d.)
        # hebben geen harde ondergrens meer; zij mogen ook vroeger starten,
        # met leeftijdsvolgorde als zachte voorkeur. Zie ortools_planner.py
        # regel ~412 voor de implementatie van dit onderscheid.
        if team.is_mixed and team.matches == 8 and s < 10 * 60:
            rep.add("VENSTER-GEM", "HARD", date,
                    f"{part} start {to_hhmm(s)}, gemengd 8-partijenteam start pas "
                    f"vanaf 10:00 (SPEC.md sectie 4)", subject=team.short)
        elif team.is_mixed and team.matches != 8 and s < 10 * 60:
            rep.add("VENSTER-GEM", "MODEL", date,
                    f"{part} start {to_hhmm(s)}, model laat niet-8p Gemengd ook "
                    f"voor 10:00 toe — dit is met besluit 2026-08-27 een zachte "
                    f"voorkeur geworden", subject=team.short)
        if team.is_jeugd_1317 and s < 11 * 60:
            rep.add("VENSTER-JEUGD", "MODEL", date,
                    f"{part} start {to_hhmm(s)}, model dwingt jeugd 13-17 vanaf "
                    f"11:00 af — die grens is met SPEC.md ingetrokken",
                    subject=team.short)
        if team.is_youth and s > 17 * 60 + 30:
            rep.add("VENSTER-JEUGD-LAAT", "MODEL", date,
                    f"{part} start {to_hhmm(s)}, jeugd niet na 17:30", subject=team.short)


def reservation_windows(res_kinds: list[str], day_start: int) -> list[tuple]:
    """Gereserveerde (baan, van, tot, soort) volgens SPEC.md sectie 3.

    Rood staat altijd op baan 1 — Oscar, 26-08-2026: naast die baan is extra
    ruimte die meegebruikt wordt. Speelt Rood mee, dan wijkt Oranje uit naar
    baan 2, 3 en 4. Beide beginnen op de dagstart.
    """
    heeft_rood = "rood" in res_kinds
    windows = []
    if heeft_rood:
        windows.append((1, day_start, day_start + 60, "rood"))
    if "oranje" in res_kinds:
        banen = (2, 3, 4) if heeft_rood else (1, 2, 3)
        windows += [(c, day_start, day_start + 120, "oranje") for c in banen]
    return windows


def check_reservations(
    rows: list[dict], res_kinds: list[str], rep: Report, date: str
) -> None:
    """Rood/oranje reserveringen: juiste baan, juiste duur, en vanaf de dagstart.

    Staan de reserveringen als rij in het schema (gold, heuristiek), dan toetsen
    we baan, duur en starttijd. Staan ze er niet in (OR-Tools uitvoer), dan
    toetsen we of de banen die gereserveerd horen te zijn ook vrij zijn gebleven.
    """
    if not res_kinds:
        return

    planned = [r for r in rows if not is_reservation(r) and "_start" in r]
    res_rows = [r for r in rows if is_reservation(r) and "_start" in r]
    if not planned and not res_rows:
        return

    # De dagstart is het vroegste moment waarop er iets gebeurt, inclusief de
    # reserveringen zelf — die beginnen er per definitie op.
    day_start = min(r["_start"] for r in (res_rows + planned))
    windows = reservation_windows(res_kinds, day_start)

    if res_rows:
        for row in res_rows:
            kind = "rood" if row_team_key(row).upper() == "ROOD" else "oranje"
            duur_ok = 60 if kind == "rood" else 120
            got = row["_end"] - row["_start"]
            if got != duur_ok:
                rep.add("RESERVERING", "HARD", date,
                        f"{kind} duurt {got} min, verwacht {duur_ok}",
                        subject=row_team_key(row))
            if row["_start"] != day_start:
                rep.add("RESERVERING", "HARD", date,
                        f"{kind} start {to_hhmm(row['_start'])}, maar de dag begint "
                        f"om {to_hhmm(day_start)}", subject=row_team_key(row))
            toegestaan = {c for c, _, _, k in windows if k == kind}
            if toegestaan and row["_court"] not in toegestaan:
                rep.add("RESERVERING", "HARD", date,
                        f"{kind} staat op baan {row['_court']}, verwacht "
                        f"{sorted(toegestaan)}", subject=row_team_key(row))
        return

    rep.add("RESERVERING", "INFO", date,
            f"geen reserveringsrijen in het schema; getoetst of de {len(windows)} "
            f"gereserveerde baanvensters vrij zijn, met dagstart {to_hhmm(day_start)}")

    for court, ws, we, kind in windows:
        for row in planned:
            if row["_court"] == court and row["_start"] < we and ws < row["_end"]:
                rep.add("RESERVERING", "HARD", date,
                        f"{row_team_key(row)} {row.get('part')} staat op baan {court} om "
                        f"{to_hhmm(row['_start'])}, maar die is voor {kind} gereserveerd "
                        f"tot {to_hhmm(we)}")


# --------------------------------------------------------------------------- #
# aansturing
# --------------------------------------------------------------------------- #

def validate_day(
    date: str,
    teams,
    rows: list[dict],
    rep: Report | None = None,
    res_kinds: list[str] | None = None,
) -> Report:
    """Valideer één speeldag tegen een expliciet meegegeven teamlijst.

    Gebruik deze vorm als je de teams zelf samenstelt — in tests, of wanneer de
    brondata niet uit een seizoens-tsv komt. `validate_date` is de variant die de
    teams uit een seizoensbestand leest.

    `teams` mag zowel `ortools_planner.TeamDay` als `build_pages.TeamDay` zijn.
    """
    rep = rep if rep is not None else Report()
    expected = expected_from_teams([t for t in teams if t.date == date])
    _validate(date, expected, res_kinds or [], rows, rep)
    return rep


def validate_date(
    date: str, rows: list[dict], rep: Report, season: Path | None = None
) -> None:
    """Valideer één speeldag met de teams uit het seizoensbestand."""
    expected, res_kinds, used = expected_for_date(date, season)
    if not expected:
        namen = ", ".join(p.name for p in SEASON_FILES) or "geen"
        rep.add("ONBEKENDE-DATUM", "HARD", date,
                f"datum staat in geen enkel seizoensbestand ({namen}), of in "
                f"meer dan één; geef dan --season op")
        return
    rep.sources[date] = used.name if used else "?"
    _validate(date, expected, res_kinds, rows, rep)


def _validate(
    date: str,
    expected: list[ExpectedTeam],
    res_kinds: list[str],
    rows: list[dict],
    rep: Report,
) -> None:

    clean, unplanned = check_rows_wellformed(rows, rep, date)
    check_court_overlap([r for r in clean if not is_reservation(r)], rep, date)
    check_reservations(clean, res_kinds, rep, date)

    groups = group_rows_by_team(clean + unplanned, expected, rep, date)
    seen_keys = set()

    for key, (team, group, sharing) in sorted(groups.items()):
        if team is None:
            if sharing:
                check_completeness_merged(group, sharing, rep, date)
            continue
        seen_keys.update({team.team_id, team.short, team.schema})
        planned = [r for r in group if "_start" in r]

        check_completeness(group, team, rep, date)
        check_duration(planned, team, rep, date)
        check_player_capacity(planned, team, rep, date)
        check_concurrent_matches(planned, team, rep, date)
        check_kind_conflicts(planned, team, rep, date)
        check_phases(planned, team, rep, date)
        check_first_start(planned, team, rep, date)
        check_courts_per_team(planned, team, rep, date)
        check_blocks(planned, team, rep, date)
        check_time_windows(planned, team, rep, date)

    for team in expected:
        if not {team.team_id, team.short, team.schema} & (seen_keys | set(groups)):
            rep.add("TEAM-ONTBREEKT", "HARD", date,
                    f"geen enkele partij van dit team in de uitvoer, ook niet als "
                    f"niet-gepland ({team.matches} verwacht)", subject=team.short)

    rep.stats[date] = {
        "teams_verwacht": len(expected),
        "partijen_verwacht": sum(len(t.parts) for t in expected),
        "partijen_gepland": len([r for r in clean if not is_reservation(r)]),
        "partijen_niet_gepland": len(unplanned),
        "hard": len([f for f in rep.findings if f.date == date and f.severity == "HARD"]),
        "model": len([f for f in rep.findings if f.date == date and f.severity == "MODEL"]),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", type=Path, help="resultaatbestand(en)")
    ap.add_argument("--date", help="alleen deze datum valideren")
    ap.add_argument("--all", action="store_true", help="alle datums in het bestand")
    ap.add_argument("--strict", action="store_true", help="MODEL-overtredingen ook als fout")
    ap.add_argument("--max-hard", type=int, metavar="N",
                    help="sta N HARD-overtredingen toe (ratchet voor CI); "
                         "faal bij meer, en ook bij minder zodat je N verlaagt")
    ap.add_argument("--max-model", type=int, metavar="N",
                    help="idem voor MODEL-overtredingen")
    ap.add_argument("--json", type=Path, help="schrijf bevindingen als JSON")
    ap.add_argument("--quiet", action="store_true", help="alleen de samenvatting")
    ap.add_argument("--season", type=Path, metavar="TSV",
                    help="wedstrijdprogramma om tegen te toetsen; standaard wordt "
                         "het bestand in data/ gezocht dat de datum bevat")
    args = ap.parse_args()

    rep = Report()
    for path in args.paths:
        if not path.exists():
            print(f"! bestand bestaat niet: {path}", file=sys.stderr)
            return 2
        per_date = load_rows(path)
        if args.date:
            per_date = {k: v for k, v in per_date.items() if k == args.date}
            if not per_date:
                print(f"! datum {args.date} niet in {path}", file=sys.stderr)
                return 2
        elif not args.all and len(per_date) > 1:
            print(f"! {path} bevat {len(per_date)} datums; kies --date of --all",
                  file=sys.stderr)
            return 2

        print(f"\n=== {path.name} ===")
        for date, rows in sorted(per_date.items()):
            before = len(rep.findings)
            validate_date(date, rows, rep, args.season)
            new = rep.findings[before:]
            s = rep.stats.get(date, {})
            bron = rep.sources.get(date, "?")
            head = (f"{date}  {s.get('partijen_gepland', 0)}/"
                    f"{s.get('partijen_verwacht', 0)} partijen  "
                    f"HARD={s.get('hard', 0)} MODEL={s.get('model', 0)}"
                    f"  [{bron}]")
            print(f"\n{head}")
            if not args.quiet:
                for f in new:
                    print(f.line())

    hard = rep.by_severity("HARD")
    model = rep.by_severity("MODEL")

    per_rule = defaultdict(int)
    for f in rep.findings:
        if f.severity != "INFO":
            per_rule[(f.severity, f.rule)] += 1
    if per_rule:
        print("\n--- per regel ---")
        for (sev, rule), n in sorted(per_rule.items(), key=lambda kv: (kv[0][0], -kv[1])):
            print(f"  {sev:5s} {rule:20s} {n}")
    print(f"\n--- totaal: {len(hard)} HARD, {len(model)} MODEL ---")

    if args.json:
        args.json.write_text(
            json.dumps({"findings": [asdict(f) for f in rep.findings],
                        "stats": rep.stats}, indent=2, ensure_ascii=False),
            encoding="utf-8")
        print(f"rapport geschreven naar {args.json}")

    exit_code = 0
    for label, found, limit in (("HARD", hard, args.max_hard),
                                ("MODEL", model, args.max_model)):
        if limit is None:
            continue
        if len(found) > limit:
            print(f"FOUT: {len(found)} {label}-overtredingen, plafond is {limit} "
                  f"— dit is een regressie.")
            exit_code = 1
        elif len(found) < limit:
            print(f"FOUT: nog maar {len(found)} {label}-overtredingen terwijl het "
                  f"plafond {limit} is. Zet --max-{label.lower()} op {len(found)} "
                  f"zodat de winst vastligt.")
            exit_code = 1
        else:
            print(f"OK: {len(found)} {label}-overtredingen, gelijk aan het plafond.")

    if args.max_hard is None and args.max_model is None:
        if hard or (args.strict and model):
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
