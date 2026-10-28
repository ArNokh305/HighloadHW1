"""Спецификация build_dashboard: требования задания, записанные как тесты.

Пока build_dashboard -- заглушка, большинство тестов красные. Это нормально:
они показывают, что осталось сделать. Тесты не привязаны к конкретной
раскладке или именам вспомогательных функций -- проверяется только результат.

Запуск (из папки generator/):
    pip install -r requirements-dev.txt
    pytest -v
"""

import re

import pytest
from generate import build_dashboard

HANDLERS = [
    {"method": "POST", "route": "/items"},
    {"method": "GET", "route": "/items/{item_id}"},
    {"method": "PUT", "route": "/items/{item_id}"},
]


# ---------- вспомогательные функции для тестов ----------

def all_panels(dashboard):
    """Все панели, включая вложенные в свернутые row (у них свои panels)."""
    for p in dashboard.get("panels", []):
        yield p
        yield from p.get("panels", [])


def data_panels(dashboard):
    """Панели с данными (без строк-заголовков)."""
    return [p for p in all_panels(dashboard) if p.get("type") != "row"]


def exprs(panel):
    return [t["expr"] for t in panel.get("targets", [])]


def panels_for(dashboard, handler):
    """Панели, все запросы которых относятся к данной ручке."""
    m = f'method="{handler["method"]}"'
    r = f'route="{handler["route"]}"'
    return [
        p for p in data_panels(dashboard)
        if exprs(p) and all(m in e and r in e for e in exprs(p))
    ]


def variable(dashboard, name):
    for v in dashboard.get("templating", {}).get("list", []):
        if v.get("name") == name:
            return v
    pytest.fail(f"нет переменной ${name} в templating.list")


@pytest.fixture
def dashboard():
    return build_dashboard(HANDLERS)


# ---------- общие свойства дашборда ----------

def test_not_editable(dashboard):
    assert dashboard["editable"] is False


def test_fixed_uid(dashboard):
    # Фиксированный uid + overwrite=True -> повторный запуск перезаписывает дашборд.
    assert dashboard["uid"]
    assert build_dashboard(HANDLERS)["uid"] == dashboard["uid"]


# ---------- селекторы ----------

@pytest.mark.parametrize("name", ["datacenter", "pod"])
def test_variable_multi_and_all(dashboard, name):
    v = variable(dashboard, name)
    assert v.get("type") == "query"
    assert v.get("multi") is True, "нужен множественный выбор"
    assert v.get("includeAll") is True, "нужен вариант All"
    assert v.get("datasource", {}).get("uid") == "prometheus"
    query = v.get("query")
    query = query.get("query", "") if isinstance(query, dict) else (query or "")
    assert "label_values" in query


def test_pod_variable_is_chained_to_datacenter(dashboard):
    """Рекомендация, а не требование: при выборе dc1 в списке подов только поды dc1."""
    query = variable(dashboard, "pod").get("query")
    query = query.get("query", "") if isinstance(query, dict) else (query or "")
    assert "$datacenter" in query


# ---------- панели по ручкам ----------

@pytest.mark.parametrize("handler", HANDLERS,
                         ids=lambda h: f'{h["method"]} {h["route"]}')
def test_each_handler_has_latency_rps_errors(dashboard, handler):
    panels = panels_for(dashboard, handler)
    assert len(
        panels) >= 3, f"для {handler} нужно 3 панели, найдено {len(panels)}"

    latency = [p for p in panels if
               any("histogram_quantile" in e for e in exprs(p))]
    errors = [p for p in panels if any("status" in e for e in exprs(p))]
    rps = [p for p in panels if p not in latency and p not in errors]
    assert latency, "нет панели latency (histogram_quantile)"
    assert errors, "нет панели ошибок (с фильтром/группировкой по status)"
    assert rps, "нет панели RPS"

    latency_exprs = " ".join(e for p in latency for e in exprs(p))
    for q in ("0.5", "0.95", "0.99"):
        assert f"histogram_quantile({q}" in latency_exprs.replace(" ",
                                                                  ""), f"нет перцентиля {q}"


def test_new_handler_appears_without_code_changes():
    """Главное требование: новая ручка -> новые панели, без изменений генератора."""
    extra = {"method": "DELETE", "route": "/items/{item_id}"}
    dashboard = build_dashboard(HANDLERS + [extra])
    assert len(panels_for(dashboard, extra)) >= 3


def test_errors_panel_groups_by_status(dashboard):
    for handler in HANDLERS:
        error_exprs = [e for p in panels_for(dashboard, handler) for e in
                       exprs(p) if "status" in e]
        assert any(re.search(r"by\s*\(\s*status\s*\)", e) for e in error_exprs), \
            f"ошибки {handler} должны быть разбиты по коду: sum by (status)"
        assert any(re.search(
            r'status\s*=~\s*"[^"]*4[^"]*5|status\s*=~\s*"[^"]*5[^"]*4', e) for e
                   in error_exprs), \
            f"ошибки {handler} должны фильтроваться по 4xx и 5xx"


# ---------- корректность PromQL ----------

def test_every_expr_filters_by_selected_datacenter_and_pod(dashboard):
    for p in data_panels(dashboard):
        for e in exprs(p):
            assert re.search(r'=~\s*"\$datacenter"',
                             e), f'нет datacenter=~"$datacenter": {e}'
            assert re.search(r'=~\s*"\$pod"',
                             e), f'нет фильтра по $pod через =~: {e}'


def test_rates_are_summed(dashboard):
    for p in data_panels(dashboard):
        for e in exprs(p):
            if "rate(" in e:
                assert "sum" in e, f"rate без sum не агрегирует поды: {e}"


def test_quantiles_over_aggregated_buckets(dashboard):
    for p in data_panels(dashboard):
        for e in exprs(p):
            if "histogram_quantile" in e:
                assert "_bucket" in e, f"перцентили считаются по бакетам: {e}"
                assert re.search(
                    r"sum[^)]*by\s*\(\s*le\s*\)|sum\s*by\s*\(\s*le\s*\)|by\s*\(\s*le\s*\)",
                    e), \
                    f"нужен histogram_quantile(q, sum by (le) (rate(..._bucket...))): {e}"


# ---------- оформление ----------

def test_panels_use_provisioned_datasource(dashboard):
    for p in data_panels(dashboard):
        assert p.get("datasource", {}).get(
            "uid") == "prometheus", f"панель {p.get('title')}"


def test_panels_have_titles_and_refids(dashboard):
    for p in data_panels(dashboard):
        assert p.get("title")
        ref_ids = [t.get("refId") for t in p.get("targets", [])]
        assert all(ref_ids) and len(ref_ids) == len(set(ref_ids)), \
            f"у запросов панели {p.get('title')} должны быть уникальные refId"


def test_panels_do_not_overlap(dashboard):
    rects = []
    for p in all_panels(dashboard):
        g = p.get("gridPos")
        assert g, f"нет gridPos у панели {p.get('title')}"
        assert 0 <= g["x"] and g["x"] + g[
            "w"] <= 24, f"панель {p.get('title')} вылезает за 24 колонки"
        rects.append(
            (g["x"], g["y"], g["x"] + g["w"], g["y"] + g["h"], p.get("title")))
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            overlap = a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[
                3]
            assert not overlap, f"панели '{a[4]}' и '{b[4]}' перекрываются"
