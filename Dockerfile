FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY maelin /app/maelin
COPY data /app/data
COPY static /app/static
EXPOSE 8000
CMD ["uvicorn", "maelin.api:api", "--host", "0.0.0.0", "--port", "8000"]
