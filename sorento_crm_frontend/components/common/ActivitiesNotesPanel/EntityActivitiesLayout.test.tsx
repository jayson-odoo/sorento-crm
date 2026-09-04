/**
 * M3-03 (`ui-motion-round2`) - the content column no longer shifts when the
 * Activities & Notes panel opens: the panel overlays it (fixed position,
 * `translate-x`), so there is nothing here to animate.
 *
 * A source scan, not a render: mounting the full component pulls in
 * `RichTextEditor` (Tiptap) and several service calls for no benefit here -
 * the property this test asserts ("the main column's class never changes
 * with `open`") is a static fact about the JSX, not something a render adds
 * confidence to. Same reasoning as the other inventory-style tests in this
 * repo (e.g. `css/design-tokens.test.ts`).
 */
import { describe, expect, it } from 'vitest';
import fs from 'fs';
import path from 'path';

const source = fs.readFileSync(
  path.resolve(__dirname, 'EntityActivitiesLayout.tsx'),
  'utf8',
);

describe('EntityActivitiesLayout main column', () => {
  it('never animates margin', () => {
    expect(source).not.toMatch(/transition-\[margin/);
  });

  it('carries no mr-* toggle tied to the open state', () => {
    expect(source).not.toMatch(/\bmr-\[420px\]/);
    expect(source).not.toMatch(/\blg:mr-/);
  });

  it('keeps the panel a fixed-position overlay that never changes the main column', () => {
    // The main column: no width/margin-affecting class conditioned on `open`.
    const mainMatch = /<main\s+className="([^"]*)">/.exec(source);
    expect(mainMatch, 'expected a plain string className on <main>').not.toBeNull();
    const mainClass = mainMatch![1];
    expect(mainClass).not.toContain('mr-');
    expect(mainClass).not.toContain('margin');

    // The panel itself stays the thing that moves, via transform.
    expect(source).toContain('translate-x-full');
    expect(source).toContain('transition-transform');
  });
});
