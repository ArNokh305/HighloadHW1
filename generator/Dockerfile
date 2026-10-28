FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /generator

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home generator
USER generator

# Без аргументов: все настройки приходят из environment в docker-compose.
CMD ["python", "generate.py"]
