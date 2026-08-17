/**
 * The snippet create/edit modal (UAC AC-L4, slice S4.4).
 *
 * The interesting case is the REJECTED save: a duplicate shortcut is a 409, the
 * mutation hook toasts it, and the dialog has to survive that with the typed
 * text intact - not throw the rejection into the void.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import MessageSnippetFormDialog from './MessageSnippetFormDialog';

function renderDialog(
  props: Partial<React.ComponentProps<typeof MessageSnippetFormDialog>> = {},
) {
  const onOpenChange = vi.fn();
  const onSubmit = vi.fn().mockResolvedValue(undefined);
  render(
    <MessageSnippetFormDialog
      open
      onOpenChange={onOpenChange}
      snippet={null}
      onSubmit={onSubmit}
      isSubmitting={false}
      {...props}
    />,
  );
  return { onOpenChange, onSubmit: props.onSubmit ?? onSubmit };
}

function fillForm(name = 'Stock check', body = 'Hi $contact_name.') {
  fireEvent.change(screen.getByLabelText('Name'), { target: { value: name } });
  fireEvent.change(screen.getByLabelText('Message'), { target: { value: body } });
}

describe('MessageSnippetFormDialog', () => {
  it('refuses to save a snippet with no name or no text', async () => {
    const { onSubmit } = renderDialog();

    fireEvent.click(screen.getByRole('button', { name: /Create snippet/i }));

    expect(await screen.findByText('Give the snippet a name.')).toBeInTheDocument();
    expect(screen.getByText('A snippet needs some text.')).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('submits the trimmed values, with a blank shortcut sent as null', async () => {
    const { onSubmit } = renderDialog();

    fillForm('  Stock check  ', 'Hi $contact_name.');
    fireEvent.click(screen.getByRole('button', { name: /Create snippet/i }));

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith({
        name: 'Stock check',
        shortcut: null,
        body: 'Hi $contact_name.',
        is_active: true,
      }),
    );
  });

  it('a rejected save keeps the dialog open, with the draft intact', async () => {
    // FINDING 11: `void submit()` let a 409 become an unhandled rejection.
    const onSubmit = vi.fn().mockRejectedValue(new Error('That shortcut is taken.'));
    const { onOpenChange } = renderDialog({ onSubmit });

    fillForm('Stock check', 'Hi $contact_name.');
    fireEvent.click(screen.getByRole('button', { name: /Create snippet/i }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    // The hook owns the toast; the dialog just has to stay put.
    expect(onOpenChange).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Name')).toHaveValue('Stock check');
  });
});
