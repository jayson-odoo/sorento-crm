/**
 * M3-05 (`ui-motion-round2`) - the sidebar's hover-to-expand rule only fires
 * on a device that can genuinely hover a pointer, so a coarse-pointer tap on
 * the collapsed sidebar does not expand it.
 *
 * A source-text scan - see `css/reduced-motion-m3.test.ts`'s header comment
 * for why a render adds nothing here.
 */
import { describe, expect, it } from 'vitest';
import fs from 'fs';
import path from 'path';

const demo1Css = fs.readFileSync(
  path.resolve(__dirname, 'demos/demo1.css'),
  'utf8',
);

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

describe('M3-05 sidebar hover-expand is gated to a device with real hover', () => {
  it('wraps the hover-expand rule in @media (hover: hover) and (pointer: fine)', () => {
    const hoverGate = block(demo1Css, '@media (hover: hover) and (pointer: fine)');
    expect(hoverGate).toContain('.demo1.sidebar-collapse .sidebar:hover');
    expect(hoverGate).toMatch(/width:\s*var\(--sidebar-default-width\)/);
  });

  it('does not leave an ungated copy of the rule outside that media query', () => {
    // The old, ungated rule has to be GONE, not shadowed by a later one - a
    // coarse pointer must never match `:hover` at all for this to hold.
    const withoutHoverGate = demo1Css.replace(
      block(demo1Css, '@media (hover: hover) and (pointer: fine)'),
      '',
    );
    expect(withoutHoverGate).not.toMatch(/\.demo1\.sidebar-collapse \.sidebar:hover\s*\{/);
  });

  /**
   * The gate above stops a tap EXPANDING the rail. It does not stop `:hover`
   * MATCHING: a tap on a touch device leaves a sticky hover on the element
   * until something else takes it, and every rule that paints the collapsed
   * rail is written as `:not(:hover)`. So the rail stayed 80px while the
   * labels, badges and submenu indicators inside it reappeared, which reads as
   * a broken rail rather than a peek.
   */
  describe('the collapsed rail keeps its appearance under a sticky tap-hover', () => {
    const coarse = block(demo1Css, '@media (hover: none), (pointer: coarse)');

    it('re-asserts the collapsed appearance without depending on :hover', () => {
      expect(coarse).not.toContain(':hover');
    });

    it.each([
      ['.default-logo', /\.demo1\.sidebar-collapse \.sidebar \.default-logo/],
      ['.small-logo', /\.demo1\.sidebar-collapse \.sidebar \.small-logo/],
      ['menu titles', /\[data-slot='accordion-menu-title'\]/],
      ['badges', /\[data-slot='badge'\]/],
      ['sub-indicators', /\[data-slot='accordion-menu-sub-indicator'\]/],
      ['sub-content', /\[data-slot='accordion-menu-sub-content'\]/],
      ['menu labels', /\[data-slot='accordion-menu-label'\]/],
    ])('covers %s', (_name, pattern) => {
      expect(coarse).toMatch(pattern);
    });

    it('hides what the :not(:hover) rules hide', () => {
      expect(coarse).toMatch(/\.default-logo\s*\{\s*display:\s*none/);
      expect(coarse).toMatch(/\.small-logo\s*\{\s*display:\s*flex/);
    });
  });
});
