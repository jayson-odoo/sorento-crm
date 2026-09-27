/**
 * B-4 (review round 2, PR #1302) - every rule keeps ONE stable id through the
 * rule modal, and the grid matches on that id everywhere.
 *
 * (1) A rule added in the modal and then edited in place in the grid actually
 *     changes; before the fix the modal's save dropped `_uid`, the grid fell back
 *     to a position id nobody else used, and the patch matched nothing.
 * (2) A rule moved to the top and then edited in the modal keeps its own id; it
 *     used to fall back to `r0`, colliding with the first rule's own `r0`. The edit
 *     changes a field, so it only lands if the id is kept (S-R4, review round 3).
 */
import React, { useState } from 'react';
import { describe, it, expect, vi } from 'vitest';
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
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
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

const words = (list: string[], value: string): SpecDerivationRule => ({
  builder: { kind: 'words', look_in: 'name', words: list, value },
});

function shape(rules: SpecDerivationRule[]): SpecRegistryKey {
  return {
    spec_key: 'shape',
    label: 'Shape',
    data_type: 'enum',
    unit: null,
    allowed_values: ['round', 'square', 'oval'],
    excluded_values: [],
    user_values: [],
    suppressed_values: [],
    value_weights: {},
    derivation_rules: rules,
    effective_rules: rules,
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
}

let latest: SpecKeyDraft | null = null;

function Harness({ row }: { row: SpecRegistryKey }) {
  const [draft, setDraftState] = useState<SpecKeyDraft>(() => projectSpecKeyDraft(row));
  latest = draft;
  return (
    <RulesTab
      row={row}
      registry={[row]}
      mode="edit"
      draft={draft}
      setDraft={(updater) => setDraftState((current) => updater(current))}
    />
  );
}

function pickOption(fieldLabel: string, option: string) {
  const dialog = screen.getByRole('dialog', { name: /a rule/ });
  const field = within(dialog).getByText(fieldLabel, { selector: 'label' }).closest('div')!;
  fireEvent.click(field.querySelector('button[role="combobox"]')!);
  fireEvent.click(screen.getByRole('option', { name: option }));
}

describe('B-4 - a rule keeps one stable id through the modal', () => {
  it('a rule added in the modal can then be edited in place in the grid', async () => {
    render(withClient(<Harness row={shape([words(['ROUND'], 'round')])} />));

    fireEvent.click(screen.getByRole('button', { name: 'Add a rule' }));
    const dialog = await screen.findByRole('dialog', { name: /a rule/ });
    const findField = within(dialog).getByText('What to find', { selector: 'label' }).closest('div')!;
    fireEvent.click(findField.querySelector('button[role="combobox"]')!);
    fireEvent.change(screen.getByPlaceholderText('Search...'), { target: { value: 'OVAL' } });
    fireEvent.click(document.body.querySelector('[data-slot="searchable-multi-select-create"]')!);
    pickOption('Value it sets', 'Oval');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save rule' }));

    await waitFor(() => expect(screen.queryByRole('dialog', { name: /a rule/ })).not.toBeInTheDocument());
    expect(latest?.rules).toHaveLength(2);
    const addedUid = latest!.rules[1]._uid;
    expect(addedUid, 'the added rule carries an id').toBeTruthy();
    expect(addedUid).not.toBe(latest!.rules[0]._uid);

    // Click the new rule's What to find cell and add a word in place.
    const row = screen.getByLabelText('Rule 2 actions').closest('tr')!;
    fireEvent.click(within(row).getByText('OVAL'));
    fireEvent.click(within(row).getByRole('combobox'));
    fireEvent.change(screen.getByPlaceholderText('Search...'), { target: { value: 'ELLIPSE' } });
    fireEvent.click(document.body.querySelector('[data-slot="searchable-multi-select-create"]')!);

    expect(latest!.rules[1].builder).toMatchObject({ words: ['OVAL', 'ELLIPSE'] });
    expect(latest!.rules[1]._uid).toBe(addedUid);
  });

  it('a rule moved to the top and edited in the modal keeps its own id, never another rule\'s', async () => {
    const row = shape([words(['ROUND'], 'round'), words(['SQUARE'], 'square'), words(['OVAL'], 'oval')]);
    render(withClient(<Harness row={row} />));
    const uidC = latest!.rules[2]._uid;

    // Move C to the top (the same arrayMove a drop makes).
    fireEvent.click(within(screen.getByLabelText('Rule 3 actions').closest('tr')!).getByText('Move up'));
    fireEvent.click(within(screen.getByLabelText('Rule 2 actions').closest('tr')!).getByText('Move up'));
    expect(latest!.rules[0].builder).toMatchObject({ words: ['OVAL'] });

    // Edit C in the modal: add a word to What to find, then save it. A change, so
    // the save only lands on C if the grid matches C by its own id (S-R4, round 3:
    // saving C unchanged proved nothing, a lost id left the same rules in place).
    fireEvent.click(within(screen.getByLabelText('Rule 1 actions').closest('tr')!).getByText('Edit'));
    const dialog = await screen.findByRole('dialog', { name: /a rule/ });
    const findField = within(dialog).getByText('What to find', { selector: 'label' }).closest('div')!;
    fireEvent.click(findField.querySelector('button[role="combobox"]')!);
    fireEvent.change(screen.getByPlaceholderText('Search...'), { target: { value: 'ELLIPSE' } });
    fireEvent.click(document.body.querySelector('[data-slot="searchable-multi-select-create"]')!);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save rule' }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: /a rule/ })).not.toBeInTheDocument());

    const uids = latest!.rules.map((r) => r._uid);
    expect(uids[0]).toBe(uidC);
    expect(new Set(uids).size, `duplicate rule ids: ${uids.join(',')}`).toBe(3);
    expect(document.body.querySelectorAll('tbody tr')).toHaveLength(3);
    expect(latest!.rules[0].builder, 'rule C took the edit').toMatchObject({ words: ['OVAL', 'ELLIPSE'] });
    expect(latest!.rules[1].builder, 'rule A is untouched').toEqual(row.derivation_rules[0].builder);
    expect(latest!.rules[2].builder, 'rule B is untouched').toEqual(row.derivation_rules[1].builder);
  });
});
