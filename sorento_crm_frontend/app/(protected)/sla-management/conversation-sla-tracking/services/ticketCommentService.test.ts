import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

import { apiFetch } from '@/lib/api';
import { createTicketComment, getTicketComments } from './ticketCommentService';

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
});

describe('getTicketComments', () => {
  it('GETs this ticket comments endpoint', async () => {
    mockApiFetch.mockResolvedValue(jsonResponse([{ id: 'c1', body: 'note' }]));

    const comments = await getTicketComments('t1');

    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/v1/sla-management/conversation-sla-tracking/t1/comments',
    );
    expect(comments[0].body).toBe('note');
  });

  it('throws the extracted error message on failure', async () => {
    mockApiFetch.mockResolvedValue(jsonResponse({ detail: 'not found' }, false, 404));

    await expect(getTicketComments('missing')).rejects.toThrow('not found');
  });
});

describe('createTicketComment', () => {
  it('POSTs the body and the mentioned user ids', async () => {
    mockApiFetch.mockResolvedValue(jsonResponse({ id: 'c1' }, true, 201));

    await createTicketComment('t1', { body: '@Team Lead look', mentioned_user_ids: ['u-1'] });

    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/v1/sla-management/conversation-sla-tracking/t1/comments',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ body: '@Team Lead look', mentioned_user_ids: ['u-1'] }),
      }),
    );
  });

  it('defaults the mentions to an empty list', async () => {
    mockApiFetch.mockResolvedValue(jsonResponse({ id: 'c1' }, true, 201));

    await createTicketComment('t1', { body: 'plain note' });

    expect(mockApiFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        body: JSON.stringify({ body: 'plain note', mentioned_user_ids: [] }),
      }),
    );
  });

  it('throws the extracted error message on failure', async () => {
    mockApiFetch.mockResolvedValue(
      jsonResponse({ message: 'One or more mentioned users no longer exist.' }, false, 400),
    );

    await expect(createTicketComment('t1', { body: 'x' })).rejects.toThrow(
      'One or more mentioned users no longer exist.',
    );
  });
});
