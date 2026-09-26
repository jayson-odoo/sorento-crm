/**
 * D15 - Add specification (the product tab's picker, `components/spec-table`)
 * lists a key by its label, never its snake_case `spec_key`.
 */
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { AddSpecificationDialog } from '@/components/spec-table';

const SNAKE_CASE = /\w_\w/;

describe('D15 guard - Add specification', () => {
  it('the picker lists a category-derived key by its label', () => {
    const { container } = render(
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
        ]}
        otherKeys={[]}
        heldKeys={[]}
        canCreateKey={false}
        onPick={() => {}}
        onCreateKey={async () => {}}
        onCheckSimilar={async () => null}
      />,
    );

    const match = (container.textContent ?? '').match(SNAKE_CASE);
    expect(match, `rendered a snake_case value: "${match?.[0]}"`).toBeNull();
  });
});
