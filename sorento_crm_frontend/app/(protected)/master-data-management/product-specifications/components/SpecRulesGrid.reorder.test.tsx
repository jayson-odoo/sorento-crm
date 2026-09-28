/**
 * AC-S1.9 (fix round 1) - a drop reorders the draft at once, through
 * `onChange`, the same shape `SalesOrderLinesTable.reorder.test.tsx` asserts
 * for its own table: dnd-kit measures real layout, which jsdom has none of,
 * so the shared rows component is replaced by one that hands back the ids it
 * was given and fires the grid's own `handleDragEnd` with an `active`/`over`
 * pair, exactly as dnd-kit would.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn(), message: vi.fn(), dismiss: vi.fn() },
}));

vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

vi.mock('@/components/ui/data-grid-table-dnd-rows', () => ({
  DataGridTableDndRowHandle: ({ rowId }: { rowId: string }) => (
    <span data-testid={`handle-${rowId}`} />
  ),
  DataGridTableDndRows: ({
    handleDragEnd,
    dataIds,
  }: {
    handleDragEnd: (event: { active: { id: string }; over: { id: string } | null }) => void;
    dataIds: string[];
  }) => (
    <div>
      <p data-testid="drag-ids">{dataIds.join(',')}</p>
      <button
        type="button"
        onClick={() => handleDragEnd({ active: { id: dataIds[1] }, over: { id: dataIds[0] } })}
      >
        drop second on first
      </button>
    </div>
  ),
}));

import { SpecRulesGrid } from './SpecRulesGrid';
import type { SpecDerivationRule, SpecRegistryKey } from '../types/productSpec.types';

function withClient(children: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const SHAPE: SpecRegistryKey = {
  spec_key: 'shape',
  label: 'Shape',
  data_type: 'enum',
  unit: null,
  allowed_values: ['round', 'square'],
  excluded_values: [],
  user_values: [],
  suppressed_values: [],
  value_weights: {},
  derivation_rules: [],
  effective_rules: [],
  synonyms: {},
  value_labels: {},
  applies_when: {},
  read_from: 'rules',
  rank_weight: null,
  measured_coverage: 0,
  source: 'seed',
  user_synonyms: {},
  suppressed_synonyms: {},
  match_tolerance: 0,
  match_decay: 0,
  is_active: true,
};

const ROUND_RULE: SpecDerivationRule = {
  builder: { kind: 'words', look_in: 'name', words: ['ROUND'], value: 'round' },
  _uid: 'r0',
};
const SQUARE_RULE: SpecDerivationRule = {
  builder: { kind: 'words', look_in: 'name', words: ['SQUARE'], value: 'square' },
  _uid: 'r1',
};

describe('SpecRulesGrid - drag to reorder, no toggle to press first (AC-S1.9)', () => {
  it('hands the DnD shell every rule id, in Order', () => {
    render(
      withClient(
        <SpecRulesGrid
          rules={[ROUND_RULE, SQUARE_RULE]}
          spec={SHAPE}
          registry={[SHAPE]}
          mode="edit"
          onChange={vi.fn()}
          onEdit={vi.fn()}
          onAdd={vi.fn()}
        />,
      ),
    );

    expect(screen.getByTestId('drag-ids')).toHaveTextContent('r0,r1');
  });

  it('a drop reorders the draft list at once, through onChange', () => {
    const onChange = vi.fn();
    render(
      withClient(
        <SpecRulesGrid
          rules={[ROUND_RULE, SQUARE_RULE]}
          spec={SHAPE}
          registry={[SHAPE]}
          mode="edit"
          onChange={onChange}
          onEdit={vi.fn()}
          onAdd={vi.fn()}
        />,
      ),
    );

    fireEvent.click(screen.getByRole('button', { name: 'drop second on first' }));

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith([SQUARE_RULE, ROUND_RULE]);
  });
});
