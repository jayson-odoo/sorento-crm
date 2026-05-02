import http from 'k6/http';
import { sleep } from 'k6';
import { SharedArray } from 'k6/data';
import { resolveOptions } from '../../profiles/index.js';
import { n8n as n8nThresholds } from '../../lib/thresholds.js';
import { requireN8nUrl } from '../../lib/env.js';
import { isOk } from '../../lib/checks.js';

const baseBody = JSON.parse(open('../../fixtures/stock_inquiry_revise.json'));
const messageTexts = new SharedArray('reviseTexts', () =>
  JSON.parse(open('../../fixtures/stock_inquiry_revise_texts.json')),
);

export const options = resolveOptions({
  exec: 'reviseInquiry',
  thresholds: n8nThresholds,
  scenarioOverrides: { peakRps: 30, preAllocatedVUs: 30, maxVUs: 200 },
});

let logged = false;

export function reviseInquiry() {
  const url = requireN8nUrl('stockInquiryReviseUrl');
  if (!logged && __ITER === 0) {
    logged = true;
    console.log(`[stock_inquiry_revise] POST ${url}`);
  }
  const body = JSON.parse(JSON.stringify(baseBody));
  const now = Date.now();
  body[0].message.messageId = now * 1000 + __ITER;
  body[0].message.timestamp = now;
  const idx = (__VU * 1000 + __ITER) % messageTexts.length;
  body[0].message.message.text = "What are the products you have?";

  const res = http.post(url, JSON.stringify(body), {
    headers: {
      'Content-Type': 'application/json',
      'User-Agent': 'Sorento-CRM/1.0.0',
    },
    tags: { name: 'n8n_stock_inquiry_revise' },
  });
  isOk(res, 'n8n revise');
  if (__ITER === 0) {
    console.log(`[stock_inquiry_revise] status=${res.status} body=${(res.body || '').toString().slice(0, 200)}`);
  }
  sleep(1);
}

export default reviseInquiry;
