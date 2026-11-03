import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

import AutomationForm from './AutomationForm';
import type { Automation } from '../types/automation.types';

const createMutateAsync = vi.fn().mockResolvedValue({});
const updateMutateAsync = vi.fn().mockResolvedValue({});

// order_inquiry_handover is event-driven (empty config_schema) but does
// support the "combine into one email" switch here so a false group_matches
// on the fixture actually round-trips through the form instead of being
// forced to true by the trigger-doesn't-support-grouping branch - that would
// muddy why the test is red.
vi.mock('../hooks/useAutomations', () => ({
  useCreateAutomation: () => ({ mutateAsync: createMutateAsync, isPending: false }),
  useUpdateAutomation: () => ({ mutateAsync: updateMutateAsync, isPending: false }),
  useTriggerCatalog: () => ({
    data: {
      triggers: [
        {
          type: 'order_inquiry_handover',
          label: 'Order inquiry handover to purchasing',
          description: 'Fires once per commit that raises, settles or cancels order inquiry rows.',
          config_schema: {},
          supports_grouping: true,
        },
      ],
    },
  }),
}));

vi.mock('../../email-templates/hooks/useEmailTemplates', () => ({
  useEmailTemplates: () => ({
    data: {
      data: [
        {
          id: 'tpl-1',
          name: 'Order Inquiry Handover to Purchasing (default)',
          code: 'order_inquiry_handover_default',
        },
      ],
    },
  }),
}));

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

// RecipientPicker fetches its users/roles lists on mount - stub both so the
// component settles without a real network call (same shape as
// RecipientPicker.include_actor.test.tsx). RecipientPicker itself is NOT
// mocked away: the whole point of this test is to render it for real and
// read back its checked state.
vi.mock('@/services/userSelectService', () => ({
  getUsersSelect: vi.fn().mockResolvedValue([]),
}));
vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn().mockResolvedValue({
    ok: true,
    json: async () => [{ id: 'role-purchasing', name: 'Purchasing', slug: 'purchasing' }],
  }),
}));

beforeEach(() => {
  vi.clearAllMocks();
  createMutateAsync.mockResolvedValue({});
  updateMutateAsync.mockResolvedValue({});
  // jsdom does not implement these; Radix Select/Checkbox call them.
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.hasPointerCapture = vi.fn();
});

// An automation loaded from the API, exactly as the "Order inquiry to
// purchasing" seed round-trips it: include_actor and include_assigned_cs_pic
// both true, group_matches explicitly false.
const AUTOMATION: Automation = {
  id: 'auto-oi-handover',
  name: 'Order inquiry to purchasing',
  description:
    'Parallel run (go-live 17 Sep): mails purchasing whenever CS raises, settles or cancels order inquiry rows.',
  enabled: true,
  trigger_type: 'order_inquiry_handover',
  trigger_config: {},
  conditions_json: null,
  action_type: 'send_email',
  email_template_id: 'tpl-1',
  email_template_name: 'Order Inquiry Handover to Purchasing (default)',
  recipient_config: {
    user_ids: [],
    role_ids: ['role-purchasing'],
    include_promotion_owner: false,
    include_assigned_cs_pic: true,
    include_actor: true,
    extra_emails: [],
  },
  group_matches: false,
  schedule_type: 'manual',
  run_time: null,
  timezone: 'Asia/Kuala_Lumpur',
  last_run_at: null,
  last_status: null,
  last_error: null,
  next_run_at: null,
  created_by_user_id: null,
  created_at: '2026-09-16T00:00:00Z',
  updated_at: '2026-09-16T00:00:00Z',
};

function renderEditForm() {
  return render(<AutomationForm open onOpenChange={vi.fn()} automation={AUTOMATION} />);
}

