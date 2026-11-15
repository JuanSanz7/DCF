# --- build the web UI
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- python app
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DCF_DATA_DIR=/data DCF_STATIC_DIR=/app/static PORT=7860 HOME=/home/app
WORKDIR /app
COPY backend/pyproject.toml ./backend/
COPY backend/dcfmc ./backend/dcfmc
RUN pip install --no-cache-dir ./backend
COPY --from=web /web/dist /app/static
# run as an unprivileged user (uid 1000, as Hugging Face Spaces expects)
RUN useradd -m -u 1000 app && mkdir -p /data && chown -R app /data
USER app
EXPOSE 7860
CMD ["python", "-m", "dcfmc", "serve", "--host", "0.0.0.0"]
