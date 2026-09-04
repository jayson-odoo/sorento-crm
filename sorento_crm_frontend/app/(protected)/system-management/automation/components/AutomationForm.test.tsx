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
        // Mirrors the real TriggerSpec payload: the form is driven by
        // config_schema and supports_grouping, never by the trigger type
        // string, so these fixtures have to carry both.
        {
          type: 'days_before_promotion_end',
          label: 'Days before promotion end',
          description: 'Fires for every active promotion…',
          config_schema: {
            type: 'object',
            properties: {
              days_before: {
                type: 'integer',
                minimum: 0,
                default: 7,
                title: 'Days before promotion ends',
              },
            },
            required: ['days_before'],
          },
          supports_grouping: true,
        },
        {
          type: 'days_before_certificate_expiry',
          label: 'Days before certificate expiry',
          description: 'Fires for every active certificate…',
          config_schema: {
            type: 'object',
            properties: {
              days_before: {
                type: 'integer',
                minimum: 0,
                default: 30,
                title: 'Days before the certificate expires',
              },
            },
            required: ['days_before'],
          },
          supports_grouping: true,
        },
        {
          type: 'complaint_approved',
          label: 'Complaint approved',
          description: 'Fires when a complaint is approved.',
          config_schema: {},
          supports_grouping: false,
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

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

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

describe('AutomationForm - combine into one email toggle', () => {
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

describe('AutomationForm - the trigger X is settable (schema-driven)', () => {
  it('renders the days input for the CERTIFICATE trigger, labelled from its schema', async () => {
    renderForm();
    fireEvent.click(screen.getByText('Days before promotion end'));
    fireEvent.click(await screen.findByText('Days before certificate expiry'));
    expect(
      await screen.findByLabelText('Days before the certificate expires'),
    ).toBeInTheDocument();
  });

  it('adopts the new trigger default instead of carrying the old number across', async () => {
    renderForm();
    // Promotion default is 7.
    expect((screen.getByLabelText('Days before promotion ends') as HTMLInputElement).value).toBe('7');
    fireEvent.click(screen.getByText('Days before promotion end'));
    fireEvent.click(await screen.findByText('Days before certificate expiry'));
    // Certificate default is 30.
    expect(
      (await screen.findByLabelText('Days before the certificate expires') as HTMLInputElement).value,
    ).toBe('30');
  });

  it('sends the chosen X in trigger_config for the certificate trigger', async () => {
    renderForm();
    fireEvent.click(screen.getByText('Days before promotion end'));
    fireEvent.click(await screen.findByText('Days before certificate expiry'));
    fireEvent.change(await screen.findByLabelText('Days before the certificate expires'), {
      target: { value: '7' },
    });
    fireEvent.change(screen.getByPlaceholderText('Promotion expiry reminder'), {
      target: { value: 'Cert expiry reminder' },
    });
    fireEvent.click(screen.getByTestId('seed-recipient'));
    await pickTemplate();
    fireEvent.click(screen.getByRole('button', { name: /create automation/i }));

    await waitFor(() => expect(createMutateAsync).toHaveBeenCalledTimes(1));
    const payload = createMutateAsync.mock.calls[0][0];
    expect(payload.trigger_type).toBe('days_before_certificate_expiry');
    // The whole point: an empty trigger_config made the run match nothing.
    expect(payload.trigger_config).toEqual({ days_before: 7 });
  });

  it('renders no days input and posts an empty config for a trigger without one', async () => {
    renderForm();
    fireEvent.click(screen.getByText('Days before promotion end'));
    fireEvent.click(await screen.findByText('Complaint approved'));
    await waitFor(() =>
      expect(screen.queryByLabelText(/Days before/i)).not.toBeInTheDocument(),
    );
    fireEvent.change(screen.getByPlaceholderText('Promotion expiry reminder'), {
      target: { value: 'Complaint automation' },
    });
    fireEvent.click(screen.getByTestId('seed-recipient'));
    await pickTemplate();
    fireEvent.click(screen.getByRole('button', { name: /create automation/i }));

    await waitFor(() => expect(createMutateAsync).toHaveBeenCalledTimes(1));
    expect(createMutateAsync.mock.calls[0][0].trigger_config).toEqual({});
  });
});

describe('AutomationForm - editing an automation saved before X was settable', () => {
  it('falls back to that trigger\'s own default, not a hardcoded 7', async () => {
    render(
      <AutomationForm
        open
        onOpenChange={vi.fn()}
        automation={
          {
            id: 'auto-1',
            name: 'test',
            description: null,
            enabled: true,
            trigger_type: 'days_before_certificate_expiry',
            // The empty config every certificate automation was saved with.
            trigger_config: {},
            action_type: 'send_email',
            email_template_id: 'tpl-1',
            recipient_config: { user_ids: [], role_ids: [], extra_emails: [] },
            group_matches: true,
            conditions_json: null,
            schedule_type: 'manual',
            run_time: null,
            timezone: 'Asia/Kuala_Lumpur',
          } as never
        }
      />,
    );
    expect(
      (await screen.findByLabelText('Days before the certificate expires') as HTMLInputElement)
        .value,
    ).toBe('30');
  });
});
