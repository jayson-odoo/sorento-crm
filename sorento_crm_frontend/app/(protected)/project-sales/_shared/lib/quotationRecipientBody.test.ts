/** PROJECT-PARTY-ROLES PR 2: what a proposal save sends about its "To". Names are invented. */
import { describe, expect, it } from 'vitest';
import { withRecipient } from './quotationRecipientBody';

const BLANKS = {
  recipient_name_snapshot: 'PGB CONTOH',
  recipient_address_snapshot: null,
  recipient_phone_snapshot: null,
  recipient_email_snapshot: null,
};

describe('withRecipient', () => {
  it('sends a newly picked party with its role and leaves unknown block fields to the server', () => {
    const out = withRecipient(BLANKS, { recipient_party_id: 'p-pgb', recipient_role: 'main_contractor' }, 'p-dev');
    expect(out).toEqual({
      recipient_name_snapshot: 'PGB CONTOH',
      recipient_party_id: 'p-pgb',
      recipient_role: 'main_contractor',
    });
  });

  it('sends nothing about the party when it did not change', () => {
    const out = withRecipient(BLANKS, { recipient_party_id: 'p-dev' }, 'p-dev');
    expect(out).toEqual(BLANKS);
    expect('recipient_party_id' in out).toBe(false);
  });

  it('a cleared party is sent as null and the typed block stays', () => {
    const out = withRecipient(BLANKS, { recipient_party_id: null }, 'p-dev');
    expect(out.recipient_party_id).toBeNull();
    expect(out.recipient_address_snapshot).toBeNull();
  });

  it('sends the Attn people with their party even when the party did not change', () => {
    const out = withRecipient({}, { recipient_party_id: 'p-dev', attn_contact_ids: ['c1', 'c2'] }, 'p-dev');
    expect(out).toEqual({ recipient_party_id: 'p-dev', attn_contact_ids: ['c1', 'c2'] });
  });

  it('a typed field on a new party is kept, only blanks are left out', () => {
    const out = withRecipient(
      { ...BLANKS, recipient_phone_snapshot: '03-1111' },
      { recipient_party_id: 'p-pgb' },
      null,
    );
    expect(out.recipient_phone_snapshot).toBe('03-1111');
    expect('recipient_email_snapshot' in out).toBe(false);
  });
});
