FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8002
ENV TASK1_API_URL=http://task1:8000

EXPOSE 8002

CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8002"]
