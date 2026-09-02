/**
 * Insert field (D59, AC-M.24).
 *
 * Written before the dialog. Two things are worth pinning: a field lands where
 * the cursor is rather than at the end (a designer inserting into the middle of
 * a sentence is the whole point), and the preview line says what the tag will
 * actually read - because a token that is going to resolve to nothing looks
 * exactly like one that will resolve fine until somebody previews it.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { TagBindingData } from '@/lib/dealer-kit/tag-template-types';
import { InsertFieldDialog } from './InsertFieldDialog';

const SPEC_KEYS = [
  { key: 'material', label: 'Material', unit: null },
  { key: 'diameter', label: 'Diameter', unit: 'mm' },
];

const DATA: TagBindingData = {
  kind: 'product',
  product: {
    id: 'p1',
    code: 'CBF3612',
    name: 'Carysil Big Bowl Sink',
    dimensions: '860 x 500 x 220 mm',
    spec_lines: ['Nano grain finish'],
    specs: [
      { key: 'material', label: 'Material', value: 'granite', unit: null },
      { key: 'diameter', label: 'Diameter', value: '407', unit: 'mm' },
    ],
    images: [],
    list_price: 2000,
    offer_price: 1500,
    promotion_id: null,
    barcode: null,
  },
};

function open(props: Partial<Parameters<typeof InsertFieldDialog>[0]> = {}) {
  const onDone = vi.fn();
  render(
    <InsertFieldDialog
      open
      value=""
      data={null}
      specKeys={SPEC_KEYS}
      onCancel={vi.fn()}
      onDone={onDone}
      {...props}
    />,
  );
  return onDone;
}

function content(): HTMLTextAreaElement {
  return screen.getByLabelText('Content') as HTMLTextAreaElement;
}

describe('InsertFieldDialog', () => {
  it('lists the catalogue grouped, with the token beside each label', () => {
    open();

    expect(screen.getByText('Product')).toBeTruthy();
    expect(screen.getByText('Specs')).toBeTruthy();
    expect(screen.getByText('Set')).toBeTruthy();
    expect(screen.getByText('Line')).toBeTruthy();
    expect(screen.getByText('{{product.code}}')).toBeTruthy();
    expect(screen.getByText('{{spec.material}}')).toBeTruthy();
  });

  it('the search box narrows the list to what was typed', () => {
    open();

    fireEvent.change(screen.getByPlaceholderText('Search fields...'), {
      target: { value: 'material' },
    });

    expect(screen.getByText('{{spec.material}}')).toBeTruthy();
    expect(screen.queryByText('{{product.code}}')).toBeNull();
  });

  it('inserts at the cursor, not at the end', () => {
    open({ value: 'Made of  today' });

    const box = content();
    box.setSelectionRange(8, 8);
    fireEvent.select(box);

    fireEvent.click(screen.getByText('{{spec.material}}'));

    expect(content().value).toBe('Made of {{spec.material}} today');
  });

  it('replaces the selection when there is one', () => {
    open({ value: 'Made of steel' });

    const box = content();
    box.setSelectionRange(8, 13);
    fireEvent.select(box);

    fireEvent.click(screen.getByText('{{spec.material}}'));

    expect(content().value).toBe('Made of {{spec.material}}');
  });

  it('says there is nothing to preview against until a product is chosen', () => {
    open({ value: 'Made of {{spec.material}}' });

    expect(screen.getByText('(preview a product to see values)')).toBeTruthy();
  });

  it('previews the resolved words once the layer has data', () => {
    open({
      value: '{{product.code}} in {{spec.material}}, {{spec.diameter}}',
      data: DATA,
    });

    expect(screen.getByText('CBF3612 in granite, 407 mm')).toBeTruthy();
  });

  it('the preview follows what is typed, so a bad token is visible before Done', () => {
    open({ data: DATA });

    fireEvent.change(content(), { target: { value: '[{{spec.finish}}]' } });

    expect(screen.getByText('[]')).toBeTruthy();
  });

  it('Done hands back the content once', () => {
    const onDone = open({ value: 'Code: ' });

    fireEvent.click(screen.getByText('{{product.code}}'));
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));

    expect(onDone).toHaveBeenCalledTimes(1);
    expect(onDone).toHaveBeenCalledWith('Code: {{product.code}}');
  });
});
