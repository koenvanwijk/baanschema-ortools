"""Club (her)aanmaken in de store vanaf de command line (seeden).

    python seed_club.py --id mierlo --profile ../../clubs/mierlo.yaml \\
        --season ../../data/season_2026-2027.tsv --store /tmp/seed
    gcloud storage cp -r /tmp/seed/clubs gs://baanschemaatje-clubs/
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from store import make_store  # noqa: E402

from baanschemaatje import miniyaml  # noqa: E402
from baanschemaatje.knltb_import import parse_export, to_tsv  # noqa: E402
from baanschemaatje.profile import profile_from_dict  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--profile", required=True, type=Path)
    ap.add_argument("--season", type=Path)
    ap.add_argument("--store", required=True)
    ap.add_argument("--demo", action="store_true", help="markeer als democlub")
    a = ap.parse_args()
    raw = miniyaml.loads(a.profile.read_text(encoding="utf-8")) if a.profile.suffix != ".json" \
        else json.loads(a.profile.read_text(encoding="utf-8"))
    prof = profile_from_dict(raw, source=str(a.profile))
    st = make_store(a.store)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    meta = {"id": a.id, "name": prof.name, "created_at": now, "updated_at": now, "season": None,
            "seeded_from": a.profile.name, "demo": a.demo}
    if a.season:
        rows, rep = parse_export(a.season.read_bytes(), a.season.name, prof.knltb_name)
        st.put(f"clubs/{a.id}/season.tsv", to_tsv(rows).encode(), "text/tab-separated-values")
        meta["season"] = {"filename": a.season.name, "uploaded_at": now, "report": rep}
    st.put(f"clubs/{a.id}/profile.json", json.dumps(raw, ensure_ascii=False, indent=1).encode(), "application/json")
    st.put(f"clubs/{a.id}/meta.json", json.dumps(meta, ensure_ascii=False, indent=1).encode(), "application/json")
    print(f"club {a.id} geschreven naar {st.describe()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
