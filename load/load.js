import http from 'k6/http';

const TARGETS = (__ENV.TARGETS || 'http://app1:8000,http://app2:8000').split(',');
const TARGET_RPS = parseInt(__ENV.TARGET_RPS || '30', 10);
const RAMP_DURATION = __ENV.RAMP_DURATION || '3m';
const HOLD_DURATION = __ENV.HOLD_DURATION || '720h';
const NOT_FOUND_RATIO = parseFloat(__ENV.NOT_FOUND_RATIO || '0.05');


const CREATE_RATIO = 0.30;
const GET_RATIO = 0.45;

const MAX_KNOWN_IDS = 1000;

export const options = {
  scenarios: {
    background: {
      executor: 'ramping-arrival-rate',
      startRate: 1,
      timeUnit: '1s',
      preAllocatedVUs: 10,
      maxVUs: 50,
      stages: [
        { target: TARGET_RPS, duration: RAMP_DURATION },
        { target: TARGET_RPS, duration: HOLD_DURATION },
      ],
    },
  },
};

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
    getItem(base, 1000000000 + Math.floor(Math.random() * 1000000));
  } else if (ids.length === 0 || r < NOT_FOUND_RATIO + CREATE_RATIO) {
    createItem(base);
  } else if (r < NOT_FOUND_RATIO + CREATE_RATIO + GET_RATIO) {
    getItem(base, pick(ids));
  } else {
    updateItem(base, pick(ids));
  }
}
