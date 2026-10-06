FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    useradd --uid 10001 --create-home digest && mkdir -p /app/data && chown digest:digest /app/data
COPY --chown=digest:digest src ./src
COPY --chown=digest:digest config ./config
COPY --chown=digest:digest prompts ./prompts
USER digest
EXPOSE 8000
CMD ["uvicorn", "src.digest.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
