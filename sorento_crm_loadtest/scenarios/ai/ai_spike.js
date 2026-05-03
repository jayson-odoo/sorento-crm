import http from 'k6/http';
import { sleep, group } from 'k6';
import { ai as aiThresholds } from '../../lib/thresholds.js';
import { requireBeUrl } from '../../lib/env.js';
import { authHeaders } from '../../lib/auth.js';
import { isOk } from '../../lib/checks.js';

// Bounded spike — never bundle with other profiles. AI is expensive + tail-latency-y.
export const options = {
  scenarios: {
    ai_spike: {
      executor: 'constant-vus',
      vus: Number(__ENV.AI_VUS || 5),
      duration: __ENV.AI_DURATION || '2m',
      exec: 'aiSpike',
      tags: { profile: 'ai-spike' },
    },
  },
  thresholds: aiThresholds,
};

let logged = false;

export function aiSpike() {
  const be = requireBeUrl();
  const headers = authHeaders();

  if (!logged && __ITER === 0) {
    logged = true;
    console.log(`[ai_spike] BE=${be}`);
  }

  group('greeting', () => {
    const res = http.get(`${be}/api/v1/system/ai-assistant/greeting`, { headers, tags: { name: 'ai_greeting' } });
    if (__ITER === 0) console.log(`[ai_greeting] status=${res.status} body=${(res.body || '').toString().slice(0, 200)}`);
    isOk(res, 'ai_greeting');
  });

  group('chat', () => {
    const res = http.post(
      `${be}/api/v1/system/ai-assistant/chat`,
      JSON.stringify({ message: `LOADTEST chat VU=${__VU} ITER=${__ITER}. What can you do?` }),
      { headers, tags: { name: 'ai_chat' }, timeout: '60s' },
    );
    if (__ITER === 0) console.log(`[ai_chat] status=${res.status} body=${(res.body || '').toString().slice(0, 200)}`);
    isOk(res, 'ai_chat');
  });

  group('usage', () => {
    const res = http.get(`${be}/api/v1/system/ai-assistant/usage/summary`, { headers, tags: { name: 'ai_usage' } });
    if (__ITER === 0) console.log(`[ai_usage] status=${res.status} body=${(res.body || '').toString().slice(0, 200)}`);
    isOk(res, 'ai_usage');
  });

  sleep(1);
}

export default aiSpike;
