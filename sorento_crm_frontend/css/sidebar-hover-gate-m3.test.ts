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
});
