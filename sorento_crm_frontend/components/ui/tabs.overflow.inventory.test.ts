/**
 * The primitive owns the scroller, not the screen.
 *
 * `tabs.tsx`'s `TabsList` has scrolled sideways with no visible scrollbar
 * since S1 (`tabs.inventory.test.ts`), and as of the 5 Sep fix it also
 * scrolls by wheel, shows edge chevrons and keeps the active tab in view -
 * all in one place. Thirteen screens had already compensated for the earlier,
 * incomplete primitive by bolting their own `overflow-x-auto` onto their
 * `TabsList`, which does nothing the primitive doesn't already do and would
 * silently shadow a future change to it. This is a source scan, not a render
 * test, for the same reason `tabs.inventory.test.ts` is one: what this
 * asserts is a property of the WHOLE tree ("no `TabsList` repeats the
 * primitive's own overflow class"), and a render test can only speak for the
 * component it mounted. A fourteenth per-screen `overflow-x-auto` added next
 * month would pass every component test in the repo and fail here.
 *
 * If a `TabsList` genuinely does not scroll, that is a primitive-level bug,
 * not a reason to re-add the class per screen.
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect } from 'vitest';

/** `components/ui` is excluded: the primitive itself owns the overflow class. */
const ROOTS = ['app', 'components'];
const EXCLUDED_PREFIXES = ['components/ui/'];

/** Every `.tsx` under the scanned roots, tests and the primitive excluded. */
function sourceFiles(): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === 'node_modules' || entry.name === '.next') continue;
        walk(full);
      } else if (entry.name.endsWith('.tsx') && !entry.name.includes('.test.')) {
        if (EXCLUDED_PREFIXES.some((prefix) => full.startsWith(prefix))) continue;
        out.push(full);
      }
    }
  };
  for (const root of ROOTS) walk(root);
  return out;
}

/**
 * The open tags of one JSX element, as source text.
 *
 * A regex to the next `>` is wrong here: `className={cn('a', x && 'b')}`
 * closes no tag. So brace depth is tracked and quotes are skipped, and the
 * tag ends at the first `>` at depth zero. Copied from `tabs.inventory.test.ts`
 * rather than imported - a source-scan test importing production code to scan
 * production code is its own kind of fragile.
 */
function openTags(src: string, name: string): string[] {
  const found: string[] = [];
  const opener = new RegExp(`<${name}(?![A-Za-z])`, 'g');
  let m: RegExpExecArray | null;
  while ((m = opener.exec(src))) {
    let i = m.index;
    let depth = 0;
    let quote: string | null = null;
    while (i < src.length) {
      const c = src[i];
      if (quote) {
        if (c === '\\') i += 1;
        else if (c === quote) quote = null;
      } else if (c === '"' || c === "'" || c === '`') {
        quote = c;
      } else if (c === '{') {
        depth += 1;
      } else if (c === '}') {
        depth -= 1;
      } else if (c === '>' && depth === 0) {
        found.push(src.slice(m.index, i + 1));
        break;
      }
      i += 1;
    }
  }
  return found;
}

describe('TabsList overflow inventory (the primitive owns it, not the screen)', () => {
  it('no TabsList outside the primitive repeats its own overflow-x class', () => {
    const offenders: string[] = [];
    for (const file of sourceFiles()) {
      const src = fs.readFileSync(file, 'utf8');
      if (!src.includes('<TabsList')) continue;
      for (const tag of openTags(src, 'TabsList')) {
        if (/\boverflow-x\b|\boverflow-auto\b/.test(tag)) offenders.push(file);
      }
    }
    expect(offenders).toEqual([]);
  });
});
