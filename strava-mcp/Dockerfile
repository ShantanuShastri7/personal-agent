FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run injects PORT at runtime — this is just the default fallback
ENV PORT=8080

CMD ["python", "server.py"]
