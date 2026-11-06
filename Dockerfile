FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir '.[infra,tracing]' && useradd --uid 10001 --create-home app
COPY alembic.ini ./
COPY migrations ./migrations
USER app
EXPOSE 8000
CMD ["uvicorn", "evonext.app.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
