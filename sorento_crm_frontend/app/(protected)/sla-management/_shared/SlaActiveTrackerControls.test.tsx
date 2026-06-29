import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SlaActiveTrackerControls } from './SlaActiveTrackerControls';
import type {
  ConversationSLATrackingDetail,
  ConversationSLAEventLog,
} from '@/app/(protected)/sla-management/conversation-sla-tracking/types/conversationSLATracking.types';

function evt(partial: Partial<ConversationSLAEventLog>): ConversationSLAEventLog {
  return {
    id: Math.random().toString(36).slice(2),
    sla_tracking_id: 't1',
    event_type: 'extend',
    event_at: new Date('2026-06-29T00:00:00Z'),
    reminder_count: 0,
    created_at: new Date('2026-06-29T00:00:00Z'),
    ...partial,
  } as ConversationSLAEventLog;
}

function tracker(partial: Partial<ConversationSLATrackingDetail>): ConversationSLATrackingDetail {
  return {
    id: 't1',
    current_tier: 2,
    current_tier_started_at: new Date('2026-06-20T00:00:00Z'),
    due_at: new Date('2026-07-01T00:00:00Z'),
    is_resolved: false,
    assigned_user_name: 'CK Lee',
    ...partial,
  } as ConversationSLATrackingDetail;
}

describe('SlaActiveTrackerControls — extension banner', () => {
  it('shows the latest extend reason of the active stage', () => {
    render(
      <SlaActiveTrackerControls
        activeTracker={tracker({
          event_logs: [
            evt({ event_at: new Date('2026-06-25T00:00:00Z'), reason: 'old reason' }),
            evt({
              event_at: new Date('2026-06-29T08:00:00Z'),
              reason: 'waiting on supplier RMA',
              due_at: new Date('2026-07-03T05:22:00Z'),
            }),
          ],
        })}
      />,
    );
    expect(screen.getByText(/SLA deadline extended/)).toBeInTheDocument();
    expect(screen.getByText(/waiting on supplier RMA/)).toBeInTheDocument();
    // Latest wins, not the older one.
    expect(screen.queryByText(/old reason/)).not.toBeInTheDocument();
  });

  it('renders nothing when the tracker is resolved (no active tracker)', () => {
    const { container } = render(<SlaActiveTrackerControls activeTracker={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('hides the extension banner when the active stage has no extend event', () => {
    render(
      <SlaActiveTrackerControls
        activeTracker={tracker({
          escalation_reason: 'manual: overdue',
          event_logs: [evt({ event_type: 'escalate', reason: 'manual: overdue' })],
        })}
      />,
    );
    // Escalation banner still shows, extension banner does not.
    expect(screen.getByText(/SLA escalated/)).toBeInTheDocument();
    expect(screen.queryByText(/SLA deadline extended/)).not.toBeInTheDocument();
  });

  it('shows both escalation and extension banners together', () => {
    render(
      <SlaActiveTrackerControls
        activeTracker={tracker({
          escalation_reason: 'manual: customer escalated',
          event_logs: [evt({ reason: 'parts ETA slipped' })],
        })}
      />,
    );
    expect(screen.getByText(/SLA escalated/)).toBeInTheDocument();
    expect(screen.getByText(/SLA deadline extended/)).toBeInTheDocument();
    expect(screen.getByText(/parts ETA slipped/)).toBeInTheDocument();
  });
});
