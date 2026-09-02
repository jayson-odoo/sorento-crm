/**
 * M6-06 - the four portal search boxes share the standard debounce.
 *
 * `PortalLanding.tsx`, `AsyncCombobox.tsx`, `MultiPillInput.tsx` and
 * `AsyncMultiCombobox.tsx` each hand-rolled their own `setTimeout` debounce
 * (300ms, 300ms, 250ms and 300ms) instead of `useDebouncedSearch`, so the
 * wait, the trim behaviour and the "still typing" signal were all
 * reinvented per box and none of them told the reader a request was coming.
 *
 * The trigger below is a `setTimeout(` whose delay literal is 250 or 300 -
 * the exact figures the four boxes used - scanned across every non-test file
 * in `app/(auth)/portal`. It does not fire on the OTHER `setTimeout` calls in
 * this tree (a blur-defer, a cooldown tick, a copy-feedback reset, an
 * object-URL revoke) because none of them share that delay.
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect } from 'vitest';

const DEBOUNCE_DELAY_PATTERN = /setTimeout\([\s\S]*?,\s*(?:250|300)\s*\)/;

function sourceFiles(): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(full);
      } else if (/\.(ts|tsx)$/.test(entry.name) && !entry.name.includes('.test.')) {
        out.push(full);
      }
    }
  };
  walk(path.join(__dirname));
  return out;
}

describe('portal search debounce (M6-06)', () => {
  it('no hand-rolled 250ms/300ms setTimeout debounce remains under app/(auth)/portal', () => {
    const offenders = sourceFiles().filter((file) =>
      DEBOUNCE_DELAY_PATTERN.test(fs.readFileSync(file, 'utf8')),
    );
    expect(offenders).toEqual([]);
  });
});
