# Baanschemaatje live-backend. Build-context = repo-root:
#   docker build -f server/baanschemaatje/Dockerfile .
# (of: gcloud builds submit --config server/baanschemaatje/cloudbuild.yaml .)
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080 BS_ROOT=/app
WORKDIR /app
COPY server/baanschemaatje/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
# Planner + validator, plus de statische web-app (web/baanschemaatje); geen backend/.
COPY pyproject.toml README.md /app/
COPY src /app/src
RUN pip install --no-cache-dir --no-deps -e /app
COPY clubs /app/clubs
COPY data/season_2026-2027.tsv /app/data/season_2026-2027.tsv
COPY scripts/validate_schedule.py scripts/build_pages.py /app/scripts/
COPY docs/SPEC.md /app/docs/SPEC.md
COPY server/baanschemaatje /app/server/baanschemaatje
# Statische web-app voor de vaste clublink (/club/<id> → /app/club.html#<id>).
COPY web/baanschemaatje /app/web/baanschemaatje
WORKDIR /app/server/baanschemaatje
EXPOSE 8080
CMD exec uvicorn app:app --host 0.0.0.0 --port ${PORT} --workers 1
