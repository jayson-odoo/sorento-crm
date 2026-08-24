import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

import { HandlingLockBanner } from './HandlingLockBanner';
import type { HandlingLockTracker } from './handlingLock';
import { formatDateTimeInMalaysia } from '@/lib/helpers';

function tracker(partial: Partial<HandlingLockTracker> = {}): HandlingLockTracker {
  return {
    id: 'trk-1',
    source_entity_type: 'complaint',
    current_tier: 2,
    is_resolved: false,
    handled_by_id: null,
    handled_by_name: null,
    handled_at: null,
    assigned_to_id: 'assignee-1',
    ...partial,
  };
}

const noop = () => {};

describe('HandlingLockBanner', () => {
  it('renders nothing when not_escalated (P1-7 regression)', () => {
    const { container } = render(
      <HandlingLockBanner state="not_escalated" tracker={null} onClaim={noop} onTakeOver={noop} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('unclaimed: shows tier + "I\'m handling this" and fires onClaim (P1-1)', () => {
    const onClaim = vi.fn();
    render(
      <HandlingLockBanner
        state="unclaimed"
        tracker={tracker({ current_tier: 3 })}
        onClaim={onClaim}
        onTakeOver={noop}
      />,
    );
    expect(screen.getByText(/Escalated to Tier 3/)).toBeInTheDocument();
    const btn = screen.getByRole('button', { name: /^Claim$/i });
    fireEvent.click(btn);
    expect(onClaim).toHaveBeenCalledTimes(1);
  });

  it('mine: shows "You\'re handling this" and no claim/take-over button (P1-2)', () => {
    render(
      <HandlingLockBanner
        state="mine"
        tracker={tracker({ handled_by_id: 'me', handled_by_name: 'You', handled_at: '2026-07-09T01:30:00' })}
        onClaim={noop}
        onTakeOver={noop}
      />,
    );
    expect(screen.getByText(/You're handling this/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Claim$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Take over handling/i })).not.toBeInTheDocument();
  });

  it('other_holds: names the holder + Take over opens a confirm before firing (P1-3, P1-9)', () => {
    const onTakeOver = vi.fn();
    const { container } = render(
      <HandlingLockBanner
        state="other_holds"
        tracker={tracker({ handled_by_id: 'jane', handled_by_name: 'Jane Tan' })}
        onClaim={noop}
        onTakeOver={onTakeOver}
      />,
    );
    expect(container).toHaveTextContent('Jane Tan is handling this');
    // Clicking the banner button opens the confirm dialog; onTakeOver not fired yet.
    fireEvent.click(screen.getByRole('button', { name: /Take over handling/i }));
    expect(onTakeOver).not.toHaveBeenCalled();
    // Confirm inside the dialog fires the handler.
    const dialog = screen.getByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: /Take over handling/i }));
    expect(onTakeOver).toHaveBeenCalledTimes(1);
  });

  it('admin_other_holds: shows Take over handling button (P1-6)', () => {
    const { container } = render(
      <HandlingLockBanner
        state="admin_other_holds"
        tracker={tracker({ handled_by_id: 'jane', handled_by_name: 'Jane Tan' })}
        onClaim={noop}
        onTakeOver={noop}
      />,
    );
    expect(container).toHaveTextContent('Jane Tan is handling this');
    expect(screen.getByRole('button', { name: /Take over handling/i })).toBeInTheDocument();
  });

  it('admin_unclaimed: subtle "not yet claimed" hint, no action button (P1-5)', () => {
    render(
      <HandlingLockBanner state="admin_unclaimed" tracker={tracker()} onClaim={noop} onTakeOver={noop} />,
    );
    expect(screen.getByText(/not yet claimed/i)).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('not_eligible: read-only banner with handler name, no button (P1-4)', () => {
    render(
      <HandlingLockBanner
        state="not_eligible"
        tracker={tracker({ handled_by_id: 'jane', handled_by_name: 'Jane Tan' })}
        onClaim={noop}
        onTakeOver={noop}
      />,
    );
    expect(screen.getByText(/handled by/i)).toBeInTheDocument();
    expect(screen.getByText(/Jane Tan/)).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});

describe('HandlingLockBanner - PersonLink integration (HL-2..HL-4)', () => {
  it('other_holds + phone → holder name is a wa.me anchor, and the "since" WHEN shows', () => {
    const { container } = render(
      <HandlingLockBanner
        state="other_holds"
        tracker={tracker({
          handled_by_id: 'jane',
          handled_by_name: 'Jane Tan',
          handled_by_wa_phone: '60123456789',
          handled_at: '2026-07-09T01:30:00',
        })}
        onClaim={noop}
        onTakeOver={noop}
      />,
    );
    const link = screen.getByRole('link', { name: 'Jane Tan' });
    expect(link).toHaveAttribute('href', 'https://wa.me/60123456789');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(container).toHaveTextContent(formatDateTimeInMalaysia('2026-07-09T01:30:00'));
    expect(container).toHaveTextContent(/is handling this/);
  });

  it('other_holds without phone → holder name is plain text, no anchor', () => {
    const { container } = render(
      <HandlingLockBanner
        state="other_holds"
        tracker={tracker({ handled_by_id: 'jane', handled_by_name: 'Jane Tan' })}
        onClaim={noop}
        onTakeOver={noop}
      />,
    );
    // The banner shell has no anchor before the confirm dialog opens.
    expect(container.querySelector('a')).toBeNull();
    expect(container).toHaveTextContent('Jane Tan is handling this');
  });

  it('not_eligible + phone → holder name is a wa.me anchor', () => {
    render(
      <HandlingLockBanner
        state="not_eligible"
        tracker={tracker({
          handled_by_id: 'jane',
          handled_by_name: 'Jane Tan',
          handled_by_wa_phone: '60123456789',
        })}
        onClaim={noop}
        onTakeOver={noop}
      />,
    );
    expect(screen.getByRole('link', { name: 'Jane Tan' })).toHaveAttribute(
      'href',
      'https://wa.me/60123456789',
    );
  });

  it('Take over confirm dialog shows the holder name as plain text (not a wa.me link)', () => {
    render(
      <HandlingLockBanner
        state="other_holds"
        tracker={tracker({
          handled_by_id: 'jane',
          handled_by_name: 'Jane Tan',
          handled_by_wa_phone: '60123456789',
        })}
        onClaim={noop}
        onTakeOver={noop}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /Take over handling/i }));
    const dialog = screen.getByRole('alertdialog');
    // Inside the confirm dialog the holder name is plain copy, never a link.
    expect(within(dialog).getByText('Jane Tan')).toBeInTheDocument();
    expect(within(dialog).queryByRole('link', { name: 'Jane Tan' })).toBeNull();
  });
});
