// AC-X7: `periodEnd` must answer the bucket's own last day regardless of the machine's
// local timezone. `TZ` is set BEFORE any import - `new Date(\`${period}T00:00:00\`)`
// parses as LOCAL time, and under UTC+8 (Asia/Kuala_Lumpur) that pushes the later
// `.toISOString()` conversion back across midnight, answering the day BEFORE the real
// end of every bucket. A machine already running in UTC would never catch this, which
// is why the coordinator's own diagnosis names the timezone explicitly.
process.env.TZ = 'Asia/Kuala_Lumpur';

import { describe, expect, it } from 'vitest';
import { periodEnd } from './orderInquiryMatrixService';

describe('periodEnd (AC-X7), under TZ=Asia/Kuala_Lumpur', () => {
  it('a week starting 2026-04-13 ends 2026-04-19, not 2026-04-18', () => {
    expect(periodEnd('2026-04-13', 'week')).toBe('2026-04-19');
  });

  it('the month 2026-04 ends 2026-04-30, not 2026-04-29', () => {
    expect(periodEnd('2026-04-01', 'month')).toBe('2026-04-30');
  });

  it('the year 2026 ends 2026-12-31, not 2026-12-30', () => {
    expect(periodEnd('2026-01-01', 'year')).toBe('2026-12-31');
  });

  it('a day bucket ends on itself', () => {
    expect(periodEnd('2026-04-13', 'day')).toBe('2026-04-13');
  });
});
