/**
 * OI-SPLIT-GUIDE test kit: Confirm (N) on the planning board opens a guide (UAC A1) instead of
 * posting. Specs that only care about what the press POSTS walk it with `walkConfirmGuide`:
 * press Confirm, step through every page with Next, then press the step 3 Confirm button.
 * Test ids are the PLAN's (`PLAN-oi-split-guide-20oct.md`, "Test ids").
 */
import { fireEvent, screen, waitFor } from '@testing-library/react';

/** Presses Confirm (N) and returns once the guide is open (nothing walked yet). */
export async function openConfirmGuide() {
  fireEvent.click(await screen.findByTestId('board-confirm'));
  return screen.findByTestId('confirm-guide');
}

/**
 * The next actionable control of the open guide: the step 3 Confirm, else an enabled Next. Null
 * once the guide has closed by itself after Review (UAC C7: every order refused).
 */
export async function guideControl(): Promise<HTMLElement | null> {
  return waitFor(() => {
    const confirm = screen.queryByTestId('confirm-guide-confirm');
    if (confirm) return confirm;
    // C7: every order refused, so the guide closed itself onto the result card.
    if (!screen.queryByTestId('confirm-guide')) return null;
    const next = screen.queryByTestId('confirm-guide-next') as HTMLButtonElement | null;
    if (next && !next.disabled) return next;
    throw new Error('the guide has no enabled Next or Confirm yet');
  });
}

/**
 * Walks Next until the step 3 Confirm shows (it stays open; nothing is posted yet). Returns null
 * when the guide closed itself after Review (C7).
 */
export async function walkToConfirmStep() {
  await openConfirmGuide();
  for (let i = 0; i < 12; i += 1) {
    const control = await guideControl();
    if (control === null) return null;
    if (control.getAttribute('data-testid') === 'confirm-guide-confirm') return control;
    fireEvent.click(control);
  }
  throw new Error('the guide never reached its Confirm step');
}

/**
 * Press Confirm (N), walk every page, press the guide's own Confirm: today's post. When every
 * order is refused the guide closes itself after Review and nothing is posted.
 */
export async function walkConfirmGuide() {
  const confirm = await walkToConfirmStep();
  if (!confirm) return;
  await waitFor(() => expect(confirm).toBeEnabled());
  fireEvent.click(confirm);
}
