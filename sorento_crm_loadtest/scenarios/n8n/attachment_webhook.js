import http from 'k6/http';
import { sleep } from 'k6';
import { resolveOptions } from '../../profiles/index.js';
import { n8n as n8nThresholds } from '../../lib/thresholds.js';
import { requireN8nUrl } from '../../lib/env.js';
import { isOk } from '../../lib/checks.js';

const baseBody = JSON.parse(open('../../fixtures/attachment_webhook.json'));

export const options = resolveOptions({
  exec: 'attachment',
  thresholds: n8nThresholds,
  scenarioOverrides: { peakRps: 30, preAllocatedVUs: 30, maxVUs: 200 },
});

function uuid() {
  // RFC4122-ish v4 — only used to make payload IDs distinct per iteration
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

let logged = false;

export function attachment() {
  const url = requireN8nUrl('attachmentUrl');
  if (!logged && __ITER === 0) {
    logged = true;
    console.log(`[attachment_webhook] POST ${url}`);
  }
  const body = { ...baseBody };
  body.integration_log_id = uuid();
  body.attachment_id = uuid();
  body.attachment_filename = `loadtest-${__VU}-${__ITER}.pdf`;
  body.file_path = `loadtest/${body.attachment_filename}`;
  body.s3_url = `s3://sorento-loadtest/${body.attachment_filename}`;
  body.attachment_url = `https://cdn.example.invalid/${body.attachment_filename}`;

  const res = http.post(url, JSON.stringify(body), {
    headers: {
      'Content-Type': 'application/json',
      'User-Agent': 'Sorento-CRM/1.0.0',
    },
    tags: { name: 'n8n_attachment' },
  });
  isOk(res, 'n8n attachment');
  if (__ITER === 0) {
    console.log(`[attachment_webhook] status=${res.status} body=${(res.body || '').toString().slice(0, 200)}`);
  }
  sleep(1);
}

export default attachment;
