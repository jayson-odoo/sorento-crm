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


/**
 * Every `selector { ... }` rule directly inside `block`, in source order.
 * Comments are dropped first or they read as part of the next selector.
 * Nested at-rules are not expected inside the reduced-motion block and would
 * be skipped by this pattern (it never matches a `{` inside a body).
 */
function rules(blockBody: string): { selector: string; body: string }[] {
  const out: { selector: string; body: string }[] = [];
  const pattern = /([^{}]+)\{([^{}]*)\}/g;
  blockBody = blockBody.replace(/\/\*[\s\S]*?\*\//g, '');
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(blockBody)) !== null) {
    out.push({ selector: match[1].trim(), body: match[2] });
  }
  return out;
}

/**
 * Specificity of a single compound selector, as (ids, classes, elements).
 *
 * Enough for the selectors this block actually contains - attribute selectors,
 * classes and `:not()` - and no more: `:not()`'s own argument counts, the
 * `:not` itself does not, which is exactly the rule that decided the drawer
 * bug (`[data-slot$="-content"]:not(...):not(...)` is (0,3,0) and beat
 * `[data-vaul-drawer]` at (0,1,0), both being `!important`).
 */
function specificity(selector: string): [number, number, number] {
  const inner = selector.replace(/:not\(([^)]*)\)/g, ' $1 ');
  const ids = (inner.match(/#[\w-]+/g) ?? []).length;
  const classes =
    (inner.match(/\.[\w-]+/g) ?? []).length +
    (inner.match(/\[[^\]]*\]/g) ?? []).length +
    (inner.match(/:[a-z-]+(?!\()/g) ?? []).length;
  const elements = (inner.match(/(?:^|[\s>+~])[a-z][\w-]*/g) ?? []).length;
  return [ids, classes, elements];
}

const higherOrEqual = (a: [number, number, number], b: [number, number, number]) =>
  a[0] !== b[0] ? a[0] > b[0] : a[1] !== b[1] ? a[1] > b[1] : a[2] >= b[2];

/**
 * The declaration that actually wins for `el` - every rule in the block is
 * `!important` and author-origin, so the cascade is decided on specificity
 * first and source order second.
 */
function winningDeclaration(blockBody: string, el: Element, property: string): string | null {
  let winner: { spec: [number, number, number]; value: string } | null = null;
  for (const rule of rules(blockBody)) {
    const matches = rule.selector
      .split(',')
      .map((one) => one.trim())
      .filter((one) => one.length > 0 && el.matches(one));
    if (matches.length === 0) continue;
    const declared = new RegExp(`(?:^|;)\\s*${property}\\s*:\\s*([^;]+)`).exec(rule.body);
    if (!declared) continue;
    const spec = matches
      .map(specificity)
      .reduce((best, next) => (higherOrEqual(next, best) ? next : best));
    // Source order breaks a tie, hence `>=`: a later rule of equal weight wins.
    if (!winner || higherOrEqual(spec, winner.spec)) {
      winner = { spec, value: declared[1].trim().replace(/\s*!important$/, '') };
    }
  }
  return winner?.value ?? null;
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

  /**
   * The tester measured the real drawer at 150ms under reduced motion, not the
   * 1ms this block intends: vaul's drawer carries `data-slot="drawer-content"`,
   * so the M2-era `-content` rule matched it at (0,3,0) and outranked
   * `[data-vaul-drawer]` at (0,1,0) - both `!important`, so specificity, not
   * source order, decided it (evidence/M3/README.md, M3-04 FAIL).
   *
   * Asserting the SELECTORS would have missed this, so this asserts the
   * cascade: build the element vaul actually renders and ask which
   * `transition-duration` survives.
   */
  it('lets the vaul rule, not the -content rule, decide the drawer duration', () => {
    const drawer = document.createElement('div');
    drawer.setAttribute('data-vaul-drawer', '');
    drawer.setAttribute('data-slot', 'drawer-content');

    expect(winningDeclaration(reducedMotion, drawer, 'transition-duration')).toBe('1ms');
  });

  it('still resets the menu and popover surfaces it was written for', () => {
    // The exclusion is drawer-shaped, not a hole: a dropdown's content still
    // gets the 150ms reset that stops its enter/exit keyframes travelling.
    const menu = document.createElement('div');
    menu.setAttribute('data-slot', 'dropdown-menu-content');

    expect(winningDeclaration(reducedMotion, menu, 'transition-duration')).toBe('150ms');
  });

  it('reaches the activities panel, whose own slide carries the shared class', () => {
    // `transition-transform duration-200` matches none of the selectors in this
    // block (a NAMED duration utility is not `transition-[...]`, and the
    // <aside> has no data-slot), so the panel slid for 200ms under reduced
    // motion (evidence/M3/README.md, M3-04 FAIL). Fixed at the site with the
    // shared `motion-reduce:` class rather than by widening this block.
    const layout = fs.readFileSync(
      path.join(root, 'components/common/ActivitiesNotesPanel/EntityActivitiesLayout.tsx'),
      'utf8',
    );
    // The tag itself, not the file: a `motion-reduce:` anywhere else in it
    // would not be on the element that slides. (`<aside` also appears in this
    // file's own prose comment, hence matching on the className that follows.)
    const aside = /<aside\s+className=\{cn\(([\s\S]*?)\)\}/.exec(layout);
    expect(aside, 'expected an <aside className={cn(...)}> in EntityActivitiesLayout').not.toBeNull();
    expect(aside![1]).toContain('transition-transform');
    expect(aside![1]).toContain('motion-reduce:transition-none');
  });
});
