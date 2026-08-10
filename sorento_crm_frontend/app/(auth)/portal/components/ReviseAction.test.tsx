/**
 * ReviseAction - the ONE policy block that drives both surfaces
 * (UAC-portal-submission-revisions B2 / B3).
 *
 * Allowed  -> a button plus the remaining budget.
 * Blocked  -> no button anywhere, and exactly one short sentence.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

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

describe('ReviseAction', () => {
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
