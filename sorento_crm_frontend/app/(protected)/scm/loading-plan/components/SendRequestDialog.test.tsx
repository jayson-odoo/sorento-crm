/**
 * "Send this request" - the channel, the recipients and the refusals (S3, AC-C1 to AC-C5).
 *
 * What is asserted here is the set of things that used to be impossible to get wrong because
 * they were not decisions at all: the send went by email, to `suppliers.email`, and a supplier
 * with no address on file got a notice that said `skipped`. Every one of them is now a choice
 * the dialog makes, so every one of them is a way to send the wrong thing to the wrong person.
 *
 * The send itself belongs to `LoadingPlanView`'s suite (it saves first, then sends) and to
 * pytest (what leaves the building); this file is about the form.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent: () => false,
  });
}
if (!window.ResizeObserver) {
  (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

type ChatContact = {
  id: string;
  name: string | null;
  phone: string | null;
  channel: string | null;
  suggested: boolean;
};

const chatState: {
  data: ChatContact[];
  connected: boolean;
  reason: string | null;
} = { data: [], connected: true, reason: null };

const chatQueries: string[] = [];

vi.mock('../../hooks/useFulfilment', () => ({
  useSupplierChatContacts: (_supplierId: string | null, query: string, enabled: boolean) => {
    if (enabled) chatQueries.push(query);
    return {
      data: enabled
        ? {
            data: chatState.data,
            total: chatState.data.length,
            wechat_connected: chatState.connected,
            wechat_channel_name: chatState.connected ? 'WeChat OA' : null,
            unavailable_reason: chatState.reason,
          }
        : undefined,
      isLoading: false,
    };
  },
}));

import { SendRequestDialog } from './SendRequestDialog';

const onSend = vi.fn();

function renderDialog(overrides: Partial<React.ComponentProps<typeof SendRequestDialog>> = {}) {
  return render(
    <SendRequestDialog
      open
      onOpenChange={vi.fn()}
      supplierId="sup-1"
      supplierName="Foshan Ceramics"
      supplierEmail="sales@jinbaichuan.cn"
      lineCount={3}
      totalQty={4242}
      unsavedCount={0}
      isBusy={false}
      error={null}
      onSend={onSend}
      {...overrides}
    />,
  );
}

function sendButton() {
  return screen.getByTestId('send-confirm') as HTMLButtonElement;
}

beforeEach(() => {
  onSend.mockReset();
  chatQueries.length = 0;
  chatState.data = [];
  chatState.connected = true;
  chatState.reason = null;
});

describe('SendRequestDialog', () => {
  it('opens on Email with the supplier address already in To (AC-C1, AC-C2)', () => {
    renderDialog();

    expect(screen.getByText('Send this request')).toBeTruthy();
    expect(screen.getByTestId('send-email-panel')).toBeTruthy();
    expect(screen.getByText('sales@jinbaichuan.cn')).toBeTruthy();
    expect(sendButton().disabled).toBe(false);
  });

  it('adds an address, and sends to every chip (AC-C2)', async () => {
    renderDialog();

    fireEvent.change(screen.getByLabelText('To'), { target: { value: 'ms.tee@sorento.com.my' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    fireEvent.click(sendButton());

    await waitFor(() =>
      expect(onSend).toHaveBeenCalledWith(
        expect.objectContaining({
          channel: 'email',
          recipients: ['sales@jinbaichuan.cn', 'ms.tee@sorento.com.my'],
        }),
      ),
    );
  });

  it('sends to an address typed but never committed with Add (AC-C2)', async () => {
    // It used to be dropped: the sender saw the address they had just typed sitting in the
    // box, pressed Send, and the request went to the OTHER addresses. What is on screen is
    // what they mean.
    renderDialog();

    fireEvent.change(screen.getByLabelText('To'), { target: { value: 'ms.tee@sorento.com.my' } });
    fireEvent.click(sendButton());

    await waitFor(() =>
      expect(onSend).toHaveBeenCalledWith(
        expect.objectContaining({
          recipients: ['sales@jinbaichuan.cn', 'ms.tee@sorento.com.my'],
        }),
      ),
    );
  });

  it('refuses to send on a typed address that is not one, and sends nothing', () => {
    renderDialog();

    fireEvent.change(screen.getByLabelText('To'), { target: { value: 'not-an-address' } });
    fireEvent.click(sendButton());

    expect(screen.getByText('not-an-address is not an email address.')).toBeTruthy();
    expect(onSend).not.toHaveBeenCalled();
  });

  it('refuses an address that is not one, inline, and does not add it (AC-C2)', () => {
    renderDialog();

    fireEvent.change(screen.getByLabelText('To'), { target: { value: 'not-an-address' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));

    expect(screen.getByText('not-an-address is not an email address.')).toBeTruthy();
    expect(screen.queryByLabelText('Remove not-an-address')).toBeNull();
  });

  it('removes a chip, and Send is disabled once nobody would receive it (AC-C2)', () => {
    renderDialog();

    fireEvent.click(screen.getByLabelText('Remove sales@jinbaichuan.cn'));

    expect(screen.queryByText('sales@jinbaichuan.cn')).toBeNull();
    expect(sendButton().disabled).toBe(true);
    expect(screen.getByText(/No address on file for Foshan Ceramics/)).toBeTruthy();
  });

  it('opens with no chips and cannot send when the supplier has no address (AC-C2)', () => {
    renderDialog({ supplierEmail: null });

    expect(sendButton().disabled).toBe(true);
  });

  it('disables Chat with the workspace reason when no WeChat channel is connected (AC-C3)', () => {
    chatState.connected = false;
    chatState.reason = 'No WeChat channel is connected in the Respond.io workspace.';
    renderDialog();

    fireEvent.click(screen.getByLabelText('Chat (WeChat)'));

    expect(screen.getByTestId('send-chat-panel')).toBeTruthy();
    expect(
      screen.getByText('No WeChat channel is connected in the Respond.io workspace.'),
    ).toBeTruthy();
    expect(sendButton().disabled).toBe(true);
  });

  it('preselects the supplier own number and sends to that contact (AC-C3)', async () => {
    chatState.data = [
      { id: 'c-1', name: 'Mr Chen (JBC)', phone: '+8613800000000', channel: 'wechat', suggested: true },
      { id: 'c-2', name: 'Someone else', phone: '+8613900000000', channel: 'wechat', suggested: false },
    ];
    renderDialog();

    fireEvent.click(screen.getByLabelText('Chat (WeChat)'));

    await waitFor(() => expect(sendButton().disabled).toBe(false));
    fireEvent.click(sendButton());
    await waitFor(() =>
      expect(onSend).toHaveBeenCalledWith(
        expect.objectContaining({ channel: 'chat', chatContactId: 'c-1' }),
      ),
    );
  });

  it('never queries Respond.io while the send is an email one (AC-C3)', () => {
    renderDialog();

    expect(chatQueries).toEqual([]);
  });

  it('says which of the eight refusals happened, in the dialog (AC-C5)', () => {
    const refused = Object.assign(new Error('server wording'), {
      code: 'template_missing',
    });
    renderDialog({ error: refused });

    expect(screen.getByTestId('send-refusal').textContent).toContain(
      'no approved template is mapped to supplier requests',
    );
  });

  it('falls back to the server message for a refusal code it has not heard of (AC-C5)', () => {
    const refused = Object.assign(new Error('Something the FE does not know about.'), {
      code: 'a_code_from_the_future',
    });
    renderDialog({ error: refused });

    expect(screen.getByTestId('send-refusal').textContent).toContain(
      'Something the FE does not know about.',
    );
  });

  it('states what leaves the building, retired link included', () => {
    renderDialog();

    expect(
      screen.getByText(/PDF \+ XLSX attached · link included · the previous link is retired/),
    ).toBeTruthy();
  });

  it('says the typed quantities are saved first (AC-A15)', () => {
    renderDialog({ unsavedCount: 2 });

    expect(screen.getByText(/Your typed quantities are saved first/)).toBeTruthy();
  });
});
