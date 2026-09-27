/**
 * D15 - Add specification (the product tab's picker, `components/spec-table`)
 * lists a key by its label, never its snake_case `spec_key`.
 */
import { describe, it, expect } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { AddSpecificationDialog } from '@/components/spec-table';

const SNAKE_CASE = /\w_\w/;

describe('D15 guard - Add specification', () => {
  it('the picker lists a category-derived key by its label', () => {
    render(
      <AddSpecificationDialog
        open
        onOpenChange={() => {}}
        applicableKeys={[
          {
            spec_key: 'from_category',
            label: 'Product class',
            data_type: 'enum',
            unit: null,
            allowed_values: ['rose_gold'],
            synonyms: {},
          },
          {
            // No label of its own: the picker must humanise the key, never print it.
            spec_key: 'capacity_oz',
            label: '',
            data_type: 'numeric',
            unit: 'oz',
            allowed_values: [],
            synonyms: {},
          },
        ]}
        otherKeys={[]}
        heldKeys={[]}
        canCreateKey={false}
        onPick={() => {}}
        onCreateKey={async () => {}}
        onCheckSimilar={async () => null}
      />,
    );

    // Open the picker so its option list (not only the trigger) renders.
    fireEvent.click(document.body.querySelector('button[role="combobox"]')!);
    expect(screen.getByRole('option', { name: 'Product class' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Capacity oz' })).toBeInTheDocument();

    // The dialog portals to `document.body`; the render's own container is empty.
    const match = (document.body.textContent ?? '').match(SNAKE_CASE);
    expect(match, `rendered a snake_case value: "${match?.[0]}"`).toBeNull();
  });
});
