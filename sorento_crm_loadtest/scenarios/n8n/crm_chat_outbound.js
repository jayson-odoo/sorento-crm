import http from 'k6/http';
import { sleep } from 'k6';
import { resolveOptions } from '../../profiles/index.js';
import { n8n as n8nThresholds } from '../../lib/thresholds.js';
import { requireN8nUrl } from '../../lib/env.js';
import { isOk } from '../../lib/checks.js';

const baseBody = JSON.parse(open('../../fixtures/crm_chat_outbound.json'));

export const options = resolveOptions({
  exec: 'outbound',
  thresholds: n8nThresholds,
  scenarioOverrides: { peakRps: 30, preAllocatedVUs: 30, maxVUs: 200 },
});

let logged = false;

export function outbound() {
  const url = requireN8nUrl('crmChatOutboundUrl');
  if (!logged && __ITER === 0) {
    logged = true;
    console.log(`[crm_chat_outbound] POST ${url}`);
  }
  const body = JSON.parse(JSON.stringify(baseBody));
  const now = Date.now();
  body[0].message.messageId = now * 1000 + __ITER;
  body[0].message.timestamp = now;
  body[0].message.status[0].timestamp = now;
  body[0].message.message.text = `LOADTEST outbound VU=${__VU} ITER=${__ITER}`;

  const res = http.post(url, JSON.stringify(body), {
    headers: {
      'Content-Type': 'application/json',
      'User-Agent': 'Sorento-CRM/1.0.0',
    },
    tags: { name: 'n8n_crm_chat_outbound' },
  });
  isOk(res, 'n8n outbound');
  if (__ITER === 0) {
    console.log(`[crm_chat_outbound] status=${res.status} body=${(res.body || '').toString().slice(0, 200)}`);
  }
  sleep(1);
}

export default outbound;
