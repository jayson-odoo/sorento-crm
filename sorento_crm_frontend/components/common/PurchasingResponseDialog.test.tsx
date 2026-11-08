/**
 * The ONE "Edit purchasing response" dialog, shared by the stock inquiry page and the new product
 * application detail (owner 8 Nov 15:10). Assumed props (the coder matches them or tells the tester):
 *   open, onOpenChange(open),
 *   response (string), onResponseChange(text),
 *   onSave()            "Save only",
 *   onReply()           "Update & Reply",
 *   canReply?: boolean  Update & Reply is drawn only when true,
 *   saving?: boolean, replying?: boolean (disable the buttons),
 *   description?: ReactNode (defaults to the stock inquiry sentence),
 *   children            the host's own fields, between the textarea and the footer.
 * Exported as `PurchasingResponseDialog` (named) or default.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import * as mod from '@/components/common/PurchasingResponseDialog';

const Dialog = ((mod as Record<string, unknown>).PurchasingResponseDialog ??
  (mod as Record<string, unknown>).default) as React.ComponentType<Record<string, unknown>>;

function setup(over: Record<string, unknown> = {}) {
  const props = {
    open: true,
    onOpenChange: vi.fn(),
    response: '',
    onResponseChange: vi.fn(),
    onSave: vi.fn(),
    onReply: vi.fn(),
    canReply: true,
    ...over,
  };
  render(
    <Dialog {...props}>
      <div data-testid="host-fields">host fields</div>
    </Dialog>,
  );
  return props;
}

const before = (a: Node, b: Node) =>
  Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);

describe('PurchasingResponseDialog', () => {
  it('exposes the shared test id on its content and titles itself like the stock inquiry one', () => {
    setup();
    const dialog = screen.getByTestId('purchasing-response-dialog');
    expect(within(dialog).getByText('Edit purchasing response')).toBeInTheDocument();
  });

  it('draws title, description, Purchasing response textarea, host children, then Cancel, Save only, Update & Reply', () => {
    setup({ response: 'ok' });
    const dialog = screen.getByTestId('purchasing-response-dialog');
    const title = within(dialog).getByText('Edit purchasing response');
    const description = within(dialog).getByText(/Update & Reply saves your text and sends it/);
    const label = within(dialog).getByText('Purchasing response');
    const box = within(dialog).getByRole('textbox', { name: /purchasing response/i });
    const host = within(dialog).getByTestId('host-fields');
    const cancel = within(dialog).getByRole('button', { name: /^cancel$/i });
    const saveOnly = within(dialog).getByRole('button', { name: /^save only$/i });
    const reply = within(dialog).getByRole('button', { name: /^update & reply$/i });
    const order = [title, description, label, box, host, cancel, saveOnly, reply];
    for (let i = 0; i < order.length - 1; i += 1) {
      expect(before(order[i], order[i + 1]), `element ${i} before ${i + 1}`).toBe(true);
    }
    expect(box.getAttribute('id')).toBe('edit-purchasing-response');
    expect(reply.querySelector('svg.lucide-send')).not.toBeNull();
  });

  it('shows the response text and reports edits', () => {
    const props = setup({ response: 'We can supply' });
    const box = screen.getByRole('textbox', { name: /purchasing response/i }) as HTMLTextAreaElement;
    expect(box.value).toBe('We can supply');
    fireEvent.change(box, { target: { value: 'New text' } });
    expect(props.onResponseChange).toHaveBeenCalledWith('New text');
  });

  it('disables both Save only and Update & Reply while the response is blank', () => {
    setup({ response: '   ' });
    expect(screen.getByRole('button', { name: /^save only$/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /^update & reply$/i })).toBeDisabled();
  });

  it('enables both once there is text, and each calls its own handler', () => {
    const props = setup({ response: 'ok' });
    fireEvent.click(screen.getByRole('button', { name: /^save only$/i }));
    expect(props.onSave).toHaveBeenCalledTimes(1);
    expect(props.onReply).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: /^update & reply$/i }));
    expect(props.onReply).toHaveBeenCalledTimes(1);
  });

  it('hides Update & Reply when the host cannot reply, and keeps Save only', () => {
    setup({ response: 'ok', canReply: false });
    expect(screen.queryByRole('button', { name: /update & reply/i })).toBeNull();
    expect(screen.getByRole('button', { name: /^save only$/i })).toBeEnabled();
  });

  it('draws nothing when closed', () => {
    setup({ open: false });
    expect(screen.queryByTestId('purchasing-response-dialog')).toBeNull();
  });
});
