/**
 * Lane BULK-CONTACT-ACCESS, UAC U11 + U20: the pure helpers behind the Import access sheet dialog.
 * Red until lib/accessSheet.ts exists. Selection is opaque: it is only built by initialSelection /
 * confirmAllExact and read by toConfirmedPayload.
 */
import { describe, it, expect } from 'vitest';
import { initialSelection, confirmAllExact, toConfirmedPayload, resultCsv } from './accessSheet';

const account = (id: string, over: Record<string, unknown> = {}) => ({
  customer_id: id,
  customer_code: `300-${id}`,
  customer_name: `ALPHA ${id}`,
  company_code: 'SRT',
  is_active: true,
  sales_agent: 'AG ONE',
  sheet_agent: 'AG ONE',
  match: 'exact',
  score: 1,
  proposed: true,
  ...over,
});

const contact = (name: string, over: Record<string, unknown> = {}) => ({
  line: 2,
  name,
  phone: '+60100000001',
  in_crm: true,
  contact_id: `id-${name}`,
  role: 'owner',
  companies: ['SRT'],
  template: 'SRT owner',
  status: 'applied',
  skip_reason: null,
  changes: [],
  warnings: [],
  not_applied: [],
  ...over,
});

const preview = {
  dry_run: true,
  counts: { rows: 3, blocks: 3 },
  errors: [],
  blocks: [
    {
      key: 'alpha bath', dealer: 'ALPHA BATH SDN BHD', alt_dealers: [], companies: ['SRT', 'MCH'], status: 'exact', warnings: [],
      accounts: [account('a1'), account('a2'), account('a3', { is_active: false, proposed: false })],
      contacts: [contact('Ann')],
    },
    {
      key: 'beta tiles', dealer: 'BETA TILES SDN BHD', alt_dealers: [], companies: ['SRT'], status: 'pick', warnings: [],
      accounts: [account('b1', { match: 'candidate', score: 0.9, proposed: false })],
      contacts: [contact('Bob')],
    },
    { key: 'gamma', dealer: 'GAMMA SDN BHD', alt_dealers: [], companies: ['SRT'], status: 'none', warnings: [], accounts: [], contacts: [contact('Cy')] },
  ],
} as never;

describe('accessSheet helpers', () => {
  it('U11: initially no block is confirmed, so the payload is empty', () => {
    expect(toConfirmedPayload(initialSelection(preview))).toEqual({});
  });

  it('U11: Confirm all exact confirms every exact block with its ticked accounts only', () => {
    const sel = confirmAllExact(preview, initialSelection(preview));
    expect(toConfirmedPayload(sel)).toEqual({ 'alpha bath': ['a1', 'a2'] });
  });

  it('U10: an unticked (inactive) account is never in the payload; pick and none blocks stay out', () => {
    const payload = toConfirmedPayload(confirmAllExact(preview, initialSelection(preview)));
    expect(payload['alpha bath']).not.toContain('a3');
    expect(payload).not.toHaveProperty('beta tiles');
    expect(payload).not.toHaveProperty('gamma');
  });

  it('confirmAllExact does not mutate the selection it was given', () => {
    const start = initialSelection(preview);
    confirmAllExact(preview, start);
    expect(toConfirmedPayload(start)).toEqual({});
  });
});

describe('resultCsv', () => {
  const result = {
    dry_run: false,
    counts: { applied: 1, skipped: 1 },
    errors: [],
    blocks: [
      {
        key: 'k', dealer: '=HYPERLINK("x")', alt_dealers: [], companies: ['SRT'], status: 'exact', warnings: [], accounts: [],
        contacts: [
          contact('=cmd|calc', { phone: '+60100000001' }),
          contact('+plus', { status: 'skipped', skip_reason: 'not_in_crm', in_crm: false, contact_id: null }),
          contact('-minus'),
          contact('@at'),
          contact('Doe, John'),
        ],
      },
    ],
  } as never;

  it('U20: cells starting with = + - @ are prefixed with a single quote', () => {
    const csv = resultCsv(result);
    expect(typeof csv).toBe('string');
    for (const raw of ['=cmd|calc', '+plus', '-minus', '@at']) {
      expect(csv).toContain(`'${raw}`);
      expect(csv).not.toMatch(new RegExp(`(^|,|\\n)"?${raw.replace(/[|+]/g, '\\$&')}`));
    }
  });

  it('a cell holding a comma is quoted; one row per contact under a header', () => {
    const csv = resultCsv(result);
    expect(csv).toContain('"Doe, John"');
    expect(csv.trim().split(/\r?\n/).length).toBeGreaterThanOrEqual(6);
  });

  it('a skipped contact carries its reason', () => {
    expect(resultCsv(result)).toContain('not_in_crm');
  });
});

describe('resultCsv tab and carriage return', () => {
  const result = {
    dry_run: false,
    counts: {},
    errors: [],
    blocks: [
      {
        key: 'k', dealer: 'D', alt_dealers: [], companies: ['SRT'], status: 'exact', warnings: [], accounts: [],
        contacts: [contact('\tTabbed'), contact('\rReturned')],
      },
    ],
  } as never;

  it('U20: cells starting with a tab or a carriage return are prefixed with a single quote', () => {
    const csv = resultCsv(result);
    expect(csv).toContain("'\tTabbed");
    expect(csv).toContain("'\rReturned");
  });
});
