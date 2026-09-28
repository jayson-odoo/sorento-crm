/**
 * Issue #1328: `chatbot_eta_offset_applied` rides the contact GET and the
 * PUT .../chatbot body as `eta_offset_applied` on the card's profile, default on.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
const getContact = vi.fn();

vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));
vi.mock('./contactService', () => ({ getContact: (...a: unknown[]) => getContact(...a) }));

import { getContactChatbotProfile, saveContactChatbotProfile } from './contactChatbotService';

beforeEach(() => {
  apiFetch.mockReset();
  getContact.mockReset();
});

describe('contactChatbotService - ETA offset switch (#1328)', () => {
  it('reads the switch off the contact, and a contact without the field defaults on', async () => {
    getContact.mockResolvedValueOnce({ chatbot_eta_offset_applied: false });
    expect((await getContactChatbotProfile('c1')).eta_offset_applied).toBe(false);

    getContact.mockResolvedValueOnce({});
    expect((await getContactChatbotProfile('c1')).eta_offset_applied).toBe(true);
  });

  it('sends the switch as chatbot_eta_offset_applied on save', async () => {
    getContact.mockResolvedValueOnce({ chatbot_eta_offset_applied: true });
    const profile = await getContactChatbotProfile('c1');
    apiFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ chatbot_eta_offset_applied: false }), { status: 200 }),
    );

    const saved = await saveContactChatbotProfile('c1', { ...profile, eta_offset_applied: false });

    const body = JSON.parse(apiFetch.mock.calls[0][1].body);
    expect(body.chatbot_eta_offset_applied).toBe(false);
    expect(saved.eta_offset_applied).toBe(false);
  });
});
