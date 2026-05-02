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

export function aiSpike() {
  const be = requireBeUrl();
  const headers = authHeaders();

  group('greeting', () => {
    const res = http.get(`${be}/api/v1/ai-assistant/greeting`, { headers, tags: { name: 'ai_greeting' } });
    isOk(res, 'ai_greeting');
  });

  group('chat', () => {
    const res = http.post(
      `${be}/api/v1/ai-assistant/chat`,
      JSON.stringify({ message: `LOADTEST chat VU=${__VU} ITER=${__ITER}. What can you do?` }),
      { headers, tags: { name: 'ai_chat' }, timeout: '60s' },
    );
    isOk(res, 'ai_chat');
  });

  group('usage', () => {
    const res = http.get(`${be}/api/v1/ai-assistant/usage/summary`, { headers, tags: { name: 'ai_usage' } });
    isOk(res, 'ai_usage');
  });

  sleep(1);
}

export default aiSpike;
