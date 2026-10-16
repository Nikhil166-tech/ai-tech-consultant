FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /app/data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8002
ENV TASK1_API_URL=http://task1:8000

EXPOSE 8002

HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=5 \
    CMD curl -f http://localhost:8002/health || exit 1

CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8002"]
