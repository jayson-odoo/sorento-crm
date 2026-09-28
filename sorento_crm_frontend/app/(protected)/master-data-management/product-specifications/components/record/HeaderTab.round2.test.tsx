/**
 * Review round 2 (PR #1302) on Other names for this specification
 * (`WordsDataGrid` under Details):
 * - S-5: renaming a built-in word keeps the old one taken away after Save.
 * - B-5: one Remove at a time.
 * - A word added in this sitting is dropped locally: no countdown, no call.
 */
import React, { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn(), message: vi.fn(), dismiss: vi.fn() },
}));

type Current = { pending: Record<string, unknown> | null; last_outcome: Record<string, unknown> | null };
let current: Current = { pending: null, last_outcome: null };
const createPendingAction = vi.fn();
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: (...args: unknown[]) => createPendingAction(...args),
  cancelPendingAction: vi.fn().mockResolvedValue({}),
  getCurrentPendingAction: vi.fn(async () => current),
}));

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

import { HeaderTab } from './HeaderTab';
import { buildPatchBody, projectSpecKeyDraft, type SpecKeyDraft } from '../../hooks/useSpecKeyRecord';
import type { SpecRegistryKey } from '../../types/productSpec.types';

const CAPACITY: SpecRegistryKey = {
  spec_key: 'capacity_oz',
  label: 'Capacity (oz)',
  data_type: 'numeric',
  unit: 'oz',
  allowed_values: [],
  synonyms: { _self: ['oz', 'ounce'] },
  excluded_values: [],
  user_values: [],
  suppressed_values: [],
  value_weights: {},
  derivation_rules: [],
  effective_rules: [],
  applies_when: {},
  read_from: 'rules',
  rank_weight: 1,
  measured_coverage: null,
  source: 'seed',
  user_synonyms: {},
  suppressed_synonyms: {},
  match_tolerance: 0,
  match_decay: 0,
  is_active: true,
};

let latest: SpecKeyDraft | null = null;
function EditHarness({ row }: { row: SpecRegistryKey }) {
  const [draft, setDraftState] = useState<SpecKeyDraft>(() => projectSpecKeyDraft(row));
  latest = draft;
  return <HeaderTab row={row} mode="edit" draft={draft} setDraft={(u) => setDraftState((d) => u(d))} />;
}

function renderHarness() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <EditHarness row={CAPACITY} />
    </QueryClientProvider>,
  );
}

const ACTION = {
  id: 'pa-3',
  action_key: 'spec_word.remove',
  entity_type: 'spec_word',
  entity_id: 'capacity_oz',
  commit_at: new Date(Date.now() + 5000).toISOString(),
  window_seconds: 5,
};

beforeEach(() => {
  latest = null;
  current = { pending: null, last_outcome: null };
  createPendingAction.mockReset();
  createPendingAction.mockImplementation(async () => {
    current = { pending: ACTION, last_outcome: null };
    return ACTION;
  });
});

describe('S-5 - a renamed built-in word stays taken away after Save', () => {
  it('renaming "oz" to "fl oz" suppresses "oz" and adds "fl oz"', () => {
    renderHarness();

    fireEvent.click(screen.getByRole('button', { name: 'oz' }));
    const input = screen.getByLabelText('Edit oz');
    fireEvent.change(input, { target: { value: 'fl oz' } });
    fireEvent.blur(input);

    const body = buildPatchBody(CAPACITY, latest!);
    expect(body.suppressed_synonyms._self).toEqual(['oz']);
    expect(body.user_synonyms._self).toEqual(['fl oz']);
  });
});

describe('B-5 - one Remove at a time on Other names', () => {
  it('while "oz" is counting down, "ounce" cannot start a second removal', async () => {
    renderHarness();

    fireEvent.click(within(screen.getByLabelText('oz actions').closest('tr')!).getByText('Remove'));
    await screen.findByText(/Removing in \ds/);

    const second = within(screen.getByLabelText('ounce actions').closest('tr')!).getByText('Remove');
    expect(second).toBeDisabled();
    fireEvent.click(second);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(createPendingAction).toHaveBeenCalledTimes(1);
  });
});

describe('A word added in this sitting is dropped locally', () => {
  it('Remove on it drops it with no countdown and no server call', async () => {
    renderHarness();

    fireEvent.click(screen.getByText('+ Add a word'));
    fireEvent.change(screen.getByPlaceholderText('e.g. oz'), { target: { value: 'ounces' } });
    fireEvent.keyDown(screen.getByPlaceholderText('e.g. oz'), { key: 'Enter' });
    expect(latest!.words._self).toContain('ounces');

    fireEvent.click(within(screen.getByLabelText('ounces actions').closest('tr')!).getByText('Remove'));

    expect(latest!.words._self).not.toContain('ounces');
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(createPendingAction).not.toHaveBeenCalled();
    expect(screen.queryByText(/Removing in/)).toBeNull();
  });
});
