/**
 * `PLAN-oi-request-cs-reserve.md` section 6c F2, `oi-request-cs-reserve-acceptance-
 * criteria.md` AC-RS-61: "`ReserveRequestsCard` and 'Earlier reserve requests' no longer
 * render." Enforced here by GREP rather than by a render assertion, the same style
 * `app/(protected)/scm/lib/format.guard.test.ts` already uses for a source-wide rule -
 * a render-level check only proves ONE screen stopped importing it; this proves NOTHING
 * under `order-inquiries/` still does, including a future re-import nobody thought to
 * check by hand.
 *
 * Red today for the honest reason: `ReserveRequestsSection.tsx` still imports
 * `ReserveRequestsCard` (round 1's own component), and the component file itself still
 * exists. Both go once the coder builds F2 - this test then simply confirms it stays
 * gone.
 */
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

const COMPONENTS_ROOT = join(import.meta.dirname);

function tsxFilesIn(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true })
    .filter((entry) => entry.isFile() && /\.(tsx|ts)$/.test(entry.name))
    .filter((entry) => entry.name !== 'ReserveRequestsCard.retired.test.tsx')
    .map((entry) => join(dir, entry.name));
}

describe('AC-RS-61: ReserveRequestsCard is retired under order-inquiries/[id]/components', () => {
  it('no file imports ReserveRequestsCard', () => {
    const offenders: string[] = [];
    for (const file of tsxFilesIn(COMPONENTS_ROOT)) {
      const content = readFileSync(file, 'utf8');
      if (/from ['"]\.\/ReserveRequestsCard['"]/.test(content)) {
        offenders.push(file);
      }
    }
    expect(offenders).toEqual([]);
  });

  it('the ReserveRequestsCard.tsx source file itself is deleted', () => {
    const files = readdirSync(COMPONENTS_ROOT);
    expect(files).not.toContain('ReserveRequestsCard.tsx');
  });

  it('the ReserveRequestsSection.tsx source file itself is deleted (F2: reserve lives on the line, not a section above the grid)', () => {
    const files = readdirSync(COMPONENTS_ROOT);
    expect(files).not.toContain('ReserveRequestsSection.tsx');
  });
});
