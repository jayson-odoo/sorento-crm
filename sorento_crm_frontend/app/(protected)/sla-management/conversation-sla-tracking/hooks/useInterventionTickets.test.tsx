/**
 * `useSendInterventionTicketMessage` - who refreshes after a ticket reply.
 *
 * Exactly ONE thing may trigger the post-send reload. The hook used to
 * invalidate the ticket + thread keys while the drawer ALSO refetched both
 * explicitly, so every reply fired both GETs twice - two Respond.io round trips
 * for one message. The drawer keeps the trigger (it also owns the delayed
 * pulses that chase delivery ticks); the hook does not touch the cache.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { useSendInterventionTicketMessage } from './useInterventionTickets';

const sendInterventionTicketMessage = vi.fn();
vi.mock('../services/interventionTicketService', () => ({
  getInterventionTicket: vi.fn(),
  resolveInterventionTicket: vi.fn(),
  sendInterventionTicketMessage: (...a: unknown[]) => sendInterventionTicketMessage(...a),
}));

const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock('@/lib/toast', () => ({
  toast: {
    success: (...a: unknown[]) => toastSuccess(...a),
    error: (...a: unknown[]) => toastError(...a),
  },
}));

let queryClient: QueryClient;

function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

describe('useSendInterventionTicketMessage', () => {
  it('invalidates nothing: the drawer owns the single post-send refresh', async () => {
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
    sendInterventionTicketMessage.mockResolvedValue({ sent_as: 'text', attachments: null });

    const { result } = renderHook(() => useSendInterventionTicketMessage('t1'), { wrapper });
    await result.current.mutateAsync({ text: 'hello' });

    await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith('Message sent'));
    expect(invalidate).not.toHaveBeenCalled();
  });

  it('says nothing when a partial send already reported a failed file', async () => {
    sendInterventionTicketMessage.mockResolvedValue({
      sent_as: 'attachment',
      attachments: { delivered: ['a.pdf'], failed: { filename: 'b.pdf', error: 'boom' } },
    });

    const { result } = renderHook(() => useSendInterventionTicketMessage('t1'), { wrapper });
    await result.current.mutateAsync({ text: '', attachments: [new File(['x'], 'a.pdf')] });

    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it('says nothing when files went up and none came back delivered', async () => {
    // The silent-degrade case: a 200 with no delivered attachments. The
    // composer raises the error and keeps the file staged; a success toast
    // beside it would contradict the screen.
    sendInterventionTicketMessage.mockResolvedValue({ sent_as: 'text', attachments: null });

    const { result } = renderHook(() => useSendInterventionTicketMessage('t1'), { wrapper });
    await result.current.mutateAsync({
      text: 'here is the photo',
      attachments: [new File(['x'], 'photo.jpg')],
    });

    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it('names the template path when the reply went out as a template', async () => {
    sendInterventionTicketMessage.mockResolvedValue({ sent_as: 'template', attachments: null });

    const { result } = renderHook(() => useSendInterventionTicketMessage('t1'), { wrapper });
    await result.current.mutateAsync({ text: 'hello' });

    await waitFor(() =>
      expect(toastSuccess).toHaveBeenCalledWith('Delivered as a template message'),
    );
  });
});
