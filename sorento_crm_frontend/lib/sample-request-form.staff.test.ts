/**
 * SAMPLE-REQUEST-V2 slice 1: the staff form's state rules (card rules 1-4, owner answers Q2-Q4).
 * Ship to is a party, the contact comes from it, the customer is a debtor, "For" and the free
 * phone / note pair are not written by the staff form.
 */
import { describe, expect, it } from 'vitest';
import {
  EMPTY_FORM,
  blankLine,
  staffPayloadFromState,
  stateFromDetail,
  validateStaff,
  withShipToParty,
  withShipToContacts,
  type FormState,
} from './sample-request-form';
import type { SampleRequestDetail } from '@/types/sampleRequest';

const ready = (over: Partial<FormState> = {}): FormState => ({
  ...EMPTY_FORM,
  customer_id: 'c1',
  customer_label: 'NUSANTARA BUILDERS SDN BHD',
  project_id: 'p1',
  project_label: 'PPF2611007 - Residensi Taman Seri Murni',
  delivery_date: '2026-11-18',
  delivery_mode: 'driver',
  ship_to_party_id: 'party-1',
  ship_to_name: 'Bintang Trading Sdn Bhd',
  ship_to_address: 'No. 12, Jalan Perindustrian 3, Klang',
  lines: [{ ...blankLine(), product_id: 'prod-1', label: 'BS-6021-WH' }],
  ...over,
});

describe('withShipToParty', () => {
  it('fills name and the party address, and clears the old contact', () => {
    const before = ready({
      ship_to_contact_ids: ['k1'],
      site_contact_name: 'Mei Ling Tan',
      site_contact_phone: '012-345 6789',
    });
    const next = withShipToParty(before, {
      id: 'party-2',
      name: 'Arkitek Lima & Rakan',
      address: 'Jalan Kajang',
      role: 'consultant',
      siteAddress: 'Lot 22, Kajang',
    });
    expect(next.ship_to_party_id).toBe('party-2');
    expect(next.ship_to_name).toBe('Arkitek Lima & Rakan');
    expect(next.ship_to_address).toBe('Jalan Kajang');
    expect(next.ship_to_role).toBe('consultant');
    expect(next.ship_to_contact_ids).toEqual([]);
    expect(next.site_contact_name).toBe('');
    expect(next.site_contact_phone).toBe('');
  });

  it('a party without an address takes the project site address', () => {
    const next = withShipToParty(ready(), {
      id: 'party-3',
      name: 'No Address Sdn Bhd',
      address: null,
      role: null,
      siteAddress: 'Lot 22, Kajang',
    });
    expect(next.ship_to_address).toBe('Lot 22, Kajang');
  });

  it('clearing the party clears name, address and contact', () => {
    const next = withShipToParty(ready({ site_contact_name: 'X' }), null);
    expect(next.ship_to_party_id).toBe('');
    expect(next.ship_to_name).toBe('');
    expect(next.ship_to_address).toBe('');
    expect(next.site_contact_name).toBe('');
  });
});

describe('withShipToContacts (owner Q3 a)', () => {
  it('prints several as "A & B" with the first one\'s phone', () => {
    const next = withShipToContacts(ready(), [
      { id: 'k1', name: 'Mei Ling Tan', phone: '0123456789' },
      { id: 'k2', name: 'Ravi Kumar', phone: null },
    ]);
    expect(next.ship_to_contact_ids).toEqual(['k1', 'k2']);
    expect(next.site_contact_name).toBe('Mei Ling Tan & Ravi Kumar');
    expect(next.site_contact_phone).not.toBe('');
  });

  it('no contacts clears the contact person', () => {
    const next = withShipToContacts(ready({ site_contact_name: 'Old' }), []);
    expect(next.site_contact_name).toBe('');
    expect(next.ship_to_contact_ids).toEqual([]);
  });
});

describe('validateStaff', () => {
  it('a ready request has no problems', () => {
    expect(validateStaff(ready(), { requireProject: false })).toEqual({});
  });

  it('a typed customer is not enough (rule 1)', () => {
    const errors = validateStaff(ready({ customer_id: '', customer_name: 'typed' }), {
      requireProject: false,
    });
    expect(errors.customer_id).toBeTruthy();
  });

  it('a typed Ship To without a party is not enough (rule 2)', () => {
    const errors = validateStaff(ready({ ship_to_party_id: '', ship_to_name: 'site office' }), {
      requireProject: false,
    });
    expect(errors.ship_to_party_id).toBeTruthy();
  });

  it('a party not on the project needs its role', () => {
    const errors = validateStaff(ready({ ship_to_needs_role: true, ship_to_role: '' }), {
      requireProject: false,
    });
    expect(errors.ship_to_role).toBeTruthy();
  });

  it('the shipping address is required', () => {
    const errors = validateStaff(ready({ ship_to_address: '  ' }), { requireProject: false });
    expect(errors.ship_to_address).toBeTruthy();
  });

  it('still needs a date, a delivery mode and an item', () => {
    const errors = validateStaff(ready({ delivery_date: '', delivery_mode: '', lines: [] }), {
      requireProject: false,
    });
    expect(Object.keys(errors).sort()).toEqual(['delivery_date', 'delivery_mode', 'lines']);
  });
});

describe('staffPayloadFromState', () => {
  it('sends the party, its role and contacts; the server prints name and contact from them', () => {
    const body = staffPayloadFromState(
      ready({ ship_to_role: 'trading_house', ship_to_contact_ids: ['k1'], site_contact_name: 'Mei' }),
    );
    expect(body.ship_to_party_id).toBe('party-1');
    expect(body.ship_to_role).toBe('trading_house');
    expect(body.ship_to_contact_ids).toEqual(['k1']);
    expect(body.ship_to_address).toBe('No. 12, Jalan Perindustrian 3, Klang');
    expect('ship_to_name' in body).toBe(false);
    expect('site_contact_name' in body).toBe(false);
    expect('site_contact_phone' in body).toBe(false);
  });

  it('never writes "For" or the contact note, and never a typed customer (rules 1, 3, 4)', () => {
    const body = staffPayloadFromState(
      ready({ scope_note: 'show unit', site_contact_note: 'call first', customer_name: 'typed' }),
    );
    expect('scope_note' in body).toBe(false);
    expect('site_contact_note' in body).toBe(false);
    expect(body.customer_name ?? null).toBeNull();
  });

  it('an empty address is left to the server (party or site address)', () => {
    const body = staffPayloadFromState(ready({ ship_to_address: '' }));
    expect('ship_to_address' in body).toBe(false);
  });
});

describe('stateFromDetail (card example E)', () => {
  it('an old free-text request keeps its typed Ship To as a hint, with no party', () => {
    const state = stateFromDetail({
      id: 'r1',
      request_no: 'SR-000118',
      status: 'draft',
      ship_to_name: 'site office, Lot 22',
      ship_to_party_id: null,
      lines: [],
    } as unknown as SampleRequestDetail);
    expect(state.ship_to_party_id).toBe('');
    expect(state.ship_to_typed_before).toBe('site office, Lot 22');
  });

  it('a request with a party loads the party', () => {
    const state = stateFromDetail({
      id: 'r2',
      request_no: 'SR-000231',
      status: 'draft',
      ship_to_name: 'Bintang Trading Sdn Bhd',
      ship_to_party_id: 'party-1',
      ship_to_role: 'trading_house',
      lines: [],
    } as unknown as SampleRequestDetail);
    expect(state.ship_to_party_id).toBe('party-1');
    expect(state.ship_to_role).toBe('trading_house');
    expect(state.ship_to_typed_before).toBe('');
  });
});
