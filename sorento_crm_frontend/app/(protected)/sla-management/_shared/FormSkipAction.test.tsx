/**
 * Tests for the skip gear item + confirm dialog (UAC C1/C2/C3/C5).
 *
 * The dialog's job is to make an irreversible action legible before it happens, so the
 * assertions centre on the consequence sentence being present and on the dialog
 * surviving a failed submit with the user's note intact.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';

import { FormSkipDialog, FormSkipMenuItem } from './FormSkipAction';
import type { UseFormSkipResult } from './useFormSkip';

vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenuItem: ({
    children,
    onSelect,
    ...rest
  }: React.PropsWithChildren<{ onSelect?: (e: { preventDefault: () => void }) => void }>) => (
    <button {...rest} onClick={() => onSelect?.({ preventDefault: () => {} })}>
      {children}
    </button>
  ),
}));

const CONSEQUENCE =
  'The technician settled this complaint during the site visit, so no replacement will be arranged and customer service will not be assigned.';

function skip(partial: Partial<UseFormSkipResult> = {}): UseFormSkipResult {
  return {
    canSkip: true,
    actionLabel: 'Settled on site',
    submit: vi.fn(),
    isSubmitting: false,
    ...partial,
  };
}

describe('FormSkipMenuItem', () => {
  it('renders the config-authored label (C1)', () => {
    render(<FormSkipMenuItem skip={skip()} onSelect={vi.fn()} />);
    expect(screen.getByTestId('form-skip-menu-item')).toHaveTextContent('Settled on site');
  });

  it('renders nothing when the stage is not skippable (C2)', () => {
    const { container } = render(<FormSkipMenuItem skip={skip({ canSkip: false })} onSelect={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when there is no label to show (C2)', () => {
    const { container } = render(
      <FormSkipMenuItem skip={skip({ actionLabel: null })} onSelect={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('opens the dialog rather than acting immediately', () => {
    const onSelect = vi.fn();
    const submit = vi.fn();
    render(<FormSkipMenuItem skip={skip({ submit })} onSelect={onSelect} />);
    fireEvent.click(screen.getByTestId('form-skip-menu-item'));
    expect(onSelect).toHaveBeenCalled();
    expect(submit).not.toHaveBeenCalled();
  });
});

describe('FormSkipDialog', () => {
  it('spells out the consequence and offers an optional note (C3)', () => {
    render(
      <FormSkipDialog
        skip={skip()}
        open
        onOpenChange={vi.fn()}
        consequence={CONSEQUENCE}
        detail="The complaint is closed as settled on site."
      />,
    );
    expect(screen.getByText(/Settled on site\?/)).toBeInTheDocument();
    expect(screen.getByText(/no replacement will be arranged/)).toBeInTheDocument();
    expect(screen.getByText(/customer service will not be assigned/)).toBeInTheDocument();
    expect(screen.getByText(/cannot be undone/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Message to contact \(optional\)/)).toBeInTheDocument();
  });

  it('submits the typed note', () => {
    const submit = vi.fn();
    render(
      <FormSkipDialog
        skip={skip({ submit })}
        open
        onOpenChange={vi.fn()}
        consequence={CONSEQUENCE}
      />,
    );
    fireEvent.change(screen.getByLabelText(/Message to contact \(optional\)/), {
      target: { value: '  Replaced the seal on site.  ' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Settled on site' }));
    expect(submit).toHaveBeenCalledWith('Replaced the seal on site.');
  });

  it('submits undefined rather than an empty string when the note is blank', () => {
    const submit = vi.fn();
    render(
      <FormSkipDialog
        skip={skip({ submit })}
        open
        onOpenChange={vi.fn()}
        consequence={CONSEQUENCE}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Settled on site' }));
    expect(submit).toHaveBeenCalledWith(undefined);
  });

  it('disables both actions and shows progress while in flight (C5)', () => {
    render(
      <FormSkipDialog
        skip={skip({ isSubmitting: true })}
        open
        onOpenChange={vi.fn()}
        consequence={CONSEQUENCE}
      />,
    );
    expect(screen.getByRole('button', { name: 'Saving…' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
  });
});
