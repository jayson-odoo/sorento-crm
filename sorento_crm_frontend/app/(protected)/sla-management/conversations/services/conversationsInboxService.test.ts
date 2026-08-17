import { beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * The contact-keyed inbox endpoints (UAC AC-N1 / AC-N2 / AC-N3).
 *
 * What matters here is the wire: which URL, which method, which body. The
 * outbound reply-to emulation was removed on 2026-08-16, so a send is text
 * (plus files) and nothing else - the backend still accepts the audit-only
 * `reply_to_*` pair, and nothing here may start sending it again.
 */
const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));
vi.mock('@/lib/api-client', () => ({
  extractApiError: vi.fn().mockResolvedValue('boom'),
}));

import {
  createContactComment,
  getContactWindow,
  listConversations,
  replyToContact,
  sendContactTemplateMessage,
} from './conversationsInboxService';

const BASE = '/api/v1/sla-management/conversations';

function ok(body: unknown) {
  return { ok: true, json: async () => body };
}

beforeEach(() => {
  apiFetch.mockReset();
});

describe('listConversations', () => {
  it('passes the tab, the trimmed query, the cursor and the limit', async () => {
    apiFetch.mockResolvedValue(ok({ items: [] }));
    await listConversations({ tab: 'mentioned', q: '  aisyah ', cursor: 'c1', limit: 30 });
    expect(apiFetch).toHaveBeenCalledWith(
      `${BASE}?tab=mentioned&q=aisyah&cursor=c1&limit=30`,
    );
  });
});

describe('createContactComment', () => {
  it('posts a CONTACT-scoped note', async () => {
    apiFetch.mockResolvedValue(ok({ id: 'c1', tracking_id: null }));

    const created = await createContactComment('10025531', {
      body: 'ping @Ben',
      mentioned_user_ids: ['u-2'],
    });

    expect(apiFetch).toHaveBeenCalledWith(
      `${BASE}/10025531/comments`,
      expect.objectContaining({ method: 'POST' }),
    );
    expect(JSON.parse(apiFetch.mock.calls[0][1].body)).toEqual({
      body: 'ping @Ben',
      mentioned_user_ids: ['u-2'],
    });
    expect(created.tracking_id).toBeNull();
  });

  it('surfaces the backend message on a refusal', async () => {
    apiFetch.mockResolvedValue({ ok: false, status: 400 });
    await expect(createContactComment('10025531', { body: '' })).rejects.toThrow('boom');
  });
});

describe('getContactWindow', () => {
  it('reads the window and the out-of-window template', async () => {
    apiFetch.mockResolvedValue(
      ok({ window: { open: false, expires_at: null }, chat_template: { configured: true } }),
    );

    const state = await getContactWindow('10025531');

    expect(apiFetch).toHaveBeenCalledWith(`${BASE}/10025531/window`);
    expect(state.window.open).toBe(false);
    expect(state.chat_template.configured).toBe(true);
  });
});

describe('sendContactTemplateMessage', () => {
  it('posts the template id and its positional params', async () => {
    apiFetch.mockResolvedValue(ok({ ok: true, stamped_ticket_id: 'tkt-1' }));

    const result = await sendContactTemplateMessage('10025531', {
      template_id: 'tpl-1',
      params: { '1': 'Aisyah' },
    });

    expect(apiFetch).toHaveBeenCalledWith(
      `${BASE}/10025531/template-message`,
      expect.objectContaining({ method: 'POST' }),
    );
    expect(JSON.parse(apiFetch.mock.calls[0][1].body)).toEqual({
      template_id: 'tpl-1',
      params: { '1': 'Aisyah' },
    });
    expect(result.stamped_ticket_id).toBe('tkt-1');
  });
});

describe('replyToContact', () => {
  it('sends only the text on the JSON lane - no reply-to emulation', async () => {
    apiFetch.mockResolvedValue(ok({ sent_as: 'text', stamped_ticket_id: null }));

    await replyToContact('10025531', { text: 'hello' });

    expect(JSON.parse(apiFetch.mock.calls[0][1].body)).toEqual({ text: 'hello' });
  });

  it('sends only text + files on the multipart lane', async () => {
    apiFetch.mockResolvedValue(ok({ sent_as: 'attachment', stamped_ticket_id: null }));
    const file = new File(['x'], 'quote.pdf', { type: 'application/pdf' });

    await replyToContact('10025531', { text: 'see attached', files: [file] });

    const form = apiFetch.mock.calls[0][1].body as FormData;
    expect(form.get('text')).toBe('see attached');
    expect(form.get('reply_to_message_id')).toBeNull();
    expect(form.get('reply_to_excerpt')).toBeNull();
    expect(form.getAll('files')).toHaveLength(1);
  });
});
