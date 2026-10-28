// Фоновая нагрузка на items-service для k6.
//
// Модель нагрузки -- открытая (ramping-arrival-rate): k6 запускает заданное
// число итераций в секунду независимо от того, как быстро отвечает сервис.
// Одна итерация = один HTTP-запрос, поэтому "итераций в секунду" = RPS.
//
// Все параметры -- через переменные окружения (в k6 они доступны как __ENV).

import http from 'k6/http';

const TARGETS = (__ENV.TARGETS || 'http://app1:8000,http://app2:8000').split(',');
const TARGET_RPS = parseInt(__ENV.TARGET_RPS || '30', 10);   // суммарно на все экземпляры
const RAMP_DURATION = __ENV.RAMP_DURATION || '3m';            // время разгона от 1 до TARGET_RPS
const HOLD_DURATION = __ENV.HOLD_DURATION || '720h';          // "пока стек не остановят" (30 дней)
const NOT_FOUND_RATIO = parseFloat(__ENV.NOT_FOUND_RATIO || '0.05'); // доля GET по несуществующему id

// Доли остальных запросов (вместе с NOT_FOUND_RATIO дают 1.0).
const CREATE_RATIO = 0.30;
const GET_RATIO = 0.45;
// остаток (~0.20) -- PUT

const MAX_KNOWN_IDS = 1000; // сколько id помнить на экземпляр, чтобы память VU не росла бесконечно

export const options = {
  scenarios: {
    background: {
      executor: 'ramping-arrival-rate',
      startRate: 1,
      timeUnit: '1s',
      // VU (virtual user) -- "исполнитель", который выполняет итерации.
      // При ответах в единицы миллисекунд хватает нескольких; maxVUs -- запас,
      // если сервис вдруг начнет тормозить (k6 досоздаст VU, чтобы держать темп).
      preAllocatedVUs: 10,
      maxVUs: 50,
      stages: [
        { target: TARGET_RPS, duration: RAMP_DURATION }, // плавный разгон
        { target: TARGET_RPS, duration: HOLD_DURATION }, // держим
      ],
    },
  },
};

// Состояние на уровне модуля. В k6 у каждого VU своя копия JS-окружения,
// так что это -- память конкретного VU, без гонок между VU.
// Важно: id храним ОТДЕЛЬНО для каждого экземпляра -- у app1 и app2 разные
// in-memory хранилища, и id, созданный на app1, на app2 вернет 404.
const knownIds = {};
for (const t of TARGETS) knownIds[t] = [];

const JSON_HEADERS = { headers: { 'Content-Type': 'application/json' } };

function pick(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

function remember(base, id) {
  const ids = knownIds[base];
  ids.push(id);
  if (ids.length > MAX_KNOWN_IDS) ids.shift();
}

// Тег name группирует запросы в статистике k6 по шаблону, а не по
// фактическому URL -- та же идея, что и лейбл route в наших метриках.
function createItem(base) {
  const res = http.post(
    `${base}/items`,
    JSON.stringify({ name: `item-${Math.random().toString(36).slice(2, 8)}` }),
    { ...JSON_HEADERS, tags: { name: 'POST /items' } },
  );
  if (res.status === 201) remember(base, res.json('id'));
}

function getItem(base, id) {
  http.get(`${base}/items/${id}`, { tags: { name: 'GET /items/{id}' } });
}

function updateItem(base, id) {
  http.put(
    `${base}/items/${id}`,
    JSON.stringify({ name: 'updated', description: 'by k6' }),
    { ...JSON_HEADERS, tags: { name: 'PUT /items/{id}' } },
  );
}

export default function () {
  const base = pick(TARGETS);
  const ids = knownIds[base];
  const r = Math.random();

  if (r < NOT_FOUND_RATIO) {
    // Заведомо несуществующий id -> 404.
    getItem(base, 1000000000 + Math.floor(Math.random() * 1000000));
  } else if (ids.length === 0 || r < NOT_FOUND_RATIO + CREATE_RATIO) {
    // Пока этот VU ничего не создал на экземпляре -- сначала создаем.
    createItem(base);
  } else if (r < NOT_FOUND_RATIO + CREATE_RATIO + GET_RATIO) {
    getItem(base, pick(ids));
  } else {
    updateItem(base, pick(ids));
  }
}
