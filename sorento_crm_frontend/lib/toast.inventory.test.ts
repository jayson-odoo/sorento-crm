/**
 * M6-04 - the one toast standard.
 *
 * `lib/toast.ts` wraps sonner so a success clears itself (4000ms) and an error
 * waits for the reader to dismiss it (`duration: Infinity` + a close button).
 * The wrapper only holds that promise while it is the ONLY door to sonner: a
 * file that imports `toast` straight from `'sonner'` gets neither default, and
 * the mistake is invisible until someone notices a toast vanished mid-read.
 *
 * `components/ui/sonner.tsx` is the one legitimate direct importer - it is
 * what MOUNTS sonner's `<Toaster>` - and `lib/toast.ts` itself is the wrapper.
 * Everything else, including every test file, goes through the wrapper so a
 * mocked `sonner` module cannot silently diverge from what the app actually
 * calls.
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect } from 'vitest';

const ALLOWED_DIRECT_IMPORTERS = new Set([
  'lib/toast.ts',
  'components/ui/sonner.tsx',
  // The wrapper's own test: it asserts against the underlying sonner mock, so
  // it has to import the real thing.
  'lib/toast.test.ts',
]);

/** Every `.ts`/`.tsx` under the app, tests included - a mock is a call site too. */
function sourceFiles(): string[] {
  const out: string[] = [];
  const roots = ['app', 'components', 'hooks', 'lib', 'providers', 'services'];
  const walk = (dir: string) => {
    if (!fs.existsSync(dir)) return;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === 'node_modules' || entry.name === '.next') continue;
        walk(full);
      } else if (/\.(ts|tsx)$/.test(entry.name)) {
        out.push(full);
      }
    }
  };
  for (const root of roots) walk(root);
  return out;
}

function importsSonnerDirectly(file: string): boolean {
  const src = fs.readFileSync(file, 'utf8');
  return /from ['"]sonner['"]/.test(src);
}

describe('toast standard (M6-04)', () => {
  it('no file outside lib/toast.ts and components/ui/sonner.tsx imports from sonner directly', () => {
    const offenders = sourceFiles().filter(
      (file) => !ALLOWED_DIRECT_IMPORTERS.has(file) && importsSonnerDirectly(file),
    );
    expect(offenders).toEqual([]);
  });
});
