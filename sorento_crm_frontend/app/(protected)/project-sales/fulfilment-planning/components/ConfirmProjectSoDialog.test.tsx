/**
 * Stage 1C - the one confirmation for the whole sales order (AC-C01, AC-G03).
 *
 * The copy is the contract: it names the sales order and the number of lines the press
 * commits, it says which of the two things is about to happen (a first revision, or one
 * that supersedes the revision standing now), and it says plainly that it cannot be
 * undone. It is the shared AlertDialog, never the browser's confirm().
 */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

import { ConfirmProjectSoDialog } from './ConfirmProjectSoDialog';

const onConfirm = vi.fn();
const onDone = vi.fn();

function renderDialog(
  props: { lineCount?: number; currentRevision?: number | null; submitting?: boolean } = {},
) {
  return render(
    <ConfirmProjectSoDialog
      reference="SO376201"
      lineCount={props.lineCount ?? 4}
      currentRevision={props.currentRevision ?? null}
      submitting={props.submitting ?? false}
      onDone={onDone}
      onConfirm={onConfirm}
    />,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ConfirmProjectSoDialog', () => {
  it('names the sales order and how many lines go with the press (AC-G03)', () => {
    renderDialog();

    expect(screen.getByText('Confirm SO376201?')).toBeInTheDocument();
    expect(screen.getByText('All 4 lines are confirmed together.')).toBeInTheDocument();
  });

  it('says "1 line" rather than "1 lines"', () => {
    renderDialog({ lineCount: 1 });

    expect(screen.getByText('All 1 line are confirmed together.')).toBeInTheDocument();
  });

  it('says which revision is about to be superseded, when there is one', () => {
    renderDialog({ currentRevision: 2 });

    expect(
      screen.getByText('All 4 lines are confirmed together and supersede revision 2.'),
    ).toBeInTheDocument();
  });

  it('says what the press does and that it cannot be undone', () => {
    renderDialog();

    expect(
      screen.getByText(
        /The composition is frozen and the Buy residual goes to purchasing\. This\s+action cannot be undone\./,
      ),
    ).toBeInTheDocument();
  });

  it('confirms once, through the shared dialog and never through the browser confirm', () => {
    const nativeConfirm = vi.spyOn(window, 'confirm');

    renderDialog();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm the sales order' }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(nativeConfirm).not.toHaveBeenCalled();
    // The dialog does not close itself: the section closes it once the call answers.
    expect(onDone).not.toHaveBeenCalled();
  });

  it('confirms nothing on cancel', () => {
    renderDialog();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(onDone).toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('blocks a second press while the first is in flight, and says it is working', () => {
    renderDialog({ submitting: true });

    const action = screen.getByRole('button', { name: /Confirming/ });
    expect(action).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
  });
});
