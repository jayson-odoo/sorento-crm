/**
 * AC-S1.15 - Choices and words: a data grid, one row per choice (Choice, Words
 * customers say, Products), sortable headers, inline edit, deferred remove. No
 * chips, no cards, no `_self` row, no "user"/"Seed" badge, no code name (D13;
 * owner ruling 27 Sep 2026, "this should be tabulated with data grid").
 */
import React, { Profiler, useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn(), message: vi.fn(), dismiss: vi.fn() },
}));

const createPendingAction = vi.fn().mockResolvedValue({
  id: 'pa-1',
  action_key: 'spec_value.remove',
  entity_type: 'spec_value',
  entity_id: 'finish',
  commit_at: new Date(Date.now() + 5000).toISOString(),
  window_seconds: 5,
});
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: (...args: unknown[]) => createPendingAction(...args),
  cancelPendingAction: vi.fn().mockResolvedValue({}),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

/** The dropdown-menu stub renders children flat - Radix's own portal timing is not
 *  what this suite is testing (established pattern, see PackingListsList.test.tsx). */
type MenuSlotProps = { children?: React.ReactNode };
type MenuItemProps = MenuSlotProps & { onClick?: () => void; variant?: string };

vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: MenuSlotProps) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: MenuSlotProps) => <>{children}</>,
  DropdownMenuContent: ({ children }: MenuSlotProps) => <div>{children}</div>,
  DropdownMenuItem: ({ children, onClick }: MenuItemProps) => (
    <button type="button" onClick={onClick}>
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
import { projectSpecKeyDraft, type SpecKeyDraft } from '../../hooks/useSpecKeyRecord';
import type { SpecRegistryKey } from '../../types/productSpec.types';

function finishOrColour(overrides: Partial<SpecRegistryKey> = {}): SpecRegistryKey {
  return {
    spec_key: 'finish',
    label: 'Finish or colour',
    data_type: 'enum',
    unit: null,
    allowed_values: ['chrome', 'rose_gold'],
    synonyms: { chrome: ['chrome', 'silver'], rose_gold: ['rose gold'], _self: ['finish'] },
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

function EditHarness({
  row,
  onDraftChange,
}: {
  row: SpecRegistryKey;
  onDraftChange?: (draft: SpecKeyDraft) => void;
}) {
  const [draft, setDraftState] = useState<SpecKeyDraft>(() => projectSpecKeyDraft(row));
  return (
    <ValuesAndWordsTab
      row={row}
      mode="edit"
      draft={draft}
      setDraft={(updater) =>
        setDraftState((current) => {
          const next = updater(current);
          onDraftChange?.(next);
          return next;
        })
      }
      onEnterEdit={() => {}}
    />
  );
}

describe('ValuesAndWordsTab - a data grid, never chips or cards (AC-S1.15)', () => {
  it('renders Choice, Words customers say and Products as column headers', () => {
    render(withClient(<ValuesAndWordsTab row={finishOrColour()} mode="view" draft={null} setDraft={() => {}} onEnterEdit={() => {}} />));

    expect(screen.getByText('Choice')).toBeInTheDocument();
    expect(screen.getByText('Words customers say')).toBeInTheDocument();
    expect(screen.getByText('Products')).toBeInTheDocument();
    expect(screen.getByText('Chrome')).toBeInTheDocument();
    expect(screen.getByText('Rose gold')).toBeInTheDocument();
  });

  it('never renders _self as a choice row', () => {
    render(withClient(<ValuesAndWordsTab row={finishOrColour()} mode="view" draft={null} setDraft={() => {}} onEnterEdit={() => {}} />));

    expect(screen.queryByText('_self')).not.toBeInTheDocument();
  });

  it('renders no chip, no card, no user/Seed badge', () => {
    render(withClient(<ValuesAndWordsTab row={finishOrColour({ source: 'user' })} mode="view" draft={null} setDraft={() => {}} onEnterEdit={() => {}} />));

    expect(screen.queryByText('User')).not.toBeInTheDocument();
    expect(screen.queryByText('Seed')).not.toBeInTheDocument();
  });
});

describe('ValuesAndWordsTab - inline edit (edit mode, AC-S1.15)', () => {
  it('clicking the Words cell edits it as a comma list', () => {
    let latest: SpecKeyDraft | undefined;
    render(withClient(<EditHarness row={finishOrColour()} onDraftChange={(d) => (latest = d)} />));

    fireEvent.click(screen.getByText('chrome, silver'));
    const input = screen.getByDisplayValue('chrome, silver');
    fireEvent.change(input, { target: { value: 'chrome, silver, gm' } });
    fireEvent.blur(input);

    expect(latest?.words.chrome).toEqual(['chrome', 'silver', 'gm']);
  });

  it('Add a choice adds a row with the typed label, never a raw slug (D15)', () => {
    let latest: SpecKeyDraft | undefined;
    render(withClient(<EditHarness row={finishOrColour()} onDraftChange={(d) => (latest = d)} />));

    fireEvent.click(screen.getByRole('button', { name: 'Add a choice' }));
    const input = screen.getByPlaceholderText('a choice, e.g. Rose gold');
    fireEvent.change(input, { target: { value: 'Satin chrome' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(latest?.liveValues).toContain('satin_chrome');
    expect(latest?.valueLabels.satin_chrome).toBe('Satin chrome');
  });

  it('Remove parks spec_value.remove on the server, keyed by the spec key - not an instant delete', async () => {
    render(withClient(<EditHarness row={finishOrColour()} />));

    const chromeRow = screen.getByLabelText('Chrome actions').closest('tr')!;
    fireEvent.click(within(chromeRow).getByText('Remove'));

    await waitFor(() =>
      expect(createPendingAction).toHaveBeenCalledWith({
        actionKey: 'spec_value.remove',
        entityType: 'spec_value',
        entityId: 'finish',
        payload: { value: 'chrome' },
      }),
    );
    expect(screen.getByText(/Removing in \ds/)).toBeInTheDocument();
    // Still in the DOM, dimmed by the countdown - not gone yet.
    expect(screen.getByText('Cancel')).toBeInTheDocument();
  });
});

describe('ValuesAndWordsTab - a Number specification has no choices (review V8)', () => {
  it('points at Details instead of an add-choice CTA', () => {
    const row = finishOrColour({
      spec_key: 'capacity_oz',
      data_type: 'numeric',
      allowed_values: [],
      synonyms: { _self: ['oz'] },
    });
    render(withClient(<ValuesAndWordsTab row={row} mode="view" draft={null} setDraft={() => {}} onEnterEdit={() => {}} />));

    expect(
      screen.getByText('Numbers have no choices. Other names for this specification are on Details.'),
    ).toBeInTheDocument();
  });
});

/**
 * D1 (CRITICAL, fix round 3, agent-browser evidence) - entering/leaving edit mode,
 * or an inline word-cell edit, pegged the renderer forever with no console error:
 * `choices` (and the `words`/`droppedValues`/`valueLabels` view-mode fallbacks
 * feeding it) were rebuilt fresh on every render and fed into `useReactTable`'s
 * `data` - `getSortedRowModel`'s own recompute calls `table._autoResetPageIndex()`
 * on every miss, which sets pagination state (a fresh object even when the value
 * is unchanged) unconditionally, which React always re-renders for, which rebuilds
 * the unstable array again (`data-grid.stable-data.inventory.test.ts`'s own finding,
 * M5 run 2 - "nothing is thrown and nothing is logged").
 *
 * A `Profiler` around the tab counts commits directly, rather than a `waitFor`
 * timeout - the real bug is a synchronous microtask storm that starves the event
 * loop, so a time-based assertion could never fire either; if this ever regresses,
 * the fairest thing this test can do is hang exactly the way the browser did,
 * which is still a loud CI failure.
 */
/** A thin, controllable stand-in for the record page: real `mode`/`draft` state
 *  (the same shape `useSpecKeyRecord` holds), `test-enter-edit`/`test-cancel`
 *  buttons standing for the record page's own Edit/Cancel, and a `Profiler`
 *  around the tab under test so the count is COMMITS, not test assertions. */
function CountingHarness({
  row,
  initialMode,
  onRender,
}: {
  row: SpecRegistryKey;
  initialMode: 'view' | 'edit';
  onRender: () => void;
}) {
  const [mode, setMode] = useState<'view' | 'edit'>(initialMode);
  const [draft, setDraftState] = useState<SpecKeyDraft | null>(
    initialMode === 'edit' ? projectSpecKeyDraft(row) : null,
  );
  return (
    <div>
      <button
        type="button"
        onClick={() => {
          setMode('edit');
          setDraftState(projectSpecKeyDraft(row));
        }}
      >
        test-enter-edit
      </button>
      <button
        type="button"
        onClick={() => {
          setMode('view');
          setDraftState(null);
        }}
      >
        test-cancel
      </button>
      <Profiler id="values-and-words" onRender={onRender}>
        <ValuesAndWordsTab
          row={row}
          mode={mode}
          draft={draft}
          setDraft={(updater) => setDraftState((current) => (current ? updater(current) : current))}
          onEnterEdit={() => {}}
        />
      </Profiler>
    </div>
  );
}

describe('D1 (fix round 3) - toggling edit mode settles, never an unbounded render loop', () => {
  it('entering edit, an inline word-cell edit, and Cancel each add only a few renders', () => {
    let renderCount = 0;
    render(
      withClient(
        <CountingHarness row={finishOrColour()} initialMode="view" onRender={() => (renderCount += 1)} />,
      ),
    );
    const afterMount = renderCount;

    // Edit, pressed on the record page - this tab goes from `draft=null` to a real draft.
    fireEvent.click(screen.getByText('test-enter-edit'));
    const afterEdit = renderCount;
    expect(afterEdit - afterMount).toBeLessThan(10);

    // An inline word-cell edit, entirely inside edit mode.
    fireEvent.click(screen.getByText('chrome, silver'));
    const afterCellOpen = renderCount;
    expect(afterCellOpen - afterEdit).toBeLessThan(10);

    fireEvent.change(screen.getByDisplayValue('chrome, silver'), {
      target: { value: 'chrome, silver, gm' },
    });
    fireEvent.blur(screen.getByDisplayValue('chrome, silver, gm'));
    const afterCellCommit = renderCount;
    expect(afterCellCommit - afterCellOpen).toBeLessThan(10);

    // Cancel - back to view mode, draft dropped.
    fireEvent.click(screen.getByText('test-cancel'));
    expect(renderCount - afterCellCommit).toBeLessThan(10);
  });
});
