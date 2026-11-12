FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim AS backend-build
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./backend/
COPY backend/src ./backend/src
RUN uv sync --project backend --locked --no-dev --no-editable

FROM python:3.11-slim AS runtime
ENV PATH="/app/backend/.venv/bin:${PATH}" \
    FRONTEND_DIST="/app/frontend/dist" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=backend-build /app/backend/.venv /app/backend/.venv
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist
RUN groupadd --system app && useradd --system --gid app --home-dir /app app \
    && chown -R app:app /app
USER app:app
EXPOSE 8000
CMD ["uvicorn", "aimplify_intake.main:app", "--host", "0.0.0.0", "--port", "8000"]
