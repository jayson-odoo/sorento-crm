/**
 * Review round 3 (PR #1302) on the rules tab:
 * - S-R3: a saved Number rule opened in the modal and saved unchanged is still the
 *   saved rule. The modal writes `ignore_below: null`, the server stores no
 *   `ignore_below`, and Remove used to drop the rule locally, with no countdown and
 *   no `spec_rule.remove`, so the page Save deleted it outside the deferred window.
 * - N-R8: a rule added in this sitting that reads the same as a saved one is not
 *   the saved one; its Remove drops it locally and parks nothing.
 */
import React, { useState } from 'react';
import { beforeEach, describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn(), message: vi.fn(), dismiss: vi.fn() },
}));
vi.mock('../../hooks/useSpecTryIt', () => ({
  useSpecTryIt: () => ({ result: null, loading: false, error: null }),
}));
vi.mock('../../hooks/useSpecPreview', () => ({
  useSpecPreview: () => ({ status: 'idle', result: null, error: null, run: vi.fn() }),
}));
vi.mock('../../services/productSpecService', () => ({
  fetchProductPickerOptions: vi.fn().mockResolvedValue([]),
}));
const createPendingAction = vi.fn();
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: (...args: unknown[]) => createPendingAction(...args),
  cancelPendingAction: vi.fn().mockResolvedValue({}),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
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

import { RulesTab } from './RulesTab';
import { projectSpecKeyDraft, type SpecKeyDraft } from '../../hooks/useSpecKeyRecord';
import type { SpecDerivationRule, SpecRegistryKey } from '../../types/productSpec.types';

function withClient(children: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function key(overrides: Partial<SpecRegistryKey>): SpecRegistryKey {
  return {
    spec_key: 'bowl_width',
    label: 'Bowl width',
    data_type: 'numeric',
    unit: 'mm',
    allowed_values: [],
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
    ...overrides,
  };
}

let latest: SpecKeyDraft | null = null;

function Harness({ row, extra = [] }: { row: SpecRegistryKey; extra?: SpecDerivationRule[] }) {
  const [draft, setDraftState] = useState<SpecKeyDraft>(() => {
    const projected = projectSpecKeyDraft(row);
    return { ...projected, rules: [...projected.rules, ...extra] };
  });
  latest = draft;
  return (
    <RulesTab
      row={row}
      registry={[row]}
      mode="edit"
      draft={draft}
      setDraft={(updater) => setDraftState((current) => updater(current))}
      onEnterEdit={() => {}}
    />
  );
}

const rowOf = (n: number) => screen.getByLabelText(`Rule ${n} actions`).closest('tr')!;

beforeEach(() => {
  createPendingAction.mockReset();
  createPendingAction.mockImplementation(async ({ entityId }: { entityId: string }) => ({
    id: 'pa-1',
    action_key: 'spec_rule.remove',
    entity_type: 'spec_rule',
    entity_id: entityId,
    commit_at: new Date(Date.now() + 5000).toISOString(),
    window_seconds: 5,
  }));
});

describe('S-R3 - a saved Number rule saved unchanged in the modal is still the saved rule', () => {
  it('its Remove parks spec_rule.remove instead of dropping it locally', async () => {
    // The stored form, exactly as `clean_builder` writes it: no ignore_below.
    const stored: SpecDerivationRule = { builder: { kind: 'number', look_in: 'any', before: ['MM'] } };
    render(withClient(<Harness row={key({ derivation_rules: [stored], effective_rules: [stored] })} />));

    fireEvent.click(within(rowOf(1)).getByText('Edit'));
    const dialog = await screen.findByRole('dialog', { name: /a rule/ });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save rule' }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: /a rule/ })).not.toBeInTheDocument());

    fireEvent.click(within(rowOf(1)).getByText('Remove'));

    await screen.findByText(/Removing in \ds/);
    expect(createPendingAction).toHaveBeenCalledTimes(1);
    expect(createPendingAction.mock.calls[0][0]).toMatchObject({ actionKey: 'spec_rule.remove' });
    expect(latest!.rules, 'the rule stays until the countdown commits').toHaveLength(1);
  });
});

describe('N-R8 - a rule added in this sitting is never the saved one', () => {
  it('Remove on an added rule that reads the same as a saved one drops it locally', async () => {
    const round: SpecDerivationRule = { builder: { kind: 'words', look_in: 'name', words: ['ROUND'], value: 'round' } };
    const row = key({
      spec_key: 'shape',
      label: 'Shape',
      data_type: 'enum',
      unit: null,
      allowed_values: ['round'],
      derivation_rules: [round],
      effective_rules: [round],
    });
    render(withClient(<Harness row={row} extra={[{ ...round, _uid: 'new-77' }]} />));

    fireEvent.click(within(rowOf(2)).getByText('Remove'));
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(createPendingAction).not.toHaveBeenCalled();
    expect(latest!.rules.map((r) => r._uid)).toEqual(['r0']);
  });
});
