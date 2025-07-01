FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Set the PORT environment variable as expected by Cloud Run
ENV PORT 8080

CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 app:app