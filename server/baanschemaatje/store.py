"""Opslag voor clubs (profiel, seizoen, metadata).

``BS_STORE`` = ``gs://<bucket>`` (Cloud Run) of een lokale map (tests/lokaal).
Indeling per club::

    clubs/<id>/meta.json      id, tijden, gehashte bewerk-sleutel, seizoen-info
    clubs/<id>/profile.json   clubprofiel (zelfde schema als clubs/*.yaml)
    clubs/<id>/season.tsv     genormaliseerd seizoen (uit de KNLTB-export)
    clubs/<id>/schedules/<dd-mm-YYYY>.json   opgeslagen baanschema van een dag
    clubs/<id>/moves.json     opgeslagen verzettingen (seizoensniveau)
"""

from __future__ import annotations

import os
from pathlib import Path


class LocalStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> bytes | None:
        p = self.root / key
        return p.read_bytes() if p.is_file() else None

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        p = self.root / key
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(p)

    def delete(self, key: str) -> bool:
        p = self.root / key
        if p.is_file():
            p.unlink()
            return True
        return False

    def list(self, prefix: str) -> list[str]:
        base = self.root / prefix
        d = base if prefix.endswith("/") else base.parent
        if not d.is_dir():
            return []
        out = [str(p.relative_to(self.root)).replace("\\", "/") for p in d.rglob("*") if p.is_file() and not p.name.endswith(".tmp")]
        return sorted(k for k in out if k.startswith(prefix))

    def list_clubs(self) -> list[str]:
        d = self.root / "clubs"
        return sorted(x.name for x in d.iterdir() if (x / "meta.json").is_file()) if d.is_dir() else []

    def describe(self) -> str:
        return f"local:{self.root}"


class GCSStore:
    def __init__(self, bucket: str):
        from google.cloud import storage  # pas laden als nodig

        self.bucket_name = bucket
        self.bucket = storage.Client().bucket(bucket)

    def get(self, key: str) -> bytes | None:
        from google.api_core.exceptions import NotFound

        try:
            return self.bucket.blob(key).download_as_bytes()
        except NotFound:
            return None

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        self.bucket.blob(key).upload_from_string(data, content_type=content_type)

    def delete(self, key: str) -> bool:
        from google.api_core.exceptions import NotFound

        try:
            self.bucket.blob(key).delete()
            return True
        except NotFound:
            return False

    def list(self, prefix: str) -> list[str]:
        return sorted(b.name for b in self.bucket.list_blobs(prefix=prefix))

    def list_clubs(self) -> list[str]:
        ids = set()
        for b in self.bucket.list_blobs(prefix="clubs/"):
            parts = b.name.split("/")
            if len(parts) == 3 and parts[2] == "meta.json":
                ids.add(parts[1])
        return sorted(ids)

    def describe(self) -> str:
        return f"gs://{self.bucket_name}"


def make_store(spec: str | None = None):
    spec = spec or os.environ.get("BS_STORE") or "/tmp/baanschemaatje-store"
    return GCSStore(spec[5:]) if spec.startswith("gs://") else LocalStore(spec)
