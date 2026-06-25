import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import AutomationForm from './AutomationForm';
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
        },
        {
          type: 'complaint_approved',
          label: 'Complaint approved',
          description: 'Fires when a complaint is approved.',
          config_schema: {},
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

// Stub RecipientPicker: seed one external email on mount so validation passes,
// and keep the test focused on the grouping toggle.
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

function renderForm() {
  return render(<AutomationForm open onOpenChange={vi.fn()} />);
}

beforeEach(() => {
  vi.clearAllMocks();
  // jsdom does not implement these; Radix Select calls them on open.
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.hasPointerCapture = vi.fn();
});

async function pickTemplate() {
  fireEvent.click(screen.getByText('Pick template'));
  fireEvent.click(await screen.findByText('Promo expire (promo expire)'));
}

describe('AutomationForm — combine into one email toggle', () => {
  it('shows the toggle for the promotion-expiry trigger (default trigger)', () => {
    renderForm();
    expect(screen.getByText('Combine into one email')).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: /combine into one email/i })).toBeChecked();
  });

  it('hides the toggle for non-promotion triggers', async () => {
    renderForm();
    expect(screen.getByText('Combine into one email')).toBeInTheDocument();
    // Switch the trigger to the complaint (event-driven) trigger.
    fireEvent.click(screen.getByText('Days before promotion end'));
    fireEvent.click(await screen.findByText('Complaint approved'));
    await waitFor(() =>
      expect(screen.queryByText('Combine into one email')).not.toBeInTheDocument(),
    );
  });

  it('includes group_matches=true in the create payload by default', async () => {
    renderForm();
    fireEvent.change(screen.getByPlaceholderText('Promotion expiry reminder'), {
      target: { value: 'My promo automation' },
    });
    fireEvent.click(screen.getByTestId('seed-recipient'));
    await pickTemplate();

    fireEvent.click(screen.getByRole('button', { name: /create automation/i }));

    await waitFor(() => expect(createMutateAsync).toHaveBeenCalledTimes(1));
    const payload = createMutateAsync.mock.calls[0][0];
    expect(payload.trigger_type).toBe('days_before_promotion_end');
    expect(payload.group_matches).toBe(true);
  });

  it('sends group_matches=false when the toggle is switched off', async () => {
    renderForm();
    fireEvent.change(screen.getByPlaceholderText('Promotion expiry reminder'), {
      target: { value: 'My promo automation' },
    });
    fireEvent.click(screen.getByTestId('seed-recipient'));
    await pickTemplate();

    fireEvent.click(screen.getByRole('switch', { name: /combine into one email/i }));
    fireEvent.click(screen.getByRole('button', { name: /create automation/i }));

    await waitFor(() => expect(createMutateAsync).toHaveBeenCalledTimes(1));
    expect(createMutateAsync.mock.calls[0][0].group_matches).toBe(false);
  });
});
