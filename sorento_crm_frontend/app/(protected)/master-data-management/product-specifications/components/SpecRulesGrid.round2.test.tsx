/**
 * Review round 2 (PR #1302) on the rules grid:
 * - B-5: one Remove at a time. A second Remove while the first is counting down
 *   used to re-point the countdown at the second rule, so the server removed the
 *   first while the draft dropped the second.
 * - A rule not yet saved to the server is dropped locally: no countdown, no call.
 * - S-11: in-place edit refuses what the server would refuse, in its words.
 * - Ruling 13: a Number rule's What to find cell opens the rule modal.
 * - B-7: Try it's per-row read is a readable value, never a slug or `true`.
 * - S-13: under `sm` only Order, What to find and Value it sets stay; at 1280 the
 *   edit-mode columns fit, so the row menu is not scrolled off the right.
 */
import React from 'react';
import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn(), message: vi.fn(), dismiss: vi.fn() },
}));

const createPendingAction = vi.fn();
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: (...args: unknown[]) => createPendingAction(...args),
  cancelPendingAction: vi.fn().mockResolvedValue({}),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
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

import { SpecRulesGrid } from './SpecRulesGrid';
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

function shape(saved: SpecDerivationRule[], overrides: Partial<SpecRegistryKey> = {}): SpecRegistryKey {
  const stored = saved.map(({ builder }) => ({ builder }));
  return {
    spec_key: 'shape',
    label: 'Shape',
    data_type: 'enum',
    unit: null,
    allowed_values: ['round', 'square', 'rose_gold'],
    excluded_values: [],
    user_values: [],
    suppressed_values: [],
    value_weights: {},
    derivation_rules: stored,
    effective_rules: stored,
    synonyms: {},
    value_labels: { rose_gold: 'Rose gold' },
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

function renderGrid(props: Partial<React.ComponentProps<typeof SpecRulesGrid>> = {}) {
  const onChange = vi.fn();
  const onEdit = vi.fn();
  const rules = props.rules ?? [ROUND, SQUARE];
  const utils = render(
    withClient(
      <SpecRulesGrid
        rules={rules}
        spec={shape([ROUND, SQUARE])}
        registry={[]}
        mode="edit"
        onChange={onChange}
        onEdit={onEdit}
        onAdd={vi.fn()}
        {...props}
      />,
    ),
  );
  return { onChange, onEdit, ...utils };
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

describe('B-5 - one Remove at a time on the rules grid', () => {
  it('while rule 1 is counting down, rule 2 cannot start a second removal', async () => {
    renderGrid();

    fireEvent.click(within(rowOf(1)).getByText('Remove'));
    await screen.findByText(/Removing in \ds/);
    expect(createPendingAction).toHaveBeenCalledTimes(1);

    const secondRemove = within(rowOf(2)).getByText('Remove');
    expect(secondRemove).toBeDisabled();
    fireEvent.click(secondRemove);
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(createPendingAction).toHaveBeenCalledTimes(1);
    // The countdown is still rule 1's.
    expect(within(screen.getByText(/Removing in \ds/).closest('tr')!).queryByLabelText('Rule 2 actions')).toBeNull();
  });
});

describe('A rule not yet saved is dropped locally (ruling 13 challenge)', () => {
  it('Remove on a draft-only rule drops it at once, with no countdown and no server call', async () => {
    const draftOnly: SpecDerivationRule = {
      builder: { kind: 'words', look_in: 'name', words: ['OVAL'], value: 'round' },
      _uid: 'new-9',
    };
    const { onChange } = renderGrid({ rules: [ROUND, draftOnly] });

    fireEvent.click(within(rowOf(2)).getByText('Remove'));

    expect(onChange).toHaveBeenCalledWith([ROUND]);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(createPendingAction).not.toHaveBeenCalled();
    expect(screen.queryByText(/Removing in/)).toBeNull();
  });
});

describe('S-11 - in-place edit refuses what the server refuses, in its words', () => {
  function openWordsCell(rowNumber: number, text: string) {
    const row = rowOf(rowNumber);
    fireEvent.click(within(row).getByText(text));
    fireEvent.click(within(rowOf(rowNumber)).getByRole('combobox'));
  }
  function typeAndCreate(word: string) {
    fireEvent.change(screen.getByPlaceholderText('Search...'), { target: { value: word } });
    fireEvent.click(document.body.querySelector('[data-slot="searchable-multi-select-create"]')!);
  }

  it('"(" alone is refused as a word to find: it needs a letter or a number (S-R2, round 3)', () => {
    const { onChange } = renderGrid();
    openWordsCell(1, 'ROUND');
    typeAndCreate('(');

    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent('Rule 1: each word needs a letter or a number.');
  });

  it('a word with a letter in it is accepted in place', () => {
    const { onChange } = renderGrid();
    openWordsCell(1, 'ROUND');
    typeAndCreate('(R)');

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('taking away the only word is refused: "Rule 1: add at least one word to find."', () => {
    const { onChange } = renderGrid();
    openWordsCell(1, 'ROUND');
    fireEvent.click(screen.getByRole('option', { name: 'ROUND' }));

    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent('Rule 1: add at least one word to find.');
  });

  it.each([
    ['...', 'Rule 1: each word needs more than dots and dashes.'],
    ['-', 'Rule 1: each word needs more than dots and dashes.'],
    ['A ... B ... C', 'Rule 1: use at most one ... in a phrase.'],
    ['X'.repeat(61), 'Rule 1: keep each word to 60 characters or fewer.'],
  ])('adding %j is refused with the server wording', (word, message) => {
    const { onChange } = renderGrid();
    openWordsCell(1, 'ROUND');
    typeAndCreate(word);

    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent(message);
  });

  it('a 21st word is refused: "Rule 1: use at most 20 words in a list."', () => {
    const twenty = Array.from({ length: 20 }, (_, i) => `W${i}`);
    const full: SpecDerivationRule = {
      builder: { kind: 'words', look_in: 'name', words: twenty, value: 'round' },
      _uid: 'r0',
    };
    const { onChange } = renderGrid({ rules: [full] });
    openWordsCell(1, twenty.join(', '));
    typeAndCreate('W20');

    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent('Rule 1: use at most 20 words in a list.');
  });

  it('a Code rule with no text left is refused in the Code wording', () => {
    const code: SpecDerivationRule = {
      builder: { kind: 'code', code_match: 'ends_with', texts: ['-RG'], value: 'round' },
      _uid: 'r0',
    };
    const { onChange } = renderGrid({ rules: [code] });
    openWordsCell(1, 'Ends with: -RG');
    fireEvent.click(screen.getByRole('option', { name: '-RG' }));

    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent('Rule 1: add at least one piece of code to find.');
  });

  it('a valid added word still patches the rule', () => {
    const { onChange } = renderGrid();
    openWordsCell(1, 'ROUND');
    typeAndCreate('CIRCLE');

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange.mock.calls[0][0][0].builder.words).toEqual(['ROUND', 'CIRCLE']);
    expect(screen.queryByRole('alert')).toBeNull();
  });
});

describe('Ruling 13 - a Number rule\'s What to find cell opens the rule modal', () => {
  it('clicking it calls onEdit with that rule\'s index', () => {
    const number: SpecDerivationRule = {
      builder: { kind: 'number', look_in: 'any', before: ['OZ'] },
      _uid: 'r1',
    };
    const { onEdit } = renderGrid({ rules: [ROUND, number] });

    const cell = within(rowOf(2)).getByText('Before: OZ').closest('button')!;
    expect(cell).not.toBeDisabled();
    fireEvent.click(cell);

    expect(onEdit).toHaveBeenCalledWith(1);
  });
});

describe('B-7 - Try it reads render as readable values', () => {
  it('a slug reads through the value label, a boolean as Yes', () => {
    const rose: SpecDerivationRule = {
      builder: { kind: 'words', look_in: 'name', words: ['ROSE GOLD'], value: 'rose_gold' },
    };
    render(
      withClient(
        <SpecRulesGrid
          rules={[rose, ROUND]}
          spec={shape([rose, ROUND])}
          registry={[]}
          mode="view"
          onChange={vi.fn()}
          onEdit={vi.fn()}
          onAdd={vi.fn()}
          reads={[
            { index: 0, value: 'rose_gold', evidence: 'ROSE GOLD' },
            { index: 1, value: true, evidence: 'ROUND' },
          ]}
          winnerIndex={0}
        />,
      ),
    );

    expect(screen.getByText('Reads: Rose gold')).toBeInTheDocument();
    expect(screen.getByText('Reads: Yes')).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/\w_\w/);
    expect(document.body.textContent).not.toMatch(/Reads: true/);
  });
});

describe('S-13 - the grid fits at 375 and at 1280', () => {
  const realMatchMedia = window.matchMedia;
  afterEach(() => {
    window.matchMedia = realMatchMedia;
  });

  it('under sm only Order, What to find and Value it sets stay', () => {
    window.matchMedia = ((query: string) => ({
      matches: query.includes('max-width: 639px') || query.includes('prefers-reduced-motion'),
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    })) as typeof window.matchMedia;
    renderGrid();

    const headers = Array.from(document.body.querySelectorAll('thead th')).map((th) => th.textContent ?? '');
    expect(headers.some((h) => h.includes('Order'))).toBe(true);
    expect(headers.some((h) => h.includes('What to find'))).toBe(true);
    expect(headers.some((h) => h.includes('Value it sets'))).toBe(true);
    expect(headers.some((h) => h.includes('Where to look'))).toBe(false);
    expect(headers.some((h) => h.includes('Kind'))).toBe(false);
    expect(headers.some((h) => h.includes('Only when'))).toBe(false);
  });

  it('in edit mode at desktop width every column, the row menu included, fits in 880px', async () => {
    renderGrid();
    await waitFor(() => expect(document.body.querySelector('[data-slot="data-grid-table"]')).not.toBeNull());
    const table = document.body.querySelector<HTMLTableElement>('[data-slot="data-grid-table"]')!;
    const minWidth = parseInt(table.style.minWidth, 10);
    expect(minWidth).toBeGreaterThan(0);
    expect(minWidth).toBeLessThanOrEqual(880);
  });
});
