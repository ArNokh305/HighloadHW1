# app/metrics.py
import os
import time

from fastapi import FastAPI, Request, Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

POD_ID = os.getenv("POD_ID", "unknown")
DATACENTER = os.getenv("DATACENTER", "unknown")

# метрики — на уровне модуля (создаются один раз при импорте)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "Request duration",
    ['method','datacenter','pod_id','route'],            # TODO: какие лейблы? (подсказка: без status — подумай, нужен ли он тут)
    buckets=(0.0005,0.001,0.0025,0.005,0.01,0.025,0.05,0.1,0.25,0.5,1,2.5),    # TODO: под какую latency? сервис in-memory, ответы ~1-10 мс
)

REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total requests",
    ['method','status','datacenter','pod_id','route'],
)

EXCLUDED_PATHS = {"/health", "/metrics","/openapi.json","/docs"}


async def metrics_middleware(request: Request, call_next):
    # TODO: если путь служебный — просто пропустить дальше без метрик
    if request.url.path in EXCLUDED_PATHS:
        return await call_next(request)
    start = time.perf_counter()
    try:
        response = await call_next(request)
        status = str(response.status_code)
    except Exception:
        status = "500"  # TODO
        raise
    finally:
        elapsed = time.perf_counter() - start
        route_obj = request.scope.get("route")
        route = route_obj.path if route_obj is not None else "unmatched"  # TODO: шаблон маршрута (см. таблицу выше), с fallback на None
        REQUEST_LATENCY.labels(method=request.method,datacenter=DATACENTER,pod_id=POD_ID, route=route).observe(elapsed)
        REQUESTS_TOTAL.labels(method=request.method,status=status,datacenter=DATACENTER,pod_id=POD_ID,route=route).inc()
    return response


def metrics_endpoint() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def setup_metrics(app: FastAPI) -> None:
    """Подключает мониторинг к приложению."""
    app.middleware("http")(metrics_middleware)       # то же самое, что декоратор @app.middleware("http")
    app.add_api_route("/metrics", metrics_endpoint, methods=["GET"])