/**
 * Review round 2 (PR #1302) on Choices and words:
 * - B-6: removing a built-in choice commits as a suppression. The row goes, and
 *   the next Save still sends it in `suppressed_values`; it used to stay on the
 *   grid and be taken OUT of the suppression list, so Save brought it back.
 * - B-5: one Remove at a time.
 * - A choice added in this sitting is dropped locally: no countdown, no call.
 * - S-5: taking a built-in word out of a choice's words (or renaming it) keeps it
 *   taken away after Save.
 */
import React, { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';
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

vi.mock('../../services/productSpecService', () => ({
  getSpecKeyProducts: vi.fn().mockResolvedValue({
    spec_key: 'finish',
    label: 'Finish or colour',
    total: 0,
    by_value: [],
    by_class: [],
    by_source: [],
    products: [],
  }),
}));

import { ValuesAndWordsTab } from './ValuesAndWordsTab';
import { buildPatchBody, projectSpecKeyDraft, type SpecKeyDraft } from '../../hooks/useSpecKeyRecord';
import type { SpecRegistryKey } from '../../types/productSpec.types';

function finishOrColour(overrides: Partial<SpecRegistryKey> = {}): SpecRegistryKey {
  return {
    spec_key: 'finish',
    label: 'Finish or colour',
    data_type: 'enum',
    unit: null,
    allowed_values: ['chrome', 'rose_gold'],
    synonyms: { chrome: ['chrome', 'silver'], rose_gold: ['rose gold'] },
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
    ...overrides,
  } as SpecRegistryKey;
}

function withClient(children: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

let latest: SpecKeyDraft | null = null;
function EditHarness({ row }: { row: SpecRegistryKey }) {
  const [draft, setDraftState] = useState<SpecKeyDraft>(() => projectSpecKeyDraft(row));
  latest = draft;
  return (
    <ValuesAndWordsTab
      row={row}
      mode="edit"
      draft={draft}
      setDraft={(updater) => setDraftState((d) => updater(d))}
      onEnterEdit={() => {}}
    />
  );
}

const ACTION = {
  id: 'pa-7',
  action_key: 'spec_value.remove',
  entity_type: 'spec_value',
  entity_id: 'finish',
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

describe('B-6 - a removed built-in choice stays removed after Save', () => {
  it('the row goes, and the Save payload keeps it in suppressed_values', async () => {
    const row = finishOrColour();
    render(withClient(<EditHarness row={row} />));

    fireEvent.click(within(screen.getByLabelText('Chrome actions').closest('tr')!).getByText('Remove'));
    await screen.findByText(/Removing in \ds/);

    // The server commits: pending clears, last_outcome says so.
    current = {
      pending: null,
      last_outcome: { id: ACTION.id, action_key: ACTION.action_key, status: 'committed', ended_at: new Date().toISOString() },
    };
    // The countdown replaces the row's menu, so wait on the row itself.
    await waitFor(() => expect(screen.queryByText('Chrome')).toBeNull(), { timeout: 3000 });

    expect(buildPatchBody(row, latest!).suppressed_values).toContain('chrome');
  });

  it('view mode never lists a choice the business has taken away', () => {
    render(
      withClient(
        <ValuesAndWordsTab
          row={finishOrColour({ allowed_values: ['chrome'], suppressed_values: ['rose_gold'] })}
          mode="view"
          draft={null}
          setDraft={() => {}}
          onEnterEdit={() => {}}
        />,
      ),
    );
    expect(screen.getByText('Chrome')).toBeInTheDocument();
    expect(screen.queryByText('Rose gold')).toBeNull();
  });
});

describe('B-5 - one Remove at a time on Choices and words', () => {
  it('while Chrome is counting down, Rose gold cannot start a second removal', async () => {
    render(withClient(<EditHarness row={finishOrColour()} />));

    fireEvent.click(within(screen.getByLabelText('Chrome actions').closest('tr')!).getByText('Remove'));
    await screen.findByText(/Removing in \ds/);

    const second = within(screen.getByLabelText('Rose gold actions').closest('tr')!).getByText('Remove');
    expect(second).toBeDisabled();
    fireEvent.click(second);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(createPendingAction).toHaveBeenCalledTimes(1);
  });
});

describe('A choice added in this sitting is dropped locally', () => {
  it('Remove on it drops it with no countdown and no server call', async () => {
    render(withClient(<EditHarness row={finishOrColour()} />));

    fireEvent.click(screen.getByText('+ Add a choice'));
    const input = screen.getByPlaceholderText('a choice, e.g. Rose gold');
    fireEvent.change(input, { target: { value: 'Satin chrome' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(latest!.liveValues).toContain('satin_chrome');

    fireEvent.click(within(screen.getByLabelText('Satin chrome actions').closest('tr')!).getByText('Remove'));

    expect(latest!.liveValues).not.toContain('satin_chrome');
    expect(latest!.valueLabels.satin_chrome).toBeUndefined();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(createPendingAction).not.toHaveBeenCalled();
    expect(screen.queryByText(/Removing in/)).toBeNull();
  });
});

describe('S-5 - a built-in word taken out of a choice stays out after Save', () => {
  it('deleting "silver" from Chrome\'s words suppresses it in the Save payload', () => {
    const row = finishOrColour();
    render(withClient(<EditHarness row={row} />));

    fireEvent.click(screen.getByText('chrome, silver'));
    const input = screen.getByDisplayValue('chrome, silver');
    fireEvent.change(input, { target: { value: 'chrome' } });
    fireEvent.blur(input);

    expect(buildPatchBody(row, latest!).suppressed_synonyms.chrome).toEqual(['silver']);
  });

  it('renaming "silver" to "silvery" suppresses the built-in and adds the new word', () => {
    const row = finishOrColour();
    render(withClient(<EditHarness row={row} />));

    fireEvent.click(screen.getByText('chrome, silver'));
    const input = screen.getByDisplayValue('chrome, silver');
    fireEvent.change(input, { target: { value: 'chrome, silvery' } });
    fireEvent.blur(input);

    const body = buildPatchBody(row, latest!);
    expect(body.suppressed_synonyms.chrome).toEqual(['silver']);
    expect(body.user_synonyms.chrome).toEqual(['silvery']);
  });
});
