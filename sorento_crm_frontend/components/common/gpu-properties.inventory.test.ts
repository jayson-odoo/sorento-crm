/**
 * M3-01/M3-02/M3-03 (`ui-motion-round2`) - GPU properties guardrail.
 *
 * `transition-[width]`, `transition-[height]`, `transition-[margin*]`,
 * `transition-[padding*]` and `transition-[inset*]` all animate a property the
 * browser has to run layout for on every frame, not one it can hand to the
 * compositor - a `transform`/`scaleX` transition costs nothing comparable. This
 * walk is the floor that keeps the four M3 sites (the deferred-action countdown,
 * the takeover bar, the cash-budget fill, the activities-panel push) from
 * drifting back to a layout property, and stops a NEW site from picking one.
 *
 * NOTE for the merge with `feat/motion2-M1-perimeter-hygiene` (#551): that
 * branch widens `css/design-tokens.test.ts` with the identical
 * `LAYOUT_PROPERTY` regex and an allowlist carrying these same four sites
 * tagged `'M3'` (pending this slice's fix). Once this branch lands, that
 * allowlist's four `M3` entries are stale (the lines they name no longer match)
 * and should be deleted at merge time - this file's own job is done at that
 * point too, since M1's widened test covers the same ground with the same
 * regex. See the M3 PR description for the exact four lines to remove.
 *
 * Same reasoning as the other inventory tests in this repo (e.g.
 * `css/design-tokens.test.ts`): this is a source scan, not a render, because
 * the property being asserted ("nothing in the whole tree does X") is not one
 * a mounted component can speak for.
 */
import { describe, expect, it } from 'vitest';
import fs from 'fs';
import path from 'path';

const root = path.resolve(__dirname, '../..');
const read = (rel: string) => fs.readFileSync(path.join(root, rel), 'utf8');

/**
 * `app/components/layouts/demo2` through `demo10` are vendor Metronic shells
 * with zero live routes (see the identical exclusion in
 * `components/ui/a11y-guardrails.inventory.test.ts`); `demo1` (the layout
 * `app/(protected)/layout.tsx` actually mounts) is NOT excluded.
 */
const DEAD_LAYOUT_PREFIX = /^app\/components\/layouts\/demo(?:[2-9]|10)\//;

function sourceFiles(): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const entry of fs.readdirSync(path.join(root, dir), { withFileTypes: true })) {
      const rel = path.posix.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === 'node_modules' || entry.name === '.next') continue;
        walk(rel);
      } else if (/\.(tsx?|css)$/.test(entry.name) && !entry.name.includes('.test.')) {
        if (DEAD_LAYOUT_PREFIX.test(rel)) continue;
        out.push(rel);
      }
    }
  };
  walk('app');
  walk('components');
  return out;
}

/** A comment mentioning the class token must not read as the class itself. */
function stripBlockComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, ' '));
}

const files = sourceFiles();

/** Identical to the regex `feat/motion2-M1-perimeter-hygiene` lands with. */
const LAYOUT_PROPERTY =
  /transition-\[[^\]]*\b(width|height|margin(?:-[a-z]+)?|padding(?:-[a-z]+)?|inset(?:-[a-z]+)?)\b[^\]]*\]/;

/**
 * The three accordion/collapsible content sites never need an entry here:
 * their height comes from the `animate-accordion-*`/`animate-collapsible-*`
 * keyframes (a CSS animation, not a `transition-[...]` utility), so the regex
 * above does not match them today and is not expected to after M1 either -
 * named here only so the allowlist documents the sites it was drafted around,
 * per the plan: `components/ui/accordion.tsx:59`,
 * `components/ui/accordion-menu.tsx:354`, `components/ui/collapsible.tsx:24`.
 */
const PROPERTY_ALLOWLIST: Record<string, string> = {};

describe('M3 GPU properties: no transition-[width|height|margin|padding|inset]', () => {
  it('leaves zero transition-[width|height|margin|padding|inset] outside the allowlist', () => {
    const offenders: string[] = [];
    for (const file of files) {
      const src = stripBlockComments(read(file));
      src.split('\n').forEach((line, i) => {
        if (LAYOUT_PROPERTY.test(line)) {
          const key = `${file}:${i + 1}`;
          if (!PROPERTY_ALLOWLIST[key]) offenders.push(key);
        }
      });
    }
    expect(offenders).toEqual([]);
  });
});
