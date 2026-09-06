/**
 * A popover scroll lock is only safe while its popover is OPEN.
 *
 * `react-remove-scroll` locks `document.body` for as long as it is MOUNTED, not for as
 * long as anything is visibly open - mounting it unconditionally left
 * `data-scroll-locked` set on the whole app with nothing open (`/user-management/settings/
 * system-health`, traced to `a8b811508` (#563, 3 Sep): `SearchableMultiSelect` computed its
 * `PopoverScrollLock` `active` prop as a bare `true` for every `renderTrigger` caller,
 * regardless of the popover's own open state).
 *
 * `PopoverScrollLock` itself now refuses to lock unless BOTH its `open` and `active` props
 * say so, but that only helps if a caller actually wires `open` to real state instead of a
 * literal `true` - the same mistake, one prop over. This is a source scan, not a render
 * test, for the same reason `tabs.overflow.inventory.test.ts` is one: the property being
 * asserted ("no call site hard-codes the lock on") is a fact about the WHOLE tree, and a
 * render test can only speak for the one component it mounted.
 *
 * Current call sites of `PopoverScrollLock`: `SearchableMultiSelect.tsx`,
 * `SearchableSelect.tsx`. `RemoveScroll` itself is used directly nowhere outside
 * `PopoverScrollLock.tsx` - a new one-off wrap that bypasses the primitive is exactly the
 * kind of change this guards against, so it is asserted here too.
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect } from 'vitest';

const ROOTS = ['app', 'components'];
/** The primitive itself is the only legitimate direct user of `RemoveScroll`. */
const PRIMITIVE_FILE = 'components/common/PopoverScrollLock.tsx';

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
  for (const root of ROOTS) walk(root);
  return out;
}

/**
 * The open tags of one JSX element, as source text. A regex to the next `>` is wrong
 * here: `className={cn('a', x && 'b')}` closes no tag. Brace depth is tracked and quotes
 * are skipped, and the tag ends at the first `>` at depth zero. Copied rather than
 * imported from `tabs.overflow.inventory.test.ts` - a source-scan test importing
 * production code to scan production code is its own kind of fragile.
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

/** The raw source of one attribute's value, e.g. `active={needsDialogScrollLock}` -> `{needsDialogScrollLock}`. */
function attrValue(tag: string, attr: string): string | null {
  const m = new RegExp(`\\b${attr}(=(\\{[^}]*\\}|"[^"]*"|'[^']*'))?`).exec(tag);
  if (!m) return null;
  return m[2] ?? '';
}

/** A literal boolean `true` - either `attr` (JSX shorthand) or `attr={true}`. */
function isLiteralTrue(value: string | null): boolean {
  if (value === null) return false;
  return value === '' || value.trim() === '{true}';
}

describe('Popover scroll lock inventory (locked only while open)', () => {
  it('every PopoverScrollLock call site binds open and active to real state', () => {
    const offenders: string[] = [];
    for (const file of sourceFiles()) {
      const src = fs.readFileSync(file, 'utf8');
      if (!src.includes('<PopoverScrollLock')) continue;
      for (const tag of openTags(src, 'PopoverScrollLock')) {
        const openVal = attrValue(tag, 'open');
        const activeVal = attrValue(tag, 'active');
        if (openVal === null || isLiteralTrue(openVal)) offenders.push(`${file}: ${tag}`);
        if (activeVal === null || isLiteralTrue(activeVal)) offenders.push(`${file}: ${tag}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it('nothing outside the primitive reaches for RemoveScroll directly', () => {
    const offenders: string[] = [];
    for (const file of sourceFiles()) {
      if (file === PRIMITIVE_FILE) continue;
      const src = fs.readFileSync(file, 'utf8');
      if (src.includes('<RemoveScroll')) offenders.push(file);
    }
    expect(offenders).toEqual([]);
  });
});
