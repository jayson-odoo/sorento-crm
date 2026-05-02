import http from 'k6/http';
import { sleep } from 'k6';
import { resolveOptions } from '../../profiles/index.js';
import { heavyWrite } from '../../lib/thresholds.js';
import { requireBeUrl } from '../../lib/env.js';
import { getToken } from '../../lib/auth.js';
import { isOk } from '../../lib/checks.js';

const SIZE = (__ENV.ATTACHMENT_SIZE || 'small').toLowerCase();
const FILE_BIN = tryOpen(SIZE);

function tryOpen(size) {
  const map = {
    small: '../../fixtures/attachments/small.pdf',
    medium: '../../fixtures/attachments/medium.pdf',
    large: '../../fixtures/attachments/large.pdf',
  };
  const path = map[size] || map.small;
  try {
    return open(path, 'b');
  } catch (_) {
    return null;
  }
}

export const options = resolveOptions({
  exec: 'uploadAttachment',
  thresholds: heavyWrite,
  scenarioOverrides: { peakRps: 5, preAllocatedVUs: 10, maxVUs: 50 },
});

export function uploadAttachment() {
  if (!FILE_BIN) {
    throw new Error(`missing fixture file for size=${SIZE}. See fixtures/attachments/README.md`);
  }
  const be = requireBeUrl();
  const token = getToken();
  const filename = `loadtest-${__VU}-${__ITER}.pdf`;

  const res = http.post(
    `${be}/api/v1/resources/attachments/`,
    {
      file: http.file(FILE_BIN, filename, 'application/pdf'),
      attachment_type: 'general',
      access_levels: 'internal',
    },
    {
      headers: { Authorization: `Bearer ${token}` },
      tags: { name: 'attachment_upload', size: SIZE },
    },
  );
  isOk(res, 'attachment_upload');
  sleep(1);
}

export default uploadAttachment;
