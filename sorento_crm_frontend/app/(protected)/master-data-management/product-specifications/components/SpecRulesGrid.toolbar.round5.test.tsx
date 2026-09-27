/**
 * Fix round 5 (owner ruling 27 Sep 13:20 MYT: "the add new rule is too low ady,
 * should be here"): Add a rule sits at the top right of the rules grid, on the
 * toolbar row above the column header, in read mode and edit mode. The grid
 * footer keeps only "N rules.". Choices and words gets the same placement for
 * Add a choice.
 */
import React, { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn(), message: vi.fn(), dismiss: vi.fn() },
}));

vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
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

vi.mock('../services/productSpecService', () => ({
  getSpecKeyProducts: vi.fn().mockResolvedValue({
    spec_key: 'shape',
    label: 'Shape',
    total: 0,
    by_value: [],
    by_class: [],
    by_source: [],
    products: [],
  }),
}));

vi.mock('../hooks/useSpecTryIt', () => ({
  useSpecTryIt: () => ({ result: null, loading: false, error: null }),
}));
vi.mock('./SpecTryItPanel', () => ({ default: () => null }));
vi.mock('./SpecRuleModal', () => ({
  SpecRuleModal: ({ open }: { open: boolean }) => (open ? <div role="dialog">Add a rule form</div> : null),
}));

import { SpecRulesGrid } from './SpecRulesGrid';
import { RulesTab } from './record/RulesTab';
import { ValuesAndWordsTab } from './record/ValuesAndWordsTab';
import { projectSpecKeyDraft, type SpecKeyDraft } from '../hooks/useSpecKeyRecord';
import type { SpecDerivationRule, SpecRegistryKey } from '../types/productSpec.types';

function withClient(children: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const ROUND: SpecDerivationRule = {
  builder: { kind: 'words', look_in: 'name', words: ['ROUND'], value: 'round' },
  _uid: 'r0',
};
const SQUARE: SpecDerivationRule = {
  builder: { kind: 'words', look_in: 'name', words: ['SQUARE'], value: 'square' },
  _uid: 'r1',
};

function shape(overrides: Partial<SpecRegistryKey> = {}): SpecRegistryKey {
  const stored = [ROUND, SQUARE].map(({ builder }) => ({ builder }));
  return {
    spec_key: 'shape',
    label: 'Shape',
    data_type: 'enum',
    unit: null,
    allowed_values: ['round', 'square'],
    excluded_values: [],
    user_values: [],
    suppressed_values: [],
    value_weights: {},
    derivation_rules: stored,
    effective_rules: stored,
    synonyms: { round: ['round'], square: ['square'] },
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

/** The toolbar row precedes the first column header in document order. */
function expectAboveHeader(el: HTMLElement) {
  const header = screen.getAllByRole('columnheader')[0];
  expect(el.compareDocumentPosition(header) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
}

describe.each(['view', 'edit'] as const)('SpecRulesGrid in %s mode - Add a rule in the toolbar', (mode) => {
  it('renders Add a rule in the toolbar row above the column header, and calls onAdd', () => {
    const onAdd = vi.fn();
    render(
      withClient(
        <SpecRulesGrid
          rules={[ROUND, SQUARE]}
          spec={shape()}
          registry={[]}
          mode={mode}
          onChange={vi.fn()}
          onEdit={vi.fn()}
          onAdd={onAdd}
        />,
      ),
    );

    const toolbar = screen.getByTestId('rules-grid-toolbar');
    const add = within(toolbar).getByRole('button', { name: 'Add a rule' });
    expectAboveHeader(toolbar);
    expect(screen.getAllByRole('button', { name: 'Add a rule' })).toHaveLength(1);

    fireEvent.click(add);
    expect(onAdd).toHaveBeenCalledTimes(1);
  });

  it('keeps only the count in the footer', () => {
    render(
      withClient(
        <SpecRulesGrid
          rules={[ROUND, SQUARE]}
          spec={shape()}
          registry={[]}
          mode={mode}
          onChange={vi.fn()}
          onEdit={vi.fn()}
          onAdd={vi.fn()}
        />,
      ),
    );

    const footer = screen.getByTestId('rules-grid-footer');
    expect(footer).toHaveTextContent(/^2 rules\.$/);
    expect(within(footer).queryByRole('button')).not.toBeInTheDocument();
  });
});

describe('RulesTab - Add a rule from read mode', () => {
  it('enters edit mode and opens the rule form', () => {
    function Harness() {
      const row = shape();
      const [mode, setMode] = useState<'view' | 'edit'>('view');
      const [draft, setDraft] = useState<SpecKeyDraft | null>(null);
      return (
        <RulesTab
          row={row}
          registry={[row]}
          mode={mode}
          draft={draft}
          setDraft={(updater) => setDraft((d) => updater(d ?? projectSpecKeyDraft(row)))}
          onEnterEdit={() => {
            setDraft(projectSpecKeyDraft(row));
            setMode('edit');
          }}
        />
      );
    }
    render(withClient(<Harness />));

    fireEvent.click(
      within(screen.getByTestId('rules-grid-toolbar')).getByRole('button', { name: 'Add a rule' }),
    );
    expect(screen.getByRole('dialog')).toHaveTextContent('Add a rule form');
  });
});

describe.each(['view', 'edit'] as const)('ValuesAndWordsTab in %s mode - Add a choice in the toolbar', (mode) => {
  it('renders Add a choice in the toolbar row above the column header', () => {
    const row = shape();
    const onEnterEdit = vi.fn();
    render(
      withClient(
        <ValuesAndWordsTab
          row={row}
          mode={mode}
          draft={mode === 'edit' ? projectSpecKeyDraft(row) : null}
          setDraft={() => {}}
          onEnterEdit={onEnterEdit}
        />,
      ),
    );

    const toolbar = screen.getByTestId('choices-grid-toolbar');
    const add = within(toolbar).getByRole('button', { name: 'Add a choice' });
    expectAboveHeader(toolbar);
    expect(screen.queryByText('+ Add a choice')).not.toBeInTheDocument();

    fireEvent.click(add);
    if (mode === 'view') expect(onEnterEdit).toHaveBeenCalledTimes(1);
    else expect(within(toolbar).getByRole('textbox', { name: 'New choice' })).toBeInTheDocument();
  });
});
