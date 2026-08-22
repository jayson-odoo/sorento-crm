/**
 * ReviseAction - the ONE policy block that drives both surfaces
 * (UAC-portal-submission-revisions B2 / B3).
 *
 * Allowed  -> an action plus the remaining budget.
 * Blocked  -> no action anywhere, and exactly one short sentence.
 *
 * Two presentations of that one policy (round 6): `inline` (the long-press
 * preview dialog's prominent button) and `menu` (the detail page's right-aligned
 * budget + gear). The policy branches must behave identically in both.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';

import { ReviseAction } from './ReviseAction';
import type { PortalRevisionPolicy } from '../lib/portal-client';

function policy(over: Partial<PortalRevisionPolicy> = {}): PortalRevisionPolicy {
  return {
    enabled: true,
    allowed: true,
    used: 1,
    max: 3,
    remaining: 2,
    blocked_reason: null,
    ...over,
  };
}

/**
 * Radix opens the dropdown on pointerdown, which jsdom does not synthesize from
 * a click - fire it explicitly, exactly as the office detail tests do.
 */
async function openGear() {
  const trigger = screen.getByRole('button', { name: 'Submission actions' });
  fireEvent.pointerDown(trigger, { button: 0, pointerId: 1 });
  fireEvent.pointerUp(trigger, { button: 0, pointerId: 1 });
  fireEvent.click(trigger);
  await waitFor(() => expect(trigger.getAttribute('aria-expanded')).toBe('true'));
  return trigger;
}

describe('ReviseAction - inline variant (the default)', () => {
  it('renders the action and the remaining budget when a revision is allowed', () => {
    render(<ReviseAction policy={policy()} onRevise={vi.fn()} />);

    expect(screen.getByRole('button', { name: 'Revise' })).toBeInTheDocument();
    expect(screen.getByText('2 of 3 revisions left')).toBeInTheDocument();
    expect(screen.queryByTestId('revise-blocked')).toBeNull();
  });

  it('calls back on click', () => {
    const onRevise = vi.fn();
    render(<ReviseAction policy={policy()} onRevise={onRevise} />);

    fireEvent.click(screen.getByRole('button', { name: 'Revise' }));
    expect(onRevise).toHaveBeenCalledTimes(1);
  });

  it('cap reached: no button, one sentence, no budget line', () => {
    render(
      <ReviseAction
        policy={policy({
          allowed: false,
          used: 3,
          remaining: 0,
          blocked_reason: 'You have used all 3 revisions.',
        })}
        onRevise={vi.fn()}
      />,
    );

    expect(screen.queryByRole('button', { name: 'Revise' })).toBeNull();
    expect(screen.queryByTestId('revise-remaining')).toBeNull();
    expect(screen.getByTestId('revise-blocked')).toHaveTextContent(
      'You have used all 3 revisions.',
    );
  });

  it('type disabled: the disabled sentence, still no button', () => {
    render(
      <ReviseAction
        policy={policy({
          enabled: false,
          allowed: false,
          max: 0,
          remaining: 0,
          blocked_reason: 'This form cannot be revised.',
        })}
        onRevise={vi.fn()}
      />,
    );

    expect(screen.queryByRole('button', { name: 'Revise' })).toBeNull();
    expect(screen.getByText('This form cannot be revised.')).toBeInTheDocument();
  });

  it('terminal status: the status sentence, still no button', () => {
    render(
      <ReviseAction
        policy={policy({
          allowed: false,
          blocked_reason: 'This stock inquiry is closed and can no longer be revised.',
        })}
        onRevise={vi.fn()}
      />,
    );

    expect(screen.queryByRole('button', { name: 'Revise' })).toBeNull();
    expect(
      screen.getByText('This stock inquiry is closed and can no longer be revised.'),
    ).toBeInTheDocument();
  });

  it('renders nothing at all when there is no policy yet', () => {
    const { container } = render(<ReviseAction policy={null} onRevise={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });
});

/**
 * The detail-page presentation: the budget and a gear, both pushed right, with
 * Revise demoted into the menu. Same policy, same copy, quieter placement.
 */
describe('ReviseAction - menu variant', () => {
  afterEach(cleanup);

  it('shows the budget beside a gear, and no bare Revise button', () => {
    render(<ReviseAction variant="menu" policy={policy()} onRevise={vi.fn()} />);

    expect(screen.getByTestId('revise-remaining')).toHaveTextContent(
      '2 of 3 revisions left',
    );
    expect(screen.getByRole('button', { name: 'Submission actions' })).toBeInTheDocument();
    // Demoted: nothing named Revise until the menu is opened.
    expect(screen.queryByRole('button', { name: 'Revise' })).toBeNull();
    expect(screen.queryByRole('menuitem', { name: 'Revise' })).toBeNull();
  });

  it('pushes the row to the right so the action sits away from the form', () => {
    render(<ReviseAction variant="menu" policy={policy()} onRevise={vi.fn()} />);

    const row = screen.getByTestId('revise-remaining').parentElement;
    expect(row).toHaveClass('justify-end');
  });

  it('keeps a touch-sized gear (44px), not the 34px office default', () => {
    render(<ReviseAction variant="menu" policy={policy()} onRevise={vi.fn()} />);

    const trigger = screen.getByRole('button', { name: 'Submission actions' });
    expect(trigger).toHaveClass('size-11');
    // twMerge must have dropped the variant's own square, or the two fight in
    // the cascade instead of one plainly winning.
    expect(trigger).not.toHaveClass('size-8.5');
  });

  it('opening the gear reveals Revise, and selecting it calls back', async () => {
    const onRevise = vi.fn();
    render(<ReviseAction variant="menu" policy={policy()} onRevise={onRevise} />);

    await openGear();
    const item = await screen.findByRole('menuitem', { name: 'Revise' });
    fireEvent.click(item);

    expect(onRevise).toHaveBeenCalledTimes(1);
  });

  it('a disabled action is present but not selectable', async () => {
    const onRevise = vi.fn();
    render(<ReviseAction variant="menu" policy={policy()} onRevise={onRevise} disabled />);

    await openGear();
    const item = await screen.findByRole('menuitem', { name: 'Revise' });
    expect(item).toHaveAttribute('data-disabled');
    fireEvent.click(item);
    expect(onRevise).not.toHaveBeenCalled();
  });

  it('blocked: the one sentence, right-aligned, with no gear and no budget', () => {
    render(
      <ReviseAction
        variant="menu"
        policy={policy({
          allowed: false,
          used: 3,
          remaining: 0,
          blocked_reason: 'You have used all 3 revisions.',
        })}
        onRevise={vi.fn()}
      />,
    );

    expect(screen.queryByRole('button', { name: 'Submission actions' })).toBeNull();
    expect(screen.queryByTestId('revise-remaining')).toBeNull();
    const blocked = screen.getByTestId('revise-blocked');
    expect(blocked).toHaveTextContent('You have used all 3 revisions.');
    // Sits where the budget line would have been.
    expect(blocked).toHaveClass('text-right');
  });

  it('renders nothing at all when there is no policy yet', () => {
    const { container } = render(
      <ReviseAction variant="menu" policy={null} onRevise={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
