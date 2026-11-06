/**
 * PRICETAG-COMBO-FORMAT fix round 1, R8: "Product data changed" shows a formatted description as
 * plain text, never as markup. The old and new values of a description change arrive as the stored
 * HTML; the dialog reads them through `richPlainText`.
 *
 * Written test-FIRST: today the value is printed as is, so `<p>` and `<strong>` show on screen.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import ProductDataReviewDialog from './ProductDataReviewDialog';
import type { TagDataChangeSet } from '@/lib/dealer-kit/product-data-changes';

const CHANGE_SET: TagDataChangeSet = {
  tag_id: 'tag-1',
  tag_label: '1a',
  line_id: 'line-1',
  code: 'ZZT-SINK-1',
  name: 'ZZT Kitchen Sink',
  changes: [
    {
      field: 'price_tag_description',
      label: 'Price tag description',
      old: '<p><strong>SRTBF11416</strong> (CABINET)</p><p>L400xW345xH390mm</p>',
      new: '<p>Updated</p><ul><li>First</li><li>Second</li></ul>',
      old_image_url: null,
      new_image_url: null,
      note: null,
    },
  ],
};

function draw() {
  return render(
    <ProductDataReviewDialog open onOpenChange={vi.fn()} changeSet={CHANGE_SET} onDecide={vi.fn(async () => {})} />,
  );
}

describe('review dialog shows rich values as plain text (R8)', () => {
  it('R8: no tag text reaches the page', () => {
    draw();
    const text = document.body.textContent ?? '';
    for (const raw of ['<p>', '</p>', '<strong>', '<ul>', '<li>']) expect(text, raw).not.toContain(raw);
  });

  it('R8: the old value reads as its lines', () => {
    draw();
    expect(document.body.textContent).toContain('SRTBF11416 (CABINET)');
    expect(document.body.textContent).toContain('L400xW345xH390mm');
  });

  it('R8: bullets read as bullets in the new value', () => {
    draw();
    expect(document.body.textContent).toContain('• First');
    expect(document.body.textContent).toContain('• Second');
  });
});
