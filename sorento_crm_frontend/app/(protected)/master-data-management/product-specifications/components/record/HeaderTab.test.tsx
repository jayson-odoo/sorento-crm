/**
 * B.2, D15b - the Header tab: Label, Unit, Active, and (numeric keys only) the
 * cap moved here from Values and words. Same field labels in both modes; edit
 * swaps each for its input in place.
 */
import { useState } from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { HeaderTab } from './HeaderTab';
import { projectSpecKeyDraft, type SpecKeyDraft } from '../../hooks/useSpecKeyRecord';
import type { SpecRegistryKey } from '../../types/productSpec.types';

function baseRow(overrides: Partial<SpecRegistryKey> = {}): SpecRegistryKey {
  return {
    spec_key: 'finish',
    label: 'Finish',
    data_type: 'enum',
    unit: null,
    allowed_values: ['chrome'],
    synonyms: { chrome: ['chrome'] },
    excluded_values: [],
    user_values: [],
    suppressed_values: [],
    value_weights: {},
    derivation_rules: [],
    effective_rules: [],
    rules_are_default: true,
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

function EditHarness({
  row,
  onDraftChange,
}: {
  row: SpecRegistryKey;
  onDraftChange?: (draft: SpecKeyDraft) => void;
}) {
  const [draft, setDraftState] = useState<SpecKeyDraft>(() => projectSpecKeyDraft(row));
  return (
    <HeaderTab
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
    />
  );
}

describe('HeaderTab - same field labels in both modes', () => {
  it('renders Label, Unit and Active in view mode', () => {
    const row = baseRow({ is_active: false, unit: 'mm' });
    render(<HeaderTab row={row} mode="view" draft={null} setDraft={() => {}} />);

    expect(screen.getByText('Label')).toBeInTheDocument();
    expect(screen.getByText('Unit')).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
    expect(screen.getByText('Finish')).toBeInTheDocument();
    expect(screen.getByText('mm')).toBeInTheDocument();
  });

  it('renders the same three labels in edit mode, as inputs', () => {
    render(<EditHarness row={baseRow({ unit: 'mm' })} />);

    expect(screen.getByText('Label')).toBeInTheDocument();
    expect(screen.getByText('Unit')).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
    expect(screen.getByLabelText('Label')).toBeInTheDocument();
    expect(screen.getByLabelText('Unit')).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'Active' })).toBeInTheDocument();
  });
});

describe('HeaderTab - "Ignore values above" (numeric keys only)', () => {
  it('shows the stored cap on a numeric key, in view mode', () => {
    const row = baseRow({ spec_key: 'dim_height', data_type: 'numeric', unit: 'mm', max_value: 5000 });
    render(<HeaderTab row={row} mode="view" draft={null} setDraft={() => {}} />);

    expect(screen.getByText('Ignore values above (mm)')).toBeInTheDocument();
    expect(screen.getByText('5000 mm')).toBeInTheDocument();
  });

  it('shows No cap when unset', () => {
    const row = baseRow({ spec_key: 'dim_height', data_type: 'numeric', unit: 'mm', max_value: null });
    render(<HeaderTab row={row} mode="view" draft={null} setDraft={() => {}} />);

    expect(screen.getByText('No cap')).toBeInTheDocument();
  });

  it('is absent on a non-numeric key in either mode', () => {
    const row = baseRow();
    render(<HeaderTab row={row} mode="view" draft={null} setDraft={() => {}} />);
    expect(screen.queryByText(/Ignore values above/)).not.toBeInTheDocument();
  });
});

describe('HeaderTab - editing the draft', () => {
  it('typing a label feeds the draft', () => {
    let latest: SpecKeyDraft | undefined;
    render(<EditHarness row={baseRow()} onDraftChange={(draft) => (latest = draft)} />);

    fireEvent.change(screen.getByLabelText('Label'), { target: { value: 'Finish colour' } });

    expect(latest?.label).toBe('Finish colour');
  });

  it('toggling Active in edit mode changes the draft', () => {
    let latest: SpecKeyDraft | undefined;
    render(
      <EditHarness
        row={baseRow({ is_active: true })}
        onDraftChange={(draft) => (latest = draft)}
      />,
    );

    const toggle = screen.getByRole('switch', { name: 'Active' });
    expect(toggle).toHaveAttribute('aria-checked', 'true');

    fireEvent.click(toggle);

    expect(latest?.isActive).toBe(false);
  });
});
