import argparse
import json
import os
import sys
import time

import requests

DATASOURCE = {"type": "prometheus", "uid": "prometheus"}

DASHBOARD_UID = "items-service"
DASHBOARD_TITLE = "Items service"

RETRIES = 10
RETRY_DELAY_SECONDS = 2
HTTP_TIMEOUT_SECONDS = 5


def make_panel(title, targets, unit, x, y):
    return {
        "type": "timeseries",
        "title": title,
        "datasource": DATASOURCE,
        "gridPos": {"x": x, "y": y, "w": 8, "h": 8},
        "fieldConfig": {"defaults": {"unit": unit}},
        "targets": targets,
    }


def make_variable(name, query) -> dict:
    return {
        "name": name,
        "type": "query",
        "datasource": DATASOURCE,
        "query": query,
        "multi": True,
        "includeAll": True,
        "allValue": ".*",
        "refresh": 2
    }


def make_row(title: str, y: int) -> dict:
    return {
        "type": "row",
        "title": title,
        "collapsed": False,
        "gridPos": {"x": 0, "y": y, "w": 24, "h": 1},
        "panels": [],
    }


def handler_selector(handler) -> str:
    return f'method="{handler["method"]}", route="{handler["route"]}", datacenter=~"$datacenter", pod_id=~"$pod"'


def build_dashboard(handlers: list[dict]) -> dict:
    datacenter_label = make_variable("datacenter",
                                     "label_values(http_requests_total, datacenter)")
    pod_label = make_variable("pod",
                              'label_values(http_requests_total{datacenter=~"$datacenter"}, pod_id)')
    panels = []
    y = 0
    for h in handlers:
        sel = handler_selector(h)
        panels.append(make_row(f'{h["method"]} {h["route"]}', y))
        latency_targets = []
        for ref_id, q, legend in [("A", 0.5, "p50"), ("B", 0.95, "p95"),
                                  ("C", 0.99, "p99")]:
            latency_targets.append({
                "refId": ref_id,
                "expr": f"histogram_quantile({q}, sum by (le) (rate(http_request_duration_seconds_bucket{{{sel}}}[$__rate_interval])))",
                "legendFormat": legend,
            })
        err_expr = f'sum by (status) (rate(http_requests_total{{{sel}, status=~"4..|5.."}}[$__rate_interval]))'
        rps_expr = f"sum(rate(http_requests_total{{{sel}}}[$__rate_interval]))"
        panels.append(make_panel("Latency", latency_targets, "s", 0, y=y + 1))
        panels.append(make_panel("RPS", [{"refId": "A", "expr": rps_expr,
                                          "legendFormat": "reqps"}], "reqps",
                                 x=8, y=y + 1))
        panels.append(make_panel("Errors", [{"refId": "A", "expr": err_expr,
                                             "legendFormat": "{{status}}"}],
                                 "reqps", x=16, y=y + 1))
        y += 9

    return {
        "uid": DASHBOARD_UID,
        "title": DASHBOARD_TITLE,
        "editable": False,
        "refresh": "10s",
        "time": {"from": "now-15m", "to": "now"},
        "templating": {"list": [datacenter_label, pod_label]},
        "panels": panels,
    }


def log(msg: str) -> None:
    print(f"[generator] {msg}", file=sys.stderr, flush=True)


def with_retries(action, description: str):
    for attempt in range(1, RETRIES + 1):
        try:
            return action()
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code < 500:
                raise
            last_error = e
        except requests.RequestException as e:  # нет соединения, таймаут и т.п.
            last_error = e
        log(f"{description}: попытка {attempt}/{RETRIES} не удалась ({last_error})")
        if attempt < RETRIES:
            time.sleep(RETRY_DELAY_SECONDS)
    raise RuntimeError(
        f"{description}: не удалось за {RETRIES} попыток") from last_error


def fetch_handlers(app_url: str) -> list[dict]:
    def action():
        resp = requests.get(f"{app_url}/handlers", timeout=HTTP_TIMEOUT_SECONDS)
        resp.raise_for_status()
        return resp.json()

    handlers = with_retries(action, f"GET {app_url}/handlers")
    if not handlers:
        raise RuntimeError(
            "приложение вернуло пустой список ручек -- нечего рисовать")
    return handlers


def upload_dashboard(dashboard: dict, grafana_url: str, user: str,
                     password: str) -> str:
    payload = {
        "dashboard": {**dashboard, "id": None},
        "overwrite": True,
    }

    def action():
        resp = requests.post(
            f"{grafana_url}/api/dashboards/db",
            json=payload,
            auth=(user, password),
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        if resp.status_code >= 400:
            log(f"Grafana ответила {resp.status_code}: {resp.text}")
        resp.raise_for_status()
        return resp.json()

    result = with_retries(action, "загрузка дашборда в Grafana")
    return result.get("url", "")


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"не задана переменная окружения {name}")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Генерация дашборда Grafana по ручкам приложения")
    parser.add_argument("--app-url",
                        default=os.getenv("APP_URL", "http://localhost:8001"))
    parser.add_argument("--grafana-url", default=os.getenv("GRAFANA_URL",
                                                           "http://localhost:3000"))
    parser.add_argument("--dry-run", action="store_true",
                        help="только напечатать JSON дашборда, в Grafana не отправлять")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if not args.dry_run:
            user, password = require_env("GRAFANA_USER"), require_env(
                "GRAFANA_PASSWORD")

        handlers = fetch_handlers(args.app_url)
        log(f"получено ручек: {len(handlers)}: " + ", ".join(
            f"{h['method']} {h['route']}" for h in handlers))

        dashboard = build_dashboard(handlers)

        if args.dry_run:
            print(json.dumps(dashboard, indent=2, ensure_ascii=False))
            return 0

        url = upload_dashboard(dashboard, args.grafana_url, user, password)
        log(f"дашборд загружен: {args.grafana_url}{url}")
        return 0
    except Exception as e:
        log(f"ОШИБКА: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
