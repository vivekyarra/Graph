FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
ENV MAELIN_ENABLE_DEMO_MUTATIONS=1
COPY maelin /app/maelin
COPY data /app/data
COPY static /app/static
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn maelin.api:api --host 0.0.0.0 --port ${PORT:-8000}"]
