FROM python:3.12-slim

# Не пишем .pyc и не буферизуем stdout -- логи сразу видны в docker logs.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Сначала только зависимости: этот слой кешируется и не пересобирается,
# пока не поменяется requirements.txt.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Не запускаем приложение от root.
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

# Ровно один воркер: in-memory хранилище (и позже метрики) живут в памяти
# процесса. С несколькими воркерами у каждого было бы свое состояние.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
