import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

const resolveConversationSLATracking = vi.fn();
vi.mock('./conversationSLATrackingService', () => ({
  resolveConversationSLATracking: (...a: unknown[]) => resolveConversationSLATracking(...a),
}));

import { apiFetch } from '@/lib/api';
import {
  getInterventionTicket,
  resolveInterventionTicket,
  sendInterventionTicketMessage,
} from './interventionTicketService';

const mockApiFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

function jsonResponse(body: unknown, ok = true, status = 200) {
  return {
    ok,
    status,
    headers: { get: () => 'application/json' },
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

beforeEach(() => {
  mockApiFetch.mockReset();
  resolveConversationSLATracking.mockReset();
});

describe('getInterventionTicket', () => {
  it('GETs the ticket detail endpoint', async () => {
    mockApiFetch.mockResolvedValue(jsonResponse({ id: 't1', contact_name: 'Aisyah' }));
    const detail = await getInterventionTicket('t1');
    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/v1/sla-management/conversation-sla-tracking/t1/ticket',
    );
    expect(detail.contact_name).toBe('Aisyah');
  });

  it('throws the extracted error message on failure', async () => {
    mockApiFetch.mockResolvedValue(jsonResponse({ detail: 'not found' }, false, 404));
    await expect(getInterventionTicket('missing')).rejects.toThrow('not found');
  });
});

// FINDING 9: there is deliberately NO thread fetcher here. The drawer reads the
// shared getSlaTrackingConversation / useSlaTrackingConversation (same route,
// same query key as the SLA detail page's conversation panel), so a send from
// the drawer refreshes both surfaces and cursor pagination is not lost to a
// second copy.
describe('thread fetching', () => {
  it('exports no thread fetcher of its own', async () => {
    const mod = await import('./interventionTicketService');
    expect('getInterventionTicketThread' in mod).toBe(false);
  });
});

describe('sendInterventionTicketMessage', () => {
  it('sends JSON when there are no attachments', async () => {
    mockApiFetch.mockResolvedValue(
      jsonResponse({ sent_as: 'text', rendered_text: 'hi', flattened: false, window: { open: true, expires_at: null } }),
    );
    const result = await sendInterventionTicketMessage('t1', { text: 'hi' });
    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/v1/sla-management/conversation-sla-tracking/t1/ticket/send',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    const [, init] = mockApiFetch.mock.calls[0];
    expect(JSON.parse(init.body as string)).toEqual({ text: 'hi' });
    expect(result.sent_as).toBe('text');
  });

  it('sends multipart/form-data (no explicit Content-Type) when there are attachments', async () => {
    mockApiFetch.mockResolvedValue(
      jsonResponse({ sent_as: 'attachment', rendered_text: '', flattened: false, window: { open: true, expires_at: null } }),
    );
    const file = new File(['x'], 'photo.jpg', { type: 'image/jpeg' });
    await sendInterventionTicketMessage('t1', {
      text: 'see attached',
      attachments: [file],
      reply_to_message_id: '123',
      reply_to_excerpt: 'earlier message',
    });
    const [, init] = mockApiFetch.mock.calls[0];
    expect(init.body).toBeInstanceOf(FormData);
    expect(init.headers).toBeUndefined();
    const fd = init.body as FormData;
    expect(fd.get('text')).toBe('see attached');
    expect(fd.get('reply_to_message_id')).toBe('123');
    expect(fd.get('reply_to_excerpt')).toBe('earlier message');
    expect(fd.getAll('files')).toHaveLength(1);
  });

  it('throws the extracted error message on failure', async () => {
    mockApiFetch.mockResolvedValue(jsonResponse({ detail: 'window closed' }, false, 422));
    await expect(sendInterventionTicketMessage('t1', { text: 'hi' })).rejects.toThrow(
      'window closed',
    );
  });
});

describe('resolveInterventionTicket', () => {
  it('delegates to the shared resolve route', async () => {
    resolveConversationSLATracking.mockResolvedValue(undefined);
    await resolveInterventionTicket('t1');
    expect(resolveConversationSLATracking).toHaveBeenCalledWith('t1');
  });
});
