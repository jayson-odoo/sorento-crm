/**
 * M1-08 - the press-class inventory: every raw `<button` under `app/(protected)`
 * either renders the shared `Button` primitive (which already carries
 * `PRESSED_CLASS` unconditionally, see `button.tsx`) or names `PRESSED_CLASS`
 * itself. The 2 Sep audit found 127 files that do neither.
 *
 * THIS TEST IS ALLOWED TO STAY RED AT THE END OF M1 - the UAC says so
 * explicitly (M1-08). M7-01 is the slice that turns it green, file by file.
 * Left red-but-real would fail every `npm run test` between now and M7, so it
 * is gated behind `M1_PRESS_INVENTORY=1` instead of skipped outright: default
 * `npm run test` reports it skipped (green build, honest about not having run
 * it), and `M1_PRESS_INVENTORY=1 npx vitest run components/ui/pressed-class.inventory.test.tsx`
 * actually runs it and prints every miss.
 *
 * Same caveat as `components/ui/mobile-one-offs.inventory.test.ts`: this reads
 * source text, not a rendered DOM, so a `<button` whose opening tag runs past
 * the 20-line window below without closing would read as covered/uncovered
 * incorrectly. None of the misses in the 2 Sep audit were that shape.
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect } from 'vitest';

function read(file: string): string {
  return fs.readFileSync(file, 'utf8');
}

/** Every `.tsx` under `app/(protected)`, tests excluded. */
function sourceFiles(): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === 'node_modules' || entry.name === '.next') continue;
        walk(full);
      } else if (entry.name.endsWith('.tsx') && !entry.name.includes('.test.')) {
        out.push(full);
      }
    }
  };
  walk('app/(protected)');
  return out;
}

/**
 * The `sm` dense-cluster carve-out documented at `button.tsx:41-45` - a file
 * whose raw `<button>` sits in a strip packed tight enough that even the
 * shared `Button` declines the coarse hit target there. The 2 Sep audit named
 * none; kept as the mechanism the UAC asks for, so a real one has somewhere to
 * go with its reason on record rather than a silent skip.
 */
const ALLOWLIST: Record<string, string> = {};

function opensOnLine(line: string): boolean {
  return /<button(\s|>|$)/.test(line);
}

/** Does the `<button` opening at `lines[start]` carry PRESSED_CLASS before its tag closes? */
function tagCarriesPressedClass(lines: string[], start: number): boolean {
  let window = '';
  for (let i = start; i < Math.min(lines.length, start + 20); i += 1) {
    window += `${lines[i]}\n`;
    // The opening tag's own `>` - not a `=>` arrow function passed as a prop -
    // ends the search window; scanning past it risks picking up the NEXT
    // element's class instead of this one's.
    if (/>\s*$/.test(lines[i]) && !/=>\s*$/.test(lines[i])) break;
  }
  return /PRESSED_CLASS/.test(window);
}

describe.skipIf(process.env.M1_PRESS_INVENTORY !== '1')(
  'M1-08 press-class inventory (audit baseline: 127 files)',
  () => {
    it('every raw <button under app/(protected) imports Button or carries PRESSED_CLASS', () => {
      const offenders: string[] = [];
      for (const file of sourceFiles()) {
        const rel = path.relative(process.cwd(), file).split(path.sep).join('/');
        if (ALLOWLIST[rel]) continue;

        const src = read(file);
        if (!/<button(\s|>|$)/.test(src)) continue;

        const importsButton = /import\s*\{[^}]*\bButton\b[^}]*\}\s*from\s*['"][^'"]*components\/ui\/button['"]/s.test(
          src,
        );
        if (importsButton) continue;

        const lines = src.split('\n');
        const everyTagCovered = lines.every((line, i) => !opensOnLine(line) || tagCarriesPressedClass(lines, i));
        if (!everyTagCovered) offenders.push(rel);
      }

      if (process.env.M1_PRESS_INVENTORY === '1') {
        // eslint-disable-next-line no-console
        console.log(`M1-08 press-class inventory misses: ${offenders.length}`);
        // eslint-disable-next-line no-console
        console.log(offenders.join('\n'));
      }

      expect(offenders).toEqual([]);
    });
  },
);
