/**
 * AC-S1.15 - Choices and words: a data grid, one row per choice (Choice, Words
 * customers say, Products), sortable headers, inline edit, deferred remove. No
 * chips, no cards, no `_self` row, no "user"/"Seed" badge, no code name (D13;
 * owner ruling 27 Sep 2026, "this should be tabulated with data grid").
 */
import React, { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

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

    fireEvent.click(screen.getByText('+ Add a choice'));
    const input = screen.getByPlaceholderText('a choice, e.g. Rose gold');
    fireEvent.change(input, { target: { value: 'Satin chrome' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(latest?.liveValues).toContain('satin_chrome');
    expect(latest?.valueLabels.satin_chrome).toBe('Satin chrome');
  });

  it('Remove is a deferred action, not an instant delete', () => {
    render(withClient(<EditHarness row={finishOrColour()} />));

    const chromeRow = screen.getByLabelText('Chrome actions').closest('tr')!;
    fireEvent.click(within(chromeRow).getByText('Remove'));

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
