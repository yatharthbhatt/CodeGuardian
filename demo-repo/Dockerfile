# Intentionally weak Dockerfile (for the DevOps agent demo). DO NOT USE IN PRODUCTION.
FROM python:latest
COPY . /app
WORKDIR /app
RUN pip install -r requirements.txt
CMD ["python", "app.py"]
