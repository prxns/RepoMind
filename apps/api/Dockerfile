FROM python:3.11-slim
WORKDIR /app
COPY apps/api/pyproject.toml /app/pyproject.toml
COPY apps/api/repomind /app/repomind
COPY apps/api/migrations /app/migrations
COPY apps/api/alembic.ini /app/alembic.ini
RUN pip install --no-cache-dir .
EXPOSE 8000
CMD ["uvicorn", "repomind.api:app", "--host", "0.0.0.0", "--port", "8000"]
