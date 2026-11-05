/**
 * Owner hand test round 2 (5 Nov, #2138): the Need by calendar opened INSIDE the
 * Escalate dialog's scroll box (the dialog is transformed and `overflow-y-auto`),
 * so the calendar was cut off, the dialog grew both scrollbars and Send to
 * marketing was clipped. The calendar must render outside the dialog, at the
 * document root, where Radix places it against the viewport.
 */
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/components/dealer-kit/DesignViewer', () => ({ __esModule: true, default: () => null }));

import { EscalateDialog } from './PriceTagSelfApproval';

describe('Escalate dialog Need by calendar', () => {
  it('opens outside the dialog, not inside its scroll box', async () => {
    render(
      <EscalateDialog open onOpenChange={() => {}} onEscalate={vi.fn()} needBy="" />,
    );
    const dialog = await screen.findByRole('dialog');

    fireEvent.click(within(dialog).getByRole('button', { name: /pick a date/i }));

    const grid = await screen.findByRole('grid');
    expect(dialog.contains(grid)).toBe(false);
    expect(document.body.contains(grid)).toBe(true);
  });
});
