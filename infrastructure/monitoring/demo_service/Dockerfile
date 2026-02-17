FROM python:3.12-slim
WORKDIR /app
COPY send_demo.py /app/send_demo.py
RUN pip install --no-cache-dir opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp requests
CMD ["python", "send_demo.py"]
