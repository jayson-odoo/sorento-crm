import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import SetDefaultTemplateDialog from './SetDefaultTemplateDialog';

vi.mock('@/services/whatsappTemplateService', async () => {
  const actual = await vi.importActual<
    typeof import('@/services/whatsappTemplateService')
  >('@/services/whatsappTemplateService');
  return {
    ...actual,
    listApprovedTemplates: vi.fn(),
    setTemplateDefault: vi.fn(),
  };
});

import {
  listApprovedTemplates,
  setTemplateDefault,
  type TemplateDefault,
  type WhatsAppTemplate,
} from '@/services/whatsappTemplateService';

const BUTTON_TEMPLATE: WhatsAppTemplate = {
  id: 'tpl-btn',
  respond_template_id: 'rt-2',
  name: 'update_with_button',
  language: 'en',
  category: 'UTILITY',
  status: 'approved',
  body_text: 'Hi {{1}}, update: {{2}}',
  param_count: 2,
  has_url_button: true,
  button_url_base: 'https://fe-sorento.foundryx.my/',
  button_text: 'View complaint',
  channel_name: 'WA',
  synced_at: '2026-06-22T00:00:00Z',
};

const PLAIN_TEMPLATE: WhatsAppTemplate = {
  ...BUTTON_TEMPLATE,
  id: 'tpl-plain',
  name: 'update_plain',
  has_url_button: false,
  button_url_base: null,
  button_text: null,
};

function makeCurrent(template: WhatsAppTemplate, mapping: Record<string, string>): TemplateDefault {
  return {
    use_case: 'complaint',
    template_id: template.id,
    template_name: template.name,
    template_status: 'approved',
    param_mapping: mapping as TemplateDefault['param_mapping'],
    is_valid: true,
    has_url_button: template.has_url_button,
    button_url_base: template.button_url_base,
  };
}

function renderDialog(current: TemplateDefault | null) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SetDefaultTemplateDialog
        useCase="complaint"
        current={current}
        open
        onOpenChange={() => {}}
      />
    </QueryClientProvider>,
  );
}

describe('SetDefaultTemplateDialog — dynamic URL button', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (listApprovedTemplates as any).mockResolvedValue([BUTTON_TEMPLATE, PLAIN_TEMPLATE]);
    (setTemplateDefault as any).mockResolvedValue({});
  });

  it('renders the Button link row for a template with a dynamic URL button', async () => {
    renderDialog(makeCurrent(BUTTON_TEMPLATE, { '1': 'contact_name', '2': 'message', button_url: 'portal_url' }));
    expect(await screen.findByText('Button link')).toBeInTheDocument();
    // The static base prefix is surfaced so the admin knows the URL shape.
    expect(screen.getByText('https://fe-sorento.foundryx.my/')).toBeInTheDocument();
  });

  it('does NOT render the Button link row for a plain template', async () => {
    renderDialog(makeCurrent(PLAIN_TEMPLATE, { '1': 'contact_name', '2': 'message' }));
    // Body renders -> dialog is ready.
    await screen.findByText('Hi {{1}}, update: {{2}}');
    expect(screen.queryByText('Button link')).not.toBeInTheDocument();
  });

  it('saves the button_url mapping in param_mapping', async () => {
    renderDialog(makeCurrent(BUTTON_TEMPLATE, { '1': 'contact_name', '2': 'message', button_url: 'portal_url' }));
    await screen.findByText('Button link');
    fireEvent.click(screen.getByRole('button', { name: /save default/i }));
    await waitFor(() => expect(setTemplateDefault).toHaveBeenCalled());
    const [, body] = (setTemplateDefault as any).mock.calls[0];
    expect(body.param_mapping.button_url).toBe('portal_url');
    expect(body.param_mapping['1']).toBe('contact_name');
  });
});

// --- Chat reply templates: `message` mapping enforcement (UAC-21) ------------

const CHAT_TEMPLATE: WhatsAppTemplate = {
  id: 'tpl-chat',
  respond_template_id: 'rt-chat',
  name: 'chat_reply',
  language: 'en',
  category: 'UTILITY',
  status: 'approved',
  body_text: 'Message from {{1}}: {{2}}',
  param_count: 2,
  has_url_button: false,
  button_url_base: null,
  button_text: null,
  channel_name: 'WA',
  synced_at: '2026-06-24T00:00:00Z',
};

// Every slot mapped, but NONE mapped to `message`.
const CHAT_CURRENT_NO_MESSAGE: TemplateDefault = {
  use_case: 'complaint_chat',
  template_id: 'tpl-chat',
  template_name: 'chat_reply',
  template_status: 'approved',
  param_mapping: { '1': 'contact_name', '2': 'sender_name' } as TemplateDefault['param_mapping'],
  is_valid: false,
};

function renderChatDialog(current: TemplateDefault | null) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SetDefaultTemplateDialog
        useCase="complaint_chat"
        current={current}
        open
        onOpenChange={() => {}}
      />
    </QueryClientProvider>,
  );
}

describe('SetDefaultTemplateDialog — chat message enforcement', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (listApprovedTemplates as any).mockResolvedValue([CHAT_TEMPLATE]);
    (setTemplateDefault as any).mockResolvedValue({});
    // Radix Select calls these on open; jsdom does not implement them.
    Element.prototype.scrollIntoView = vi.fn();
    (Element.prototype as any).hasPointerCapture = vi.fn();
    (Element.prototype as any).setPointerCapture = vi.fn();
    (Element.prototype as any).releasePointerCapture = vi.fn();
  });

  it('disables Save + shows chat-message-required when no slot maps to message', async () => {
    renderChatDialog(CHAT_CURRENT_NO_MESSAGE);
    expect(await screen.findByText('Message from {{1}}: {{2}}')).toBeInTheDocument();

    expect(screen.getByTestId('chat-message-required')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /save default/i })).toBeDisabled();
  });

  it('enables Save once a slot is remapped to message', async () => {
    renderChatDialog(CHAT_CURRENT_NO_MESSAGE);
    await screen.findByText('Message from {{1}}: {{2}}');

    // Slot {{2}} currently shows "Sender name"; remap it to "Full update message".
    // The slot picker is a SearchableSelect (Popover + cmdk) — it opens on click,
    // then renders its options as role="option" in the popover content.
    const slot2 = screen
      .getAllByRole('combobox')
      .find((el) => el.textContent?.includes('Sender name'))!;
    fireEvent.click(slot2);
    fireEvent.click(await screen.findByRole('option', { name: 'Full update message' }));

    await waitFor(() =>
      expect(screen.queryByTestId('chat-message-required')).not.toBeInTheDocument(),
    );
    expect(screen.getByRole('button', { name: /save default/i })).toBeEnabled();
  });
});
