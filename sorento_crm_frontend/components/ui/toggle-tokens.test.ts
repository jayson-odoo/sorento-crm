/**
 * UI v2 phase 0, slice S3 (red first). UAC C-9 (decision D9: TOGGLE-SELECTED, one token pair).
 *
 * CONTRACT:
 *   - css/config.reui.css defines `--toggle-selected-bg` and `--toggle-selected-fg`:
 *       :root                 -> var(--primary)       / var(--primary-foreground)   (v1 pixels unchanged)
 *       :root[data-ui='v2']   -> var(--primary-soft)  / var(--primary)              (soft tint, primary text)
 *     (a `.dark[data-ui='v2']` rule may restate them; if present it must keep the soft pair)
 *   - components/ui/toggle.tsx (selector data-[state=on]) and components/ui/tabs.tsx pill variants
 *     `default` and `button` (data-[state=active]) use `bg-(--toggle-selected-bg)` and
 *     `text-(--toggle-selected-fg)` instead of bg-primary / text-primary-foreground. ToggleGroupItem reuses
 *     toggleVariants, so it follows.
 *   - the `line` tab variant keeps its underline and gets no fill.
 *   NOTE for the coder: components/ui/toggle.selected.test.tsx and tabs.selected.test.tsx pin the OLD class strings
 *   (`data-[state=on]:bg-primary`, `data-[state=active]:bg-primary`); they must be updated to the token form in
 *   the same change (the v1 rule they describe is unchanged in pixels).
 */
import { describe, expect, it } from 'vitest';
import fs from 'fs';
import path from 'path';

const root = path.resolve(__dirname, '..', '..');
const read = (rel: string) => fs.readFileSync(path.join(root, rel), 'utf8');
const css = read('css/config.reui.css');

/** Leaf rules (no nested braces): [selector, body]. Comments are stripped first. */
function rules(text: string): Array<[string, string]> {
  const out: Array<[string, string]> = [];
  const re = /([^{}]+)\{([^{}]*)\}/g;
  const clean = text.replace(/\/\*[\s\S]*?\*\//g, '');
  let m: RegExpExecArray | null;
  while ((m = re.exec(clean))) {
    const sel = m[1].split(/[;}]/).pop()!.trim();
    out.push([sel, m[2]]);
  }
  return out;
}

const decl = (body: string, name: string) =>
  new RegExp(`${name}\\s*:\\s*([^;]+);`).exec(body)?.[1].trim();

const V2 = /\[data-ui=["']v2["']\]/;

describe('toggle-selected tokens in css/config.reui.css', () => {
  const all = rules(css);

  it('v1: :root resolves to the primary fill (today)', () => {
    const rootRules = all.filter(([sel]) => /(^|,)\s*:root\s*(,|$)/.test(sel) && !V2.test(sel));
    expect(rootRules.some(([, b]) => decl(b, '--toggle-selected-bg') === 'var(--primary)')).toBe(true);
    expect(rootRules.some(([, b]) => decl(b, '--toggle-selected-fg') === 'var(--primary-foreground)')).toBe(true);
  });

  it('v2: :root[data-ui="v2"] resolves to the soft tint with primary text', () => {
    const v2Rules = all.filter(([sel]) => V2.test(sel) && /:root/.test(sel) && !/\.dark/.test(sel));
    expect(v2Rules.length).toBeGreaterThan(0);
    expect(v2Rules.some(([, b]) => decl(b, '--toggle-selected-bg') === 'var(--primary-soft)')).toBe(true);
    expect(v2Rules.some(([, b]) => decl(b, '--toggle-selected-fg') === 'var(--primary)')).toBe(true);
  });

  it('no v2 rule resolves the pair back to the primary fill', () => {
    for (const [sel, body] of all.filter(([s]) => V2.test(s))) {
      expect(decl(body, '--toggle-selected-bg'), sel).not.toBe('var(--primary)');
    }
  });
});

describe('components consume the pair', () => {
  const toggle = read('components/ui/toggle.tsx');
  const tabs = read('components/ui/tabs.tsx');

  it('Toggle (and so ToggleGroupItem) selected state uses the tokens', () => {
    expect(toggle).toContain('data-[state=on]:bg-(--toggle-selected-bg)');
    expect(toggle).toContain('data-[state=on]:text-(--toggle-selected-fg)');
    expect(toggle).not.toContain('data-[state=on]:bg-primary');
    expect(toggle).not.toContain('data-[state=on]:text-primary-foreground');
  });

  it('pill tab variants (default, button) use the tokens', () => {
    expect(tabs).toContain('data-[state=active]:bg-(--toggle-selected-bg)');
    expect(tabs).toContain('data-[state=active]:text-(--toggle-selected-fg)');
    expect(tabs).not.toContain('data-[state=active]:bg-primary');
    expect(tabs).not.toContain('data-[state=active]:text-primary-foreground');
  });

  it('the line variant keeps its primary underline', () => {
    expect(tabs).toContain('data-[state=active]:border-primary');
  });
});