// AC-H16 round-trip half: the recipient picker's checkboxes and the
// combine-into-one-email switch must reflect what the server actually saved,
// and an unchanged save must not silently rewrite them. AutomationForm.tsx's
// edit-open hydration (around line 103-108) drops include_actor and
// include_assigned_cs_pic when rebuilding recipientConfig, so (a) and (c)
// below are red today.
describe('AutomationForm - edit-open hydration (AC-H16)', () => {
  it('renders "Cc the person who raised it" checked when the saved automation has include_actor: true', async () => {
    renderEditForm();
    const checkbox = await screen.findByLabelText(/Cc the person who raised it/i);
    expect(checkbox.getAttribute('aria-checked')).toBe('true');
  });

  it('renders "Include assigned CS PIC" checked when the saved automation has include_assigned_cs_pic: true', async () => {
    renderEditForm();
    const checkbox = await screen.findByLabelText(/Include assigned CS PIC/i);
    expect(checkbox.getAttribute('aria-checked')).toBe('true');
  });

  it('submits include_actor, include_assigned_cs_pic and group_matches unchanged when saving with no edits', async () => {
    renderEditForm();
    // Let RecipientPicker's user/role fetches settle before saving.
    await screen.findByLabelText(/Cc the person who raised it/i);

    fireEvent.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => expect(updateMutateAsync).toHaveBeenCalledTimes(1));
    const payload = updateMutateAsync.mock.calls[0][0];
    expect(payload.recipient_config.include_actor).toBe(true);
    expect(payload.recipient_config.include_assigned_cs_pic).toBe(true);
    expect(payload.group_matches).toBe(false);
  });

  // DEALER-OI-ROUTE card Q2 (b), as ruled on 1 Nov: an existing row keeps "first address To,
  // the rest Cc" until someone changes a To or Cc address; only then do the boxes mean
  // exactly To and Cc (OI-ROUTE-BY-RAISER review, 4 Nov).
  it('a save that changes no To/Cc address keeps a legacy row legacy', async () => {
    renderEditForm();
    await screen.findByLabelText(/Cc the person who raised it/i);
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }));
    await waitFor(() => expect(updateMutateAsync).toHaveBeenCalledTimes(1));
    expect(updateMutateAsync.mock.calls[0][0].recipient_config.explicit_to_cc).toBe(false);
  });

  it('changing a checkbox is not a To/Cc address change', async () => {
    renderEditForm();
    fireEvent.click(await screen.findByLabelText(/Cc the person who raised it/i));
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }));
    await waitFor(() => expect(updateMutateAsync).toHaveBeenCalledTimes(1));
    const config = updateMutateAsync.mock.calls[0][0].recipient_config;
    expect(config.include_actor).toBe(false);
    expect(config.explicit_to_cc).toBe(false);
  });

  it('adding a Cc address marks the row explicit', async () => {
    renderEditForm();
    await screen.findByLabelText(/Cc the person who raised it/i);
    const cc = within(screen.getByRole('group', { name: 'Cc' }));
    fireEvent.change(cc.getByPlaceholderText('someone@example.com'), {
      target: { value: 'cc@example.com' },
    });
    fireEvent.click(cc.getByRole('button', { name: 'Add' }));
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }));
    await waitFor(() => expect(updateMutateAsync).toHaveBeenCalledTimes(1));
    const config = updateMutateAsync.mock.calls[0][0].recipient_config;
    expect(config.cc_emails).toEqual(['cc@example.com']);
    expect(config.explicit_to_cc).toBe(true);
  });

  it('removing a To address marks the row explicit', async () => {
    render(
      <AutomationForm
        open
        onOpenChange={vi.fn()}
        automation={{
          ...AUTOMATION,
          recipient_config: { ...AUTOMATION.recipient_config, extra_emails: ['to@example.com'] },
        }}
      />,
    );
    await screen.findByLabelText(/Cc the person who raised it/i);
    const to = within(screen.getByRole('group', { name: 'To' }));
    fireEvent.click(to.getByRole('button', { name: /remove to@example.com/i }));
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }));
    await waitFor(() => expect(updateMutateAsync).toHaveBeenCalledTimes(1));
    expect(updateMutateAsync.mock.calls[0][0].recipient_config.explicit_to_cc).toBe(true);
  });

  it('a row already explicit stays explicit on an unchanged save', async () => {
    render(
      <AutomationForm
        open
        onOpenChange={vi.fn()}
        automation={{
          ...AUTOMATION,
          recipient_config: { ...AUTOMATION.recipient_config, explicit_to_cc: true },
        }}
      />,
    );
    await screen.findByLabelText(/Cc the person who raised it/i);
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }));
    await waitFor(() => expect(updateMutateAsync).toHaveBeenCalledTimes(1));
    expect(updateMutateAsync.mock.calls[0][0].recipient_config.explicit_to_cc).toBe(true);
  });
});
