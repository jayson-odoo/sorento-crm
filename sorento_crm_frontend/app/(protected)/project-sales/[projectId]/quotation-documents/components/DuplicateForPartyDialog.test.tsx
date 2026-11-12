/**
 * QUOTE-DUPLICATE-PARTY (UAC D2): one small popup, the header's own To + Attn pickers, Duplicate
 * disabled until a party is picked, and the pick is what is sent. Names are invented.
 */
import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('./QuotationRecipientPicker', () => ({
  QuotationRecipientPicker: ({ onChange }: { onChange: (p: Record<string, unknown>) => void }) => (
    <button
      type="button"
      onClick={() =>
        onChange({
          recipient_party_id: 'p-arch',
          recipient_role: 'architect',
          recipient_name_snapshot: 'ARKITEK CONTOH',
          attn_contact_ids: [],
        })
      }
    >
      pick architect
    </button>
  ),
  QuotationAttnChooser: ({ onChange }: { onChange: (p: Record<string, unknown>) => void }) => (
    <button
      type="button"
      onClick={() => onChange({ attn_contact_ids: ['c-1'], attn_name: 'Ar. Test Person' })}
    >
      choose contacts
    </button>
  ),
}));

import { DuplicateForPartyDialog } from './DuplicateForPartyDialog';

afterEach(cleanup);

function renderDialog(onConfirm = vi.fn(), onOpenChange = vi.fn()) {
  render(
    <DuplicateForPartyDialog
      open
      projectId="proj-1"
      siteAddress={null}
      isSaving={false}
      onOpenChange={onOpenChange}
      onConfirm={onConfirm}
    />,
  );
  return { onConfirm, onOpenChange };
}

describe('DuplicateForPartyDialog', () => {
  it('titles itself and disables Duplicate until a party is picked', () => {
    renderDialog();
    expect(screen.getByRole('dialog', { name: 'Duplicate for another party' })).toBeTruthy();
    const go = screen.getByRole('button', { name: 'Duplicate' }) as HTMLButtonElement;
    expect(go.disabled).toBe(true);
  });

  it('sends the picked party, its role and Attn people only', () => {
    const { onConfirm } = renderDialog();
    fireEvent.click(screen.getByText('pick architect'));
    fireEvent.click(screen.getByText('choose contacts'));
    const go = screen.getByRole('button', { name: 'Duplicate' }) as HTMLButtonElement;
    expect(go.disabled).toBe(false);
    fireEvent.click(go);
    expect(onConfirm).toHaveBeenCalledWith({
      recipient_party_id: 'p-arch',
      recipient_role: 'architect',
      attn_contact_ids: ['c-1'],
    });
  });

  it('Cancel closes with nothing sent', () => {
    const { onConfirm, onOpenChange } = renderDialog();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
