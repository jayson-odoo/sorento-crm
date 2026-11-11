import React from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TownCards } from './TownCards';
import { TownLightbox } from './TownLightbox';
import { townTip } from '../lib/townTips';

/** TOWN-PROJECT-CITY (plan PLAN-town-project-city-11nov.md, "Phase 2 contract"): the split board, project sites,
 * trading houses. Invented names only. */
const SITE = {
  key: 'p1', name: 'Residensi Alpha', code: 'P-0101', stage: 'quoted', final_negotiation: true, state: 'Johor',
  launch_date: '2025-03-01', delivery_date: '2028-03-01', estimated_value: '1200000.00',
};
const TH = { key: 't1', name: 'TH Alpha Trading', state: 'Selangor', open_projects: 4, today_docs: 2 };
const FULL = {
  schema: 1, company_id: 'c', day: '2026-11-03', as_of: '2026-11-03T15:00:00+08:00', data_as_of: null, phase: 'day',
  today: {
    amount: '480.00', invoice_count: 6, credit_note_count: 0, customer_count: 4, dealer_customer_count: 3,
    split: { dealer: { amount: '300.00', invoice_count: 3 }, project: { amount: '150.00', invoice_count: 2 }, other: { amount: '30.00', invoice_count: 1 } },
  },
  shops: [], warehouses: [], reorder: { below_count: 0, set_count: 0 }, deliveries: { to_deliver: 2, project_orders: 1 },
  approvals: { total: 0, purchase_requests: 0, quotation_documents: 0 },
  projects: { open_count: 33, more: 32, dormant: 3, sites: [SITE] },
  trading_houses: { more: 0, rows: [TH] },
};
const { name: _n, code: _c, estimated_value: _v, ...ANON_SITE } = SITE;
const REDACTED = {
  ...FULL,
  today: { ...FULL.today, amount: undefined, split: { dealer: { invoice_count: 3 }, project: { invoice_count: 2 }, other: { invoice_count: 1 } } },
  projects: { ...FULL.projects, sites: [{ ...ANON_SITE, key: 'sabcdef012345' }] },
  trading_houses: { more: 0, rows: [{ key: 'sabcdef012346', state: 'Selangor', open_projects: 4, today_docs: 2 }] },
};

describe('TOWN-PROJECT-CITY: split board, sites, trading houses', () => {
  it('splits the sales card into dealers, projects and other, in RM for a full viewer', () => {
    render(<TownCards snapshot={FULL as never} />);
    expect(screen.getByText(/Dealers RM 300 · Projects RM 150 · Other RM 30/)).toBeTruthy();
  });

  it('splits by invoice counts when the viewer may not see amounts', () => {
    render(<TownCards snapshot={REDACTED as never} />);
    expect(screen.getByText(/Dealers 3 · Projects 2 · Other 1/)).toBeTruthy();
    expect(screen.queryByText(/RM/)).toBeNull();
  });

  it("opens a site: its name, our stage, final negotiation, state, its own timeline, value and the project's page", () => {
    render(<TownLightbox snapshot={FULL as never} target={{ kind: 'site', key: 'p1' }} onClose={() => undefined} />);
    expect(screen.getByText('Residensi Alpha · P-0101')).toBeTruthy();
    expect(screen.getAllByText('Quoted').length).toBeGreaterThan(0);
    expect(screen.getByText('Johor')).toBeTruthy();
    expect(screen.getByText(/Launch Mar 2025 · Delivery Mar 2028 · 56% of the way/)).toBeTruthy();
    expect(screen.getByText('RM 1,200,000.00')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Open project' }).getAttribute('href')).toBe('/project-sales/p1');
  });

  it('opens a site without a name, value or link for a viewer without amounts', () => {
    render(<TownLightbox snapshot={REDACTED as never} target={{ kind: 'site', key: 'sabcdef012345' }} onClose={() => undefined} />);
    expect(screen.getByText('Project site')).toBeTruthy();
    expect(screen.queryByText(/Residensi/)).toBeNull();
    expect(screen.queryByText(/RM/)).toBeNull();
    expect(screen.queryByRole('link', { name: 'Open project' })).toBeNull();
  });

  it('opens a trading house with its open projects and project invoices today', () => {
    render(<TownLightbox snapshot={FULL as never} target={{ kind: 'trading_house', key: 't1' }} onClose={() => undefined} />);
    expect(screen.getByText('TH Alpha Trading')).toBeTruthy();
    expect(screen.getByText('Selangor')).toBeTruthy();
    expect(screen.getByText('4')).toBeTruthy();
  });

  it('opens the projects sign: open, shown, more and dormant', () => {
    render(<TownLightbox snapshot={FULL as never} target={{ kind: 'projects' }} onClose={() => undefined} />);
    expect(screen.getByText('33 open projects')).toBeTruthy();
    expect(screen.getByText(/1 on the map · \+32 more · 3 dormant/)).toBeTruthy();
  });

  it('names sites and trading houses in the tooltip only when the snapshot carries the name', () => {
    expect(townTip(FULL as never, { kind: 'site', site: SITE as never })).toEqual({ title: 'Residensi Alpha · P-0101', detail: 'Quoted, final negotiation · frame going up' });
    expect(townTip(REDACTED as never, { kind: 'site', site: REDACTED.projects.sites[0] as never }).title).toBe('Project site');
    expect(townTip(FULL as never, { kind: 'trading_house', row: TH as never })).toEqual({ title: 'TH Alpha Trading', detail: '4 open projects · bought today' });
    expect(townTip(REDACTED as never, { kind: 'trading_house', row: REDACTED.trading_houses.rows[0] as never }).title).toBe('Trading house');
  });
});
