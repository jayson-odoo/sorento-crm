/**
 * CERT-TAB-UX (owner, 11 Nov 2026): no "Suggested" state anywhere. A code the system read itself
 * (`source: 'ai'`) looks like a typed one, on the register and on the quote: no badge, no Confirm
 * tick, and the pencil still edits it.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../hooks/useCertificates', () => ({
  useUpdateCertificateProductCode: () => ({ mutate: vi.fn(), isPending: false }),
}));

import { CoverageCodeEditor } from './CoverageCodeEditor';

describe('CoverageCodeEditor', () => {
  it.each([true, false])('shows an ai code with no Suggested badge or Confirm (canEdit %s)', (canEdit) => {
    render(
      <CoverageCodeEditor
        certificateId="c1"
        coverageId="cov1"
        code="WCY 8840"
        source="ai"
        canEdit={canEdit}
      />,
    );
    expect(screen.getByText('WCY 8840')).toBeInTheDocument();
    expect(screen.queryByText(/suggested/i)).toBeNull();
    expect(screen.queryByRole('button', { name: /confirm code/i })).toBeNull();
    if (canEdit) {
      expect(screen.getByRole('button', { name: /edit code on certificate/i })).toBeInTheDocument();
    }
  });
});
