import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

import MyPendingSLAWidget from './MyPendingSLAWidget';
import type { MyPendingSLAItem } from '../services/conversationSLATrackingService';

const getMyPendingSLA = vi.fn();
const resolveConversationSLATracking = vi.fn();
const escalateConversationSLATracking = vi.fn();

vi.mock('../services/conversationSLATrackingService', () => ({
  getMyPendingSLA: (...a: unknown[]) => getMyPendingSLA(...a),
  resolveConversationSLATracking: (...a: unknown[]) => resolveConversationSLATracking(...a),
  escalateConversationSLATracking: (...a: unknown[]) => escalateConversationSLATracking(...a),
}));

const push = vi.fn();
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const formItem: MyPendingSLAItem = {
  id: 'f1',
  source_entity_type: 'purchase_request',
  source_entity_id: 'pr-uuid',
  is_form_sla: true,
  reference: 'PR26-0316',
  respond_io_id: null,
  next_action: 'Send for approval',
  due_at: new Date(Date.now() + 3600_000).toISOString(),
  is_responded: false,
  current_tier: 1,
  policy_name: 'Default',
};

const convoItem: MyPendingSLAItem = {
  id: 'c1',
  source_entity_type: null,
  source_entity_id: null,
  is_form_sla: false,
  reference: '+60166753328',
  respond_io_id: '999',
  next_action: null,
  due_at: new Date(Date.now() - 3600_000).toISOString(),
  is_responded: false,
  current_tier: 2,
  policy_name: 'Default',
};

// A ticket is a form-SLA type the FE route map does NOT know, yet it has a Respond
// contact — the case that used to be mis-classified as a conversation.
const ticketItem: MyPendingSLAItem = {
  id: 'tk1',
  source_entity_type: 'ticket',
  source_entity_id: 'ticket-uuid',
  is_form_sla: true,
  reference: null,
  respond_io_id: '440987225',
  next_action: 'Mark CS resolved',
  due_at: new Date(Date.now() - 3600_000).toISOString(),
  is_responded: false,
  current_tier: 1,
  policy_name: 'Default',
};

describe('MyPendingSLAWidget clickable rows', () => {
  beforeEach(() => {
    getMyPendingSLA.mockReset();
    resolveConversationSLATracking.mockReset();
    escalateConversationSLATracking.mockReset();
    push.mockReset();
  });

  it('form-SLA row: no open/resolve/escalate buttons; clicking the row opens the record', async () => {
    getMyPendingSLA.mockResolvedValue([formItem]);
    render(<MyPendingSLAWidget />);

    await waitFor(() => expect(screen.getByText('Purchase request')).toBeInTheDocument());
    expect(screen.getByText(/Tier 1 · Send for approval/i)).toBeInTheDocument();
    // The Open record / Resolve / Escalate controls are gone for form rows.
    expect(screen.queryByRole('link', { name: /Open record/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Resolve/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Escalate/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('Purchase request'));
    expect(push).toHaveBeenCalledWith('/procurement-management/purchase-requests/pr-uuid');
  });

  it('conversation-SLA row: Escalate + Resolve buttons; clicking the row opens Respond', async () => {
    getMyPendingSLA.mockResolvedValue([convoItem]);
    const openSpy = vi.spyOn(window, 'open').mockReturnValue(null);
    render(<MyPendingSLAWidget />);

    await waitFor(() => expect(screen.getByText('Enquiry')).toBeInTheDocument());
    expect(screen.getByText(/Tier 2 · Reply/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Open in Respond/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Escalate/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Resolve/i })).toBeInTheDocument();

    fireEvent.click(screen.getByText('Enquiry'));
    expect(openSpy).toHaveBeenCalledWith(
      'https://app.respond.io/space/364817/inbox/999',
      '_blank',
      'noopener,noreferrer',
    );
    openSpy.mockRestore();
  });

  it('Escalate flow: opens reason dialog, submits, calls escalate service with reason', async () => {
    getMyPendingSLA.mockResolvedValue([convoItem]);
    escalateConversationSLATracking.mockResolvedValue(undefined);
    render(<MyPendingSLAWidget />);

    await waitFor(() => expect(screen.getByRole('button', { name: /Escalate/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Escalate/i }));

    await waitFor(() => expect(screen.getByText('Escalate to tier 3')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'Customer angry' } });
    // The dialog submit button is the second "Escalate" (the row button is the first).
    const escalateButtons = screen.getAllByRole('button', { name: /^Escalate$/i });
    fireEvent.click(escalateButtons[escalateButtons.length - 1]);

    await waitFor(() =>
      expect(escalateConversationSLATracking).toHaveBeenCalledWith('c1', 'Customer angry'),
    );
  });

  it('ticket (form-SLA, no FE route) shows NO buttons; clicking opens Respond', async () => {
    getMyPendingSLA.mockResolvedValue([ticketItem]);
    const openSpy = vi.spyOn(window, 'open').mockReturnValue(null);
    render(<MyPendingSLAWidget />);

    await waitFor(() => expect(screen.getByText('Ticket')).toBeInTheDocument());
    // Form-SLA stage: no conversation Escalate/Resolve (handled at the form).
    expect(screen.queryByRole('button', { name: /Escalate/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Resolve/i })).not.toBeInTheDocument();
    // It has a Respond contact but no FE record route → clicking opens Respond.
    fireEvent.click(screen.getByText('Ticket'));
    expect(openSpy).toHaveBeenCalledWith(
      'https://app.respond.io/space/364817/inbox/440987225',
      '_blank',
      'noopener,noreferrer',
    );
    expect(push).not.toHaveBeenCalled();
    openSpy.mockRestore();
  });

  it('Resolve confirm calls the resolve service', async () => {
    getMyPendingSLA.mockResolvedValue([convoItem]);
    resolveConversationSLATracking.mockResolvedValue(undefined);
    render(<MyPendingSLAWidget />);

    await waitFor(() => expect(screen.getByRole('button', { name: /Resolve/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Resolve/i }));
    await waitFor(() => expect(screen.getByText('Mark as resolved')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /^Confirm$/i }));

    await waitFor(() => expect(resolveConversationSLATracking).toHaveBeenCalledWith('c1'));
  });

  it('empty state when nothing pending', async () => {
    getMyPendingSLA.mockResolvedValue([]);
    render(<MyPendingSLAWidget />);
    await waitFor(() =>
      expect(screen.getByText(/you're all caught up/i)).toBeInTheDocument(),
    );
  });
});
