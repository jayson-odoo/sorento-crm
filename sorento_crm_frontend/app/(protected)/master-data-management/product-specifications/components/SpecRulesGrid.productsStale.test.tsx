/**
 * S-12 (review round 2) - a committed rule removal re-reads products on the
 * server, so the Products tab and the Choices counts have to be fetched again.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn(), message: vi.fn(), dismiss: vi.fn() },
}));

const ACTION = {
  id: 'pa-11',
  action_key: 'spec_rule.remove',
  entity_type: 'spec_rule',
  entity_id: 'shape',
  commit_at: new Date(Date.now() + 5000).toISOString(),
  window_seconds: 5,
};
let current: { pending: unknown; last_outcome: unknown } = { pending: null, last_outcome: null };
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(async () => {
    current = { pending: ACTION, last_outcome: null };
    return ACTION;
  }),
  cancelPendingAction: vi.fn().mockResolvedValue({}),
  getCurrentPendingAction: vi.fn(async () => current),
}));

type MenuSlotProps = { children?: React.ReactNode };
type MenuItemProps = MenuSlotProps & { onClick?: () => void; disabled?: boolean };
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

const ROUND: SpecDerivationRule = {
  builder: { kind: 'words', look_in: 'name', words: ['ROUND'], value: 'round' },
  _uid: 'r0',
};

const SHAPE: SpecRegistryKey = {
  spec_key: 'shape',
  label: 'Shape',
  data_type: 'enum',
  unit: null,
  allowed_values: ['round'],
  excluded_values: [],
  user_values: [],
  suppressed_values: [],
  value_weights: {},
  derivation_rules: [{ builder: ROUND.builder }],
  effective_rules: [{ builder: ROUND.builder }],
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

describe('S-12 - a committed rule removal refetches the products of that spec', () => {
  it('invalidates spec-key-products for the key once the server commits', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const spy = vi.spyOn(client, 'invalidateQueries');
    const onChange = vi.fn();
    render(
      <QueryClientProvider client={client}>
        <SpecRulesGrid
          rules={[ROUND]}
          spec={SHAPE}
          registry={[]}
          mode="edit"
          onChange={onChange}
          onEdit={vi.fn()}
          onAdd={vi.fn()}
        />
      </QueryClientProvider>,
    );

    fireEvent.click(within(screen.getByLabelText('Rule 1 actions').closest('tr')!).getByText('Remove'));
    await screen.findByText(/Removing in \ds/);
    current = {
      pending: null,
      last_outcome: { id: ACTION.id, action_key: ACTION.action_key, status: 'committed', ended_at: new Date().toISOString() },
    };

    await waitFor(() => expect(onChange).toHaveBeenCalledWith([]), { timeout: 3000 });
    const productCalls = spy.mock.calls.filter(([filters]) => {
      const key = (filters as { queryKey?: unknown[] } | undefined)?.queryKey;
      return Array.isArray(key) && key[0] === 'spec-key-products' && key[1] === 'shape';
    });
    expect(productCalls.length).toBeGreaterThan(0);
  });
});
