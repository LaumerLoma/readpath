FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
ENV JIT_DB_PATH=/data/jit.db
EXPOSE 8766
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8766"]
