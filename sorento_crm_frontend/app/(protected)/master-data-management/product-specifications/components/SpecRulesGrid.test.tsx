/**
 * AC-S1.9, AC-S1.14 (fix round 1) - the rules grid is the shared `DataGrid`
 * (fixed, resizable columns), not a hand-rolled `<table>`: row drag-reorder
 * goes through `components/ui/data-grid-table-dnd-rows.tsx` (the same shell
 * `SalesOrderLinesTable.tsx` uses), with a handle on every row only while
 * sorted by Order; sorting by anything else drops the handles and falls back
 * to the plain `DataGridTable`. Remove is `spec_rule.remove` (D7, D8): a
 * server-deferred action, not a local timer.
 *
 * The actual DROP is simulated in `SpecRulesGrid.reorder.test.tsx` (dnd-kit
 * measures real layout, which jsdom has none of) - this file renders the real
 * `DataGridTableDndRows`/`DataGridTable` unmocked, so the header's own sort
 * click is real too.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn(), message: vi.fn(), dismiss: vi.fn() },
}));

const createPendingAction = vi.fn().mockResolvedValue({
  id: 'pa-1',
  action_key: 'spec_rule.remove',
  entity_type: 'spec_rule',
  entity_id: 'shape',
  commit_at: new Date(Date.now() + 5000).toISOString(),
  window_seconds: 5,
});
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: (...args: unknown[]) => createPendingAction(...args),
  cancelPendingAction: vi.fn().mockResolvedValue({}),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

/** The dropdown-menu stub renders children flat - established pattern, see
 *  `PackingListsList.test.tsx`; Radix's own portal timing is not what this
 *  suite is testing. */
type MenuSlotProps = { children?: React.ReactNode };
type MenuItemProps = MenuSlotProps & { onClick?: () => void; disabled?: boolean; variant?: string };
vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: MenuSlotProps) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: MenuSlotProps) => <>{children}</>,
  DropdownMenuContent: ({ children }: MenuSlotProps) => <div>{children}</div>,
  DropdownMenuItem: ({ children, onClick, disabled }: MenuItemProps) => (
    <button type="button" onClick={onClick} disabled={disabled}>
      {children}
    </button>
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

function renderGrid(overrides: Partial<React.ComponentProps<typeof SpecRulesGrid>> = {}) {
  const onChange = vi.fn();
  const utils = render(
    withClient(
      <SpecRulesGrid
        rules={[ROUND_RULE, SQUARE_RULE]}
        spec={SHAPE}
        registry={[SHAPE]}
        mode="edit"
        onChange={onChange}
        onEdit={vi.fn()}
        onAdd={vi.fn()}
        {...overrides}
      />,
    ),
  );
  return { onChange, ...utils };
}

describe('SpecRulesGrid - drag handles only while sorted by Order (AC-S1.9)', () => {
  it('draws a drag handle on every row while sorted by Order, edit mode', () => {
    renderGrid();
    expect(screen.getAllByLabelText('Drag to reorder')).toHaveLength(2);
  });

  it('sorting by another column drops the drag handles', () => {
    renderGrid();
    fireEvent.click(screen.getByRole('button', { name: /Where to look/ }));
    expect(screen.queryAllByLabelText('Drag to reorder')).toHaveLength(0);
  });

  it('view mode never draws a drag handle', () => {
    renderGrid({ mode: 'view' });
    expect(screen.queryAllByLabelText('Drag to reorder')).toHaveLength(0);
  });
});

describe('SpecRulesGrid - Remove is spec_rule.remove, server-deferred (D7, D8, fix round 1)', () => {
  it('Remove parks spec_rule.remove keyed by the spec key, payload the builder', async () => {
    // Review round 2: only a rule the server holds is removed on the server; one
    // that exists only in the draft is dropped locally. These two are saved.
    renderGrid({ spec: { ...SHAPE, effective_rules: [ROUND_RULE, SQUARE_RULE] } });

    const row = screen.getByLabelText('Rule 1 actions').closest('tr')!;
    fireEvent.click(within(row).getByText('Remove'));

    await waitFor(() =>
      expect(createPendingAction).toHaveBeenCalledWith({
        actionKey: 'spec_rule.remove',
        entityType: 'spec_rule',
        entityId: 'shape',
        payload: { builder: ROUND_RULE.builder },
      }),
    );
  });
});
