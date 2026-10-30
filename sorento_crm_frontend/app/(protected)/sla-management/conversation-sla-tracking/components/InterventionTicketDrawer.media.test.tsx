/**
 * QUOTE-DRAWING-ESCALATE round 2 (owner hand test, 30 Oct): resolving a product drawing or photo
 * task feels like chat. The same side panel opens in `media` mode: no chat ticket fetch (that one
 * reaches Respond.io), the product, the quotations waiting, a link to Resources, Respond then
 * Resolve ticket.
 *
 * QUOTE-MEDIA-CHAT: a task with a conversation (`has_conversation`) mounts the chat panel and has no
 * Respond button (a reply is the Respond); without one it is the panel above. No "Following".
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import InterventionTicketDrawer from './InterventionTicketDrawer';
import type { MediaRequestDetail } from '../services/conversationSLATrackingService';

const useInterventionTicket = vi.fn();
const useMediaRequest = vi.fn();
const actOnDrawingRequest = vi.fn();
const refetch = vi.fn();

vi.mock('../hooks/useInterventionTickets', () => ({
  useInterventionTicket: (...a: unknown[]) => useInterventionTicket(...a),
  useResolveInterventionTicket: () => ({ mutate: vi.fn(), isPending: false }),
  useSendInterventionTicketMessage: () => ({
    mutate: vi.fn(),
    isPending: false,
  }),
  useDraftInterventionTicketReply: () => ({
    mutate: vi.fn(),
    isPending: false,
  }),
}));
vi.mock('../hooks/useMediaRequest', () => ({
  useMediaRequest: (...a: unknown[]) => useMediaRequest(...a),
}));
vi.mock('../services/conversationSLATrackingService', () => ({
  actOnDrawingRequest: (...a: unknown[]) => actOnDrawingRequest(...a),
}));
vi.mock('../hooks/useTeamPendingSLA', () => ({
  useReassignSLATracking: () => ({ mutate: vi.fn(), isPending: false }),
  useTakeoverSLATracking: () => ({ mutate: vi.fn(), isPending: false }),
}));
const hasPermission = vi.fn<(slug?: string) => boolean>(() => true);
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (...a: unknown[]) => hasPermission(...(a as [])),
}));
vi.mock('./ReassignDialog', () => ({
  default: ({ open }: { open: boolean }) =>
    open ? <div data-testid="reassign-dialog" /> : null,
}));
vi.mock('./ExtendDueDialog', () => ({
  default: ({ open }: { open: boolean }) =>
    open ? <div data-testid="extend-dialog" /> : null,
}));
vi.mock('./TicketConversationPanel', () => ({
  default: ({ ticketId }: { ticketId: string | null }) => (
    <div data-testid="ticket-conversation-panel" data-ticket-id={ticketId ?? ''} />
  ),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

const FUTURE = new Date(Date.now() + 5 * 3600_000).toISOString();

function detail(
  overrides: Partial<MediaRequestDetail> = {},
): MediaRequestDetail {
  return {
    tracking_id: 'trk-1',
    kind: 'drawing',
    product_id: 'p-1',
    product_code: 'PRD-CCC-03',
    product_name: 'Close coupled WC',
    product_href: '/master-data-management/products/p-1',
    resources_href: '/resource-management/attachment-directories',
    assignee_name: 'Aina',
    assignee_team_id: 'team-1',
    is_assignee: true,
    can_resolve: true,
    is_responded: false,
    responded_at: null,
    is_resolved: false,
    resolved_at: null,
    due_at: FUTURE,
    due_at_resolution: FUTURE,
    current_tier: 1,
    escalated_at: null,
    extension_count: 0,
    quotations: [
      {
        quotation_id: 'q1',
        project_id: 'pr1',
        label: 'QT-0001 · Townhouse',
        href: '/project-sales/pr1/quotations/q1',
      },
      {
        quotation_id: 'q2',
        project_id: 'pr1',
        label: 'QT-0002 · Villa',
        href: '/project-sales/pr1/quotations/q2',
      },
    ],
    has_conversation: false,
    // Tolerated while the old payload shape is still read; the panel no longer renders it.
    ...{ followers: [] as string[] },
    ...overrides,
  };
}

function mountDetail(
  data: MediaRequestDetail | undefined,
  extra: Record<string, unknown> = {},
) {
  useMediaRequest.mockReturnValue({
    data,
    isLoading: !data,
    isError: false,
    error: null,
    refetch,
    ...extra,
  });
}

function renderDrawer(
  props: Partial<React.ComponentProps<typeof InterventionTicketDrawer>> = {},
) {
  return render(
    <InterventionTicketDrawer
      ticketId="trk-1"
      open
      onOpenChange={() => {}}
      variant="media"
      {...props}
    />,
  );
}

beforeEach(() => {
  useInterventionTicket.mockReset();
  useInterventionTicket.mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  });
  useMediaRequest.mockReset();
  actOnDrawingRequest.mockReset();
  actOnDrawingRequest.mockResolvedValue(undefined);
  refetch.mockReset();
  refetch.mockResolvedValue(undefined);
  hasPermission.mockReset();
  hasPermission.mockReturnValue(true);
});

describe('InterventionTicketDrawer media variant', () => {
  it('shows the title, the product and the quotations waiting, and no Following section', () => {
    mountDetail(detail());
    renderDrawer();

    expect(
      screen.getByText('Product drawing · PRD-CCC-03'),
    ).toBeInTheDocument();
    const product = screen.getByRole('link', { name: /PRD-CCC-03/ });
    expect(product).toHaveAttribute(
      'href',
      '/master-data-management/products/p-1',
    );
    expect(screen.getByText(/Close coupled WC/)).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'QT-0001 · Townhouse' }),
    ).toHaveAttribute('href', '/project-sales/pr1/quotations/q1');
    expect(
      screen.getByRole('link', { name: 'QT-0002 · Villa' }),
    ).toBeInTheDocument();
    expect(screen.queryByText('Following')).not.toBeInTheDocument();
  });

  it('titles a photo task "Product photo"', () => {
    mountDetail(detail({ kind: 'photo' }));
    renderDrawer();
    expect(screen.getByText('Product photo · PRD-CCC-03')).toBeInTheDocument();
  });

  it('links to Resources as a plain link: no upload control in the panel', () => {
    mountDetail(detail());
    renderDrawer();

    const link = screen.getByRole('link', { name: /Upload in Resources/i });
    expect(link).toHaveAttribute(
      'href',
      '/resource-management/attachment-directories',
    );
    expect(document.querySelector('input[type="file"]')).toBeNull();
  });

  it('does not call the chat ticket fetch and shows no chat panel without a conversation', () => {
    mountDetail(detail({ has_conversation: false }));
    renderDrawer();

    expect(useInterventionTicket).not.toHaveBeenCalled();
    expect(screen.queryByTestId('ticket-conversation-panel')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Respond$/ })).toBeInTheDocument();
    expect(useMediaRequest).toHaveBeenCalledWith('trk-1');
  });

  it('with a conversation mounts the chat panel on the ticket and has no Respond button', () => {
    mountDetail(detail({ has_conversation: true }));
    renderDrawer();

    const panel = screen.getByTestId('ticket-conversation-panel');
    expect(panel).toHaveAttribute('data-ticket-id', 'trk-1');
    expect(
      screen.queryByRole('button', { name: /^Respond$/ }),
    ).not.toBeInTheDocument();
    // The facts block and Resolve ticket stay.
    expect(screen.getByRole('link', { name: /Upload in Resources/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Resolve ticket/ })).toBeInTheDocument();
    expect(useInterventionTicket).not.toHaveBeenCalled();
  });

  it('asks for the detail only while open', () => {
    mountDetail(detail());
    renderDrawer({ open: false });
    expect(useMediaRequest).toHaveBeenCalledWith(null);
  });

  it('shows empty states with a heading and a hint, no button, when nobody is waiting', () => {
    mountDetail(detail({ quotations: [] }));
    renderDrawer();

    expect(screen.getByText('Waiting on this')).toBeInTheDocument();
    expect(screen.getByTestId('media-quotations-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('media-followers-empty')).not.toBeInTheDocument();
    expect(
      screen.getByTestId('media-quotations-empty').querySelector('button'),
    ).toBeNull();
  });

  it('shows no UUID text anywhere', () => {
    mountDetail(detail());
    renderDrawer();
    expect(document.body.textContent ?? '').not.toMatch(
      /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}/,
    );
  });
});

describe('InterventionTicketDrawer media variant: Respond and Resolve', () => {
  it('shows Respond while not responded and calls the respond action', async () => {
    mountDetail(detail());
    renderDrawer();

    fireEvent.click(screen.getByRole('button', { name: /^Respond$/ }));

    await waitFor(() =>
      expect(actOnDrawingRequest).toHaveBeenCalledWith('trk-1', 'respond'),
    );
    await waitFor(() => expect(refetch).toHaveBeenCalled());
  });

  it('hides Respond once responded', () => {
    mountDetail(detail({ is_responded: true, responded_at: FUTURE }));
    renderDrawer();
    expect(
      screen.queryByRole('button', { name: /^Respond$/ }),
    ).not.toBeInTheDocument();
  });

  it('Resolve ticket asks to confirm first, then calls the resolve action and tells the worklist', async () => {
    const onResolved = vi.fn();
    mountDetail(detail({ is_responded: true }));
    renderDrawer({ onResolved });

    fireEvent.click(screen.getByRole('button', { name: /Resolve ticket/ }));
    expect(actOnDrawingRequest).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByRole('button', { name: /^Confirm$/ }));

    await waitFor(() =>
      expect(actOnDrawingRequest).toHaveBeenCalledWith('trk-1', 'resolve'),
    );
    await waitFor(() => expect(onResolved).toHaveBeenCalled());
    expect(refetch).toHaveBeenCalled();
  });

  it('disables Resolve ticket, and says whose it is, when the viewer cannot resolve', () => {
    mountDetail(detail({ can_resolve: false, is_assignee: false }));
    renderDrawer();

    const button = screen.getByRole('button', { name: /Resolve ticket/ });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('title', 'Assigned to Aina');
  });

  it('says the permission is missing, not whose it is, when the assignee cannot resolve', () => {
    mountDetail(detail({ can_resolve: false, is_assignee: true }));
    renderDrawer();

    const button = screen.getByRole('button', { name: /Resolve ticket/ });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('title', 'Your role cannot resolve SLA tasks');
  });

  it('stays open in the Resolved state with the badge, and offers no Respond or Resolve', () => {
    mountDetail(
      detail({ is_resolved: true, is_responded: true, resolved_at: FUTURE }),
    );
    renderDrawer();

    expect(screen.getByTestId('ticket-resolved-badge')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /Resolve ticket/ }),
    ).toBeDisabled();
    expect(
      screen.queryByRole('button', { name: /^Respond$/ }),
    ).not.toBeInTheDocument();
  });

  it('offers Reassign when the viewer holds the permission and the task has a team', () => {
    mountDetail(detail());
    renderDrawer();
    fireEvent.click(screen.getByTestId('ticket-reassign'));
    expect(screen.getByTestId('reassign-dialog')).toBeInTheDocument();
  });

  it('hides Reassign without the permission', () => {
    hasPermission.mockImplementation(
      (slug) => !String(slug).endsWith('.reassign'),
    );
    mountDetail(detail());
    renderDrawer();
    expect(screen.queryByTestId('ticket-reassign')).not.toBeInTheDocument();
  });
});

describe('InterventionTicketDrawer default variant is the chat panel, unchanged', () => {
  it('reads the chat ticket and never the media detail', () => {
    useInterventionTicket.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      refetch: vi.fn(),
    });
    mountDetail(undefined);
    render(
      <InterventionTicketDrawer ticketId="t-9" open onOpenChange={() => {}} />,
    );

    expect(useInterventionTicket).toHaveBeenCalledWith('t-9');
    expect(useMediaRequest).not.toHaveBeenCalled();
  });
});
