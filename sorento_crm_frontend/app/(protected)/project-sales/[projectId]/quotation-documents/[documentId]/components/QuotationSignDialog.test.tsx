/**
 * Which name a signature is filed under.
 *
 * The pad's `typedText` means different things per mode: in Type it is the signatory's name, in
 * Initials it is "A.F.". Sending it blindly filed an initialled signature under the initials, and
 * that name is what the printed quotation shows beside the ink, so the document ends up signed by
 * "A.F." rather than by a person. Draw mode carries no text at all and must fall back the same way.
 */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { SignatureValue } from '@/components/common/SignaturePad';
import { QuotationSignDialog } from './QuotationSignDialog';

/**
 * The pad is stubbed to a set of buttons, one per mode, each committing the value that mode
 * really produces. What is under test is the mapping from a committed signature to the request,
 * not the canvas.
 */
vi.mock('@/components/common/SignaturePad', () => ({
  SignaturePad: ({ onChange }: { onChange: (value: SignatureValue | null) => void }) => {
    const base = {
      dataUrl: 'data:image/png;base64,STUB',
      signedAt: '2026-08-05T02:00:00.000Z',
      gpsLat: null,
      gpsLng: null,
    };
    return (
      <div>
        <button
          type="button"
          onClick={() => onChange({ ...base, mode: 'type', typedText: 'Ahmad Faizal' })}
        >
          commit type
        </button>
        <button
          type="button"
          onClick={() => onChange({ ...base, mode: 'initials', typedText: 'A.F.' })}
        >
          commit initials
        </button>
        <button
          type="button"
          onClick={() => onChange({ ...base, mode: 'draw', typedText: null })}
        >
          commit draw
        </button>
        <button type="button" onClick={() => onChange(null)}>
          clear
        </button>
      </div>
    );
  },
}));

function renderDialog(onSign = vi.fn(), signatoryName: string | null = 'Ahmad Faizal') {
  render(
    <QuotationSignDialog
      open
      onOpenChange={vi.fn()}
      signatoryName={signatoryName}
      isSaving={false}
      onSign={onSign}
    />,
  );
  return onSign;
}

describe('QuotationSignDialog: the name a signature is filed under', () => {
  it('files an initialled signature under the signatory, not under the initials', () => {
    const onSign = renderDialog();

    fireEvent.click(screen.getByText('commit initials'));

    expect(onSign).toHaveBeenCalledTimes(1);
    expect(onSign.mock.calls[0][0]).toMatchObject({
      signer_name: 'Ahmad Faizal',
      mode: 'initials',
    });
    // The exact defect: "A.F." reaching the name field and then the printed quotation.
    expect(onSign.mock.calls[0][0].signer_name).not.toBe('A.F.');
  });

  it('takes the typed name in Type mode, because there it really is the name', () => {
    const onSign = renderDialog(vi.fn(), 'Stale Default');

    fireEvent.click(screen.getByText('commit type'));

    expect(onSign.mock.calls[0][0].signer_name).toBe('Ahmad Faizal');
  });

  it('falls back to the signatory when the mode carries no text at all', () => {
    const onSign = renderDialog();

    fireEvent.click(screen.getByText('commit draw'));

    expect(onSign.mock.calls[0][0].signer_name).toBe('Ahmad Faizal');
  });

  it('sends nothing when the pad is cleared, because clearing is a local act', () => {
    const onSign = renderDialog();

    fireEvent.click(screen.getByText('clear'));

    expect(onSign).not.toHaveBeenCalled();
  });
});
