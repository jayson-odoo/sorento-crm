/**
 * M3-04 (`ui-motion-round2`) - the reduced-motion block reaches the shell,
 * the mobile drawer and any one-off bracket-syntax transition, not only
 * Radix `-content` surfaces.
 *
 * A source-text scan, not a render - see `css/design-tokens.test.ts`'s own
 * header comment for why: jsdom does not run a stylesheet a test never
 * linked, so a `getComputedStyle` assertion would pass against an empty
 * string. These tests read the stylesheet the browser will resolve instead.
 */
import { describe, expect, it } from 'vitest';
import fs from 'fs';
import path from 'path';

const root = path.resolve(__dirname, '..');
const read = (rel: string) => fs.readFileSync(path.join(root, rel), 'utf8');

const stylesCss = read('css/styles.css');

/** Body of the first `{...}` that follows `selector`, brace-balanced so nested at-rules survive. */
function block(css: string, selector: string): string {
  const at = css.indexOf(selector);
  if (at === -1) throw new Error(`selector not found: ${selector}`);
  const open = css.indexOf('{', at);
  if (open === -1) throw new Error(`no block for: ${selector}`);
  let depth = 0;
  for (let i = open; i < css.length; i += 1) {
    if (css[i] === '{') depth += 1;
    else if (css[i] === '}') {
      depth -= 1;
      if (depth === 0) return css.slice(open + 1, i);
    }
  }
  throw new Error(`unbalanced block for: ${selector}`);
}

describe('M3-04 reduced-motion reaches the shell, the drawer and bracket transitions', () => {
  const reducedMotion = block(stylesCss, '@media (prefers-reduced-motion: reduce)');

  it('turns off the demo1 shell transitions (sidebar collapse, header, wrapper)', () => {
    expect(reducedMotion).toMatch(
      /\.demo1 \.sidebar,\s*\.demo1 \.wrapper,\s*\.demo1 \.header\s*\{\s*transition:\s*none\s*!important;/,
    );
  });

  it('collapses the mobile nav drawer (vaul) to no travel', () => {
    expect(reducedMotion).toMatch(/\[data-vaul-drawer\]\s*\{\s*transition-duration:\s*1ms\s*!important;/);
  });

  it('collapses any bracket-syntax transition-[...] utility to no travel', () => {
    expect(reducedMotion).toMatch(
      /\[class\*='transition-\['\]\s*\{\s*transition-duration:\s*1ms\s*!important;/,
    );
  });
});
