FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY config.yaml ./config.yaml

ENV PYTHONPATH=/app/src:/app/src/generated
CMD ["python", "-m", "src.run", "--config", "/app/config.yaml"]
