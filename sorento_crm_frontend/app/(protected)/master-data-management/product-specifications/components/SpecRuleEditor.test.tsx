/**
 * AC-C.1 (sentences, one per kind), AC-C.2 (Advanced shows the compiled pattern; Edit
 * pattern drops the builder), AC-C.3 (a shipped row is an ordinary row with a tag).
 * `builderSentence` renders the row's TEXT; this only exercises what wires it in - the
 * kind menu, the blanks, the Advanced pane and the remove button.
 */
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import SpecRuleEditor from './SpecRuleEditor';
import type { SpecDerivationRule } from '../types/productSpec.types';
import { compileBuilder } from '../lib/ruleSentence';

// B2's test needs to actually CHANGE the kind select, which the real
// SearchableSelect (Radix popover + cmdk) is non-deterministic to drive in jsdom -
// stood in as a native `<select>`, the same swap `PlanRowPanel.test.tsx` and
// `AddEditPolicyModal.test.tsx` already use. Every other test in this file only
// renders the row (never opens a dropdown), so the swap changes nothing for them.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
  }: {
    value: string;
    onChange: (v: string) => void;
    options: { value: string; label: string }[];
  }) => (
    <select value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

function ruleFor(
  builder: SpecDerivationRule['builder'],
  extra: Partial<SpecDerivationRule> = {},
): SpecDerivationRule {
  return {
    _uid: `r-${builder?.kind ?? 'pattern'}`,
    ...(builder
      ? { builder, ...compileBuilder(builder) }
      : { match: 'regex', pattern: '', capture: 1 }),
    ...extra,
  } as SpecDerivationRule;
}

describe('every sentence kind renders its blanks', () => {
  it('number after a word', () => {
    render(
      <SpecRuleEditor
        rules={[ruleFor({ kind: 'number_after', word: 'L' })]}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText('Number after the word')).toBeInTheDocument();
    expect(screen.getByDisplayValue('L')).toBeInTheDocument();
  });

  it('number before a word', () => {
    render(
      <SpecRuleEditor
        rules={[ruleFor({ kind: 'number_before', word: 'MM' })]}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText('Number before')).toBeInTheDocument();
    expect(screen.getByDisplayValue('MM')).toBeInTheDocument();
  });

  it('number between two words', () => {
    const { container } = render(
      <SpecRuleEditor
        rules={[ruleFor({ kind: 'number_between', from: 'S-TRAP', to: 'MM' })]}
        onChange={vi.fn()}
      />,
    );
    expect(container.textContent).toContain('Number between');
    expect(container.textContent).toContain('and');
    expect(screen.getByDisplayValue('S-TRAP')).toBeInTheDocument();
    expect(screen.getByDisplayValue('MM')).toBeInTheDocument();
  });

  it('text contains', () => {
    render(
      <SpecRuleEditor
        rules={[
          ruleFor({ kind: 'text_contains', word: 'RIMLESS', value: 'yes' }),
        ]}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText('Text contains')).toBeInTheDocument();
    expect(screen.getByDisplayValue('RIMLESS')).toBeInTheDocument();
    expect(screen.getByDisplayValue('yes')).toBeInTheDocument();
  });

  it('text ends with', () => {
    render(
      <SpecRuleEditor
        rules={[
          ruleFor({
            kind: 'text_ends_with',
            word: 'SQUATTING PAN',
            value: 'Squatting Pan',
          }),
        ]}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText('Text ends with')).toBeInTheDocument();
  });

  it('word is present', () => {
    const { container } = render(
      <SpecRuleEditor
        rules={[ruleFor({ kind: 'word_present', word: 'THERMOSTATIC' })]}
        onChange={vi.fn()}
      />,
    );
    expect(container.textContent).toContain('Word');
    expect(container.textContent).toContain('is present → yes');
    expect(screen.getByDisplayValue('THERMOSTATIC')).toBeInTheDocument();
  });

  it('code contains', () => {
    render(
      <SpecRuleEditor
        rules={[
          ruleFor({
            kind: 'code_contains',
            word: 'SRTSC',
            value: 'Seat Cover',
          }),
        ]}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText('Code contains')).toBeInTheDocument();
  });

  it('code starts with', () => {
    render(
      <SpecRuleEditor
        rules={[
          ruleFor({ kind: 'code_starts_with', word: 'SRT', value: 'Sorento' }),
        ]}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText('Code starts with')).toBeInTheDocument();
  });

  it('code ends with', () => {
    render(
      <SpecRuleEditor
        rules={[ruleFor({ kind: 'code_ends_with', word: 'UF', value: 'uf' })]}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText('Code ends with')).toBeInTheDocument();
  });

  it("from the product's own field", () => {
    render(
      <SpecRuleEditor
        rules={[ruleFor({ kind: 'from_field', field: 'brand' })]}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText('From')).toBeInTheDocument();
  });

  it('size from L x W x H', () => {
    const { container } = render(
      <SpecRuleEditor
        rules={[ruleFor({ kind: 'size_triple', position: 1 })]}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText('L x W x H')).toBeInTheDocument();
    expect(container.textContent).toContain('number');
  });

  it('product name head', () => {
    render(
      <SpecRuleEditor
        rules={[ruleFor({ kind: 'name_head' })]}
        onChange={vi.fn()}
      />,
    );
    expect(
      screen.getByText(
        'Product name head (text before the first bracket or WITH)',
      ),
    ).toBeInTheDocument();
  });
});

describe('a row without a builder', () => {
  it('renders as a pattern, the only place raw regex shows (AC-C.1)', () => {
    const { container } = render(
      <SpecRuleEditor
        rules={[
          { _uid: 'p1', match: 'regex', pattern: '(\\d+)MM', capture: 1 },
        ]}
        onChange={vi.fn()}
      />,
    );
    expect(container.textContent).toContain('Pattern');
    expect(container.textContent).toContain('capture the');
    expect(container.textContent).toContain('number');
    expect(screen.getByDisplayValue('(\\d+)MM')).toBeInTheDocument();
  });
});

describe('Advanced (AC-C.2)', () => {
  it('shows the compiled pattern read-only', () => {
    render(
      <SpecRuleEditor
        rules={[ruleFor({ kind: 'number_after', word: 'L' })]}
        onChange={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /Advanced/ }));
    // The exact compiled pattern (compileBuilder's own output), not a re-derivation of it.
    expect(
      screen.getByText((content) => content.includes('\\bL\\s*(\\d+')),
    ).toBeInTheDocument();
  });

  it('"Edit pattern" drops the builder, turning the row into a pattern row', () => {
    const onChange = vi.fn();
    render(
      <SpecRuleEditor
        rules={[ruleFor({ kind: 'number_after', word: 'L' })]}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /Advanced/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Edit pattern' }));

    const [updated] = onChange.mock.calls.at(-1)![0] as SpecDerivationRule[];
    expect(updated.builder).toBeUndefined();
    // What runs is unchanged - only the builder is gone.
    expect(updated.match).toBe('regex');
    expect(updated.pattern).toBe('\\bL\\s*(\\d+(?:\\.\\d+)?)');
  });
});

describe('shipped rows (AC-C.3)', () => {
  it('carry a tag and remove exactly like a user row', () => {
    const onChange = vi.fn();
    render(
      <SpecRuleEditor
        rules={[
          ruleFor(
            { kind: 'from_field', field: 'column:dimensions_length' },
            { shipped: true },
          ),
        ]}
        onChange={onChange}
      />,
    );
    expect(screen.getByText('shipped')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Remove rule 1' }));
    expect(onChange).toHaveBeenCalledWith([]);
  });
});

describe('try-it reads render into the rows (AC-B.3)', () => {
  it('shows what each row read, and marks the winner', () => {
    render(
      <SpecRuleEditor
        rules={[
          ruleFor({ kind: 'number_before', word: 'MM' }),
          ruleFor({ kind: 'word_present', word: 'RIMLESS' }),
        ]}
        onChange={vi.fn()}
        reads={[
          { index: 0, value: 800, evidence: '(800MM)' },
          { index: 1, value: null, evidence: null },
        ]}
        winnerIndex={0}
      />,
    );
    expect(screen.getByText('800 from `(800MM)`')).toBeInTheDocument();
    expect(screen.getByText('nothing')).toBeInTheDocument();
    expect(screen.getByText('winner')).toBeInTheDocument();
  });

  it('renders no read line at all when no try-it source is picked', () => {
    render(
      <SpecRuleEditor
        rules={[ruleFor({ kind: 'number_before', word: 'MM' })]}
        onChange={vi.fn()}
      />,
    );
    expect(screen.queryByText(/^Reads:/)).not.toBeInTheDocument();
  });

  it('a capped-and-dropped read shows why, not a bare "nothing" (nit)', () => {
    render(
      <SpecRuleEditor
        rules={[ruleFor({ kind: 'number_before', word: 'MM' })]}
        onChange={vi.fn()}
        reads={[
          {
            index: 0,
            value: null,
            evidence: '540180 from (540180MM) (above 5000, ignored)',
          },
        ]}
        winnerIndex={null}
      />,
    );
    expect(
      screen.getByText('540180 from (540180MM) (above 5000, ignored)'),
    ).toBeInTheDocument();
    expect(screen.queryByText('nothing')).not.toBeInTheDocument();
  });
});

describe("changing a rule's kind (B2)", () => {
  it('changing Text contains -> Number after a word drops value', () => {
    const onChange = vi.fn();
    render(
      <SpecRuleEditor
        rules={[
          ruleFor({ kind: 'text_contains', word: 'PP SEAT', value: 'PP' }),
        ]}
        onChange={onChange}
      />,
    );

    const combos = screen.getAllByRole('combobox');
    const kindSelect = combos.find((el) =>
      within(el).queryByRole('option', { name: 'Text contains...' }),
    )!;
    fireEvent.change(kindSelect, { target: { value: 'number_after' } });

    const [updated] = onChange.mock.calls.at(-1)![0] as SpecDerivationRule[];
    expect(updated.builder).toEqual({ kind: 'number_after', word: '' });
    expect(updated.match).toBe('regex');
    expect(updated.pattern).toBe('\\b\\s*(\\d+(?:\\.\\d+)?)');
    expect(updated.capture).toBe(1);
    // The stale value from the row's previous life as `text_contains` must not
    // survive the kind change, or the server refuses the save as a builder
    // mismatch (spec_rule_builder_mismatch).
    expect(updated.value).toBeUndefined();
  });
});

describe('the source select (S6)', () => {
  it('renders a prose label for a size_text-scoped row instead of a blank select', () => {
    render(
      <SpecRuleEditor
        rules={[
          ruleFor(
            { kind: 'number_before', word: 'MM' },
            { source: 'size_text' },
          ),
        ]}
        onChange={vi.fn()}
      />,
    );
    expect(
      screen.getByText('the description, sizes only (trap span ignored)'),
    ).toBeInTheDocument();
  });

  it('renders a prose label for a class_tail-scoped row', () => {
    render(
      <SpecRuleEditor
        rules={[
          ruleFor(
            { kind: 'text_contains', word: 'TAP', value: 'Tap' },
            { source: 'class_tail' },
          ),
        ]}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText('the product name tail')).toBeInTheDocument();
  });
});
