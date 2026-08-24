/**
 * AutomationForm - RuleBuilder gating + conditions_json payload + 422 handling.
 *
 * RuleBuilder is stubbed (exposes a "set-tree" button that emits a fixed tree).
 * The trigger catalog gives the promotion trigger a fact_source and the
 * complaint trigger none, so we can assert the builder shows only for triggers
 * that expose facts, that conditions_json travels in the payload (null with no
 * sources), that switching triggers resets the tree, and that a 422
 * {detail: string[]} renders the problems inline.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import AutomationForm from './AutomationForm';
import { AutomationRuleValidationError } from '../services/automationService';
import type { RecipientConfig } from '../types/automation.types';

const createMutateAsync = vi.fn().mockResolvedValue({});
const updateMutateAsync = vi.fn().mockResolvedValue({});

vi.mock('../hooks/useAutomations', () => ({
  useCreateAutomation: () => ({ mutateAsync: createMutateAsync, isPending: false }),
  useUpdateAutomation: () => ({ mutateAsync: updateMutateAsync, isPending: false }),
  useTriggerCatalog: () => ({
    data: {
      triggers: [
        {
          type: 'days_before_promotion_end',
          label: 'Days before promotion end',
          description: 'Fires for every active promotion…',
          config_schema: {},
          fact_sources: ['promotion'],
        },
        {
          type: 'complaint_approved',
          label: 'Complaint approved',
          description: 'Fires when a complaint is approved.',
          config_schema: {},
          fact_sources: [],
        },
      ],
    },
  }),
}));

vi.mock('../../email-templates/hooks/useEmailTemplates', () => ({
  useEmailTemplates: () => ({
    data: { data: [{ id: 'tpl-1', name: 'Promo expire', code: 'promo expire' }] },
  }),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

vi.mock('./RecipientPicker', () => ({
  default: ({
    value,
    onChange,
  }: {
    value: RecipientConfig;
    onChange: (c: RecipientConfig) => void;
  }) => (
    <button
      type="button"
      data-testid="seed-recipient"
      onClick={() => onChange({ ...value, extra_emails: ['x@example.com'] })}
    >
      seed
    </button>
  ),
}));

// Stub RuleBuilder: render the sources it received + a button that emits a tree.
const FIXED_TREE = {
  kind: 'group' as const,
  combinator: 'or' as const,
  rules: [
    {
      kind: 'condition' as const,
      fact: 'promotion.name',
      operator: 'contains' as const,
      valueKind: 'literal' as const,
      value: 'Sorento',
    },
  ],
};
vi.mock('@/components/rule-builder/RuleBuilder', () => ({
  RuleBuilder: ({
    sources,
    onChange,
  }: {
    sources: string[];
    onChange: (g: unknown) => void;
  }) => (
    <div data-testid="rule-builder" data-sources={sources.join(',')}>
      <button type="button" data-testid="set-tree" onClick={() => onChange(FIXED_TREE)}>
        set tree
      </button>
    </div>
  ),
}));

function renderForm() {
  return render(<AutomationForm open onOpenChange={vi.fn()} />);
}

beforeEach(() => {
  vi.clearAllMocks();
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.hasPointerCapture = vi.fn();
});

async function pickTemplate() {
  fireEvent.click(screen.getByText('Pick template'));
  fireEvent.click(await screen.findByText('Promo expire (promo expire)'));
}

async function fillMinimum() {
  fireEvent.change(screen.getByPlaceholderText('Promotion expiry reminder'), {
    target: { value: 'My automation' },
  });
  fireEvent.click(screen.getByTestId('seed-recipient'));
  await pickTemplate();
}

describe('AutomationForm - RuleBuilder gating', () => {
  it('shows the builder for the promotion trigger (has fact_sources)', () => {
    renderForm();
    expect(screen.getByTestId('rule-builder')).toBeInTheDocument();
    expect(screen.getByTestId('rule-builder').getAttribute('data-sources')).toBe('promotion');
  });

  it('hides the builder for a trigger with no fact_sources', async () => {
    renderForm();
    expect(screen.getByTestId('rule-builder')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Days before promotion end'));
    fireEvent.click(await screen.findByText('Complaint approved'));
    await waitFor(() => expect(screen.queryByTestId('rule-builder')).not.toBeInTheDocument());
  });

  it('includes conditions_json in the payload when a tree is set', async () => {
    renderForm();
    await fillMinimum();
    fireEvent.click(screen.getByTestId('set-tree'));

    fireEvent.click(screen.getByRole('button', { name: /create automation/i }));
    await waitFor(() => expect(createMutateAsync).toHaveBeenCalledTimes(1));
    expect(createMutateAsync.mock.calls[0][0].conditions_json).toEqual(FIXED_TREE);
  });

  it('sends conditions_json=null for a trigger with no fact_sources', async () => {
    renderForm();
    // Switch to the complaint trigger (no fact sources).
    fireEvent.click(screen.getByText('Days before promotion end'));
    fireEvent.click(await screen.findByText('Complaint approved'));
    await fillMinimum();

    fireEvent.click(screen.getByRole('button', { name: /create automation/i }));
    await waitFor(() => expect(createMutateAsync).toHaveBeenCalledTimes(1));
    expect(createMutateAsync.mock.calls[0][0].conditions_json).toBeNull();
  });

  it('resets the tree when the trigger changes', async () => {
    renderForm();
    // Set a tree on the promotion trigger…
    fireEvent.click(screen.getByTestId('set-tree'));
    // …switch to complaint (resets)…
    fireEvent.click(screen.getByText('Days before promotion end'));
    fireEvent.click(await screen.findByText('Complaint approved'));
    await fillMinimum();

    fireEvent.click(screen.getByRole('button', { name: /create automation/i }));
    await waitFor(() => expect(createMutateAsync).toHaveBeenCalledTimes(1));
    // Even though a tree was set earlier, the trigger change cleared it.
    expect(createMutateAsync.mock.calls[0][0].conditions_json).toBeNull();
  });

  it('renders a 422 {detail: string[]} inline as problems', async () => {
    createMutateAsync.mockRejectedValueOnce(
      new AutomationRuleValidationError(['Unknown field foo', 'Operator not allowed']),
    );
    renderForm();
    await fillMinimum();
    fireEvent.click(screen.getByTestId('set-tree'));

    fireEvent.click(screen.getByRole('button', { name: /create automation/i }));
    expect(await screen.findByText('Unknown field foo')).toBeInTheDocument();
    expect(screen.getByText('Operator not allowed')).toBeInTheDocument();
  });
});
