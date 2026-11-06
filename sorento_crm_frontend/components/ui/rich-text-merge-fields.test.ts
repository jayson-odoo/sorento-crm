/**
 * DESIGNER-RICH-TEXT: `{{path}}` tokens become one atomic node inside the shared editor and come
 * back out as plain `{{path}}` text, so the stored HTML never carries an editor-only wrapper.
 *
 * Written test-FIRST: `rich-text-merge-fields.ts` does not exist yet.
 */
import { describe, expect, it } from 'vitest';

import { unwrapMergeFieldTokens, wrapMergeFieldTokens } from './rich-text-merge-fields';

describe('wrapMergeFieldTokens', () => {
  it('wraps every token in a merge-field span', () => {
    const out = wrapMergeFieldTokens('<p>LP: {{product.list_price}} / {{ spec.width }}</p>');
    const doc = new DOMParser().parseFromString(out, 'text/html');
    const spans = Array.from(doc.querySelectorAll('span[data-merge-field]'));
    expect(spans.map((s) => s.getAttribute('data-merge-field'))).toEqual([
      'product.list_price',
      'spec.width',
    ]);
    expect(spans.map((s) => s.textContent)).toEqual(['{{product.list_price}}', '{{ spec.width }}']);
    expect(doc.body.textContent).toBe('LP: {{product.list_price}} / {{ spec.width }}');
  });

  it('keeps the marks around a token', () => {
    const out = wrapMergeFieldTokens('<p><strong>{{product.code}}</strong></p>');
    const doc = new DOMParser().parseFromString(out, 'text/html');
    expect(doc.querySelector('strong > span[data-merge-field="product.code"]')).not.toBeNull();
  });

  it('is idempotent', () => {
    const once = wrapMergeFieldTokens('<p>{{product.code}}</p>');
    expect(wrapMergeFieldTokens(once)).toBe(once);
  });

  it('leaves content with no token unchanged', () => {
    expect(wrapMergeFieldTokens('<p>hello</p>')).toBe('<p>hello</p>');
  });
});

describe('unwrapMergeFieldTokens', () => {
  it('turns each merge-field span back into its token text, marks kept', () => {
    const html = '<p><strong>{{product.code}}</strong> x {{spec.width}}</p>';
    expect(unwrapMergeFieldTokens(wrapMergeFieldTokens(html))).toBe(html);
  });

  it('uses the stored path, not whatever text the span holds', () => {
    expect(
      unwrapMergeFieldTokens('<p><span data-merge-field="product.code" class="chip">code</span></p>'),
    ).toBe('<p>{{product.code}}</p>');
  });
});
