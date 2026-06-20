import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

import MyPendingSLAWidget from './MyPendingSLAWidget';
import type { MyPendingSLAItem } from '../services/conversationSLATrackingService';

const getMyPendingSLA = vi.fn();
const resolveConversationSLATracking = vi.fn();

vi.mock('../services/conversationSLATrackingService', () => ({
  getMyPendingSLA: (...a: unknown[]) => getMyPendingSLA(...a),
  resolveConversationSLATracking: (...a: unknown[]) => resolveConversationSLATracking(...a),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const formItem: MyPendingSLAItem = {
  id: 'f1',
  source_entity_type: 'purchase_request',
  source_entity_id: 'pr-uuid',
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
  reference: '+60166753328',
  respond_io_id: '999',
  next_action: null,
  due_at: new Date(Date.now() - 3600_000).toISOString(),
  is_responded: false,
  current_tier: 2,
  policy_name: 'Default',
};

describe('MyPendingSLAWidget guiding rows', () => {
  beforeEach(() => {
    getMyPendingSLA.mockReset();
    resolveConversationSLATracking.mockReset();
  });

  it('form-SLA row shows the SLA-config action (no generic responded/resolution line)', async () => {
    getMyPendingSLA.mockResolvedValue([formItem]);
    render(<MyPendingSLAWidget />);

    await waitFor(() => expect(screen.getByText('Purchase request')).toBeInTheDocument());
    // SLA-config-driven action, not "responded/awaiting resolution".
    expect(screen.getByText(/Tier 1 · Send for approval/i)).toBeInTheDocument();
    expect(screen.queryByText(/awaiting resolution/i)).not.toBeInTheDocument();
    // The old explanatory third line is gone.
    expect(screen.queryByText(/review and respond/i)).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Open record/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Resolve/i })).not.toBeInTheDocument();
  });

  it('conversation-SLA row: Respond redirect + Resolve, no files-unsupported line', async () => {
    getMyPendingSLA.mockResolvedValue([convoItem]);
    render(<MyPendingSLAWidget />);

    await waitFor(() => expect(screen.getByText('Enquiry')).toBeInTheDocument());
    expect(screen.getByText(/Tier 2 · Reply/i)).toBeInTheDocument();
    expect(screen.queryByText(/files cannot be sent/i)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Open in Respond/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Resolve/i })).toBeInTheDocument();
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
