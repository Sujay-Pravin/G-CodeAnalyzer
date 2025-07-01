# Use the official Python image as a base
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install git (required by GitPython)
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Copy the application code
COPY . .

# Expose the port Flask runs on
EXPOSE 8080 

# Cloud Run expects applications to listen on port 8080

# Run the Flask app
# Use Gunicorn for production-ready Flask server
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 app:app