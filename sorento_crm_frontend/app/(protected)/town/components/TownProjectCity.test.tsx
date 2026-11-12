import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TownCards } from './TownCards';
import { TownLightbox } from './TownLightbox';
import { townTip, type TipSubject } from '../lib/townTips';
import { splitParts } from '../lib/townFormat';
import { stageColor, stageLabel } from '../lib/townMap';

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
const ANON_SITE = { key: SITE.key, stage: SITE.stage, final_negotiation: SITE.final_negotiation, state: SITE.state, launch_date: SITE.launch_date, delivery_date: SITE.delivery_date };
const REDACTED = {
  ...FULL,
  today: { ...FULL.today, amount: undefined, split: { dealer: { invoice_count: 3 }, project: { invoice_count: 2 }, other: { invoice_count: 1 } } },
  projects: { ...FULL.projects, sites: [{ ...ANON_SITE, key: 'opaque-site-1' }] },
  trading_houses: { more: 0, rows: [{ key: 'opaque-house-1', state: 'Selangor', open_projects: 4, today_docs: 2 }] },
};

describe('TOWN-PROJECT-CITY: split board, sites, trading houses', () => {
  it('splits the sales card into dealers, projects and other, in RM for a full viewer', () => {
    render(<TownCards snapshot={FULL as never} />);
    // owner rule (no ' · ' joining two values, crew 12 Nov): each part is its own labelled item
    expect(screen.getByText('Dealers RM 300')).toBeTruthy();
    expect(screen.getByText('Projects RM 150')).toBeTruthy();
    expect(screen.getByText('Other RM 30')).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/·/);
    expect(splitParts(FULL.today as never)).toEqual(['Dealers RM 300', 'Projects RM 150', 'Other RM 30']);
  });

  it('splits by invoice counts when the viewer may not see amounts', () => {
    render(<TownCards snapshot={REDACTED as never} />);
    expect(screen.getByText('Dealers 3')).toBeTruthy();
    expect(screen.getByText('Other 1')).toBeTruthy();
    expect(screen.queryByText(/RM/)).toBeNull();
  });

  it("opens a site: its name, our stage, final negotiation, state, its own timeline, value and the project's page", () => {
    render(<TownLightbox snapshot={FULL as never} target={{ kind: 'site', key: 'p1' }} onClose={() => undefined} />);
    expect(screen.getByRole('dialog').querySelector('h2')?.textContent).toBe('Residensi Alpha');
    expect(screen.getByText('Code')).toBeTruthy();
    expect(screen.getByText('P-0101')).toBeTruthy();
    expect(screen.getAllByText('Quoted').length).toBeGreaterThan(0);
    expect(screen.getByText('Johor')).toBeTruthy();
    const row = (label: string) => screen.getByText(label).closest('tr')?.textContent;
    expect(row('Launch')).toBe('LaunchMar 2025');
    expect(row('Delivery')).toBe('DeliveryMar 2028');
    expect(row('Progress')).toBe('Progress56% of the way');
    expect(screen.getByRole('dialog').textContent).not.toMatch(/·/);
    expect(screen.getByText('RM 1,200,000.00')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Open project' }).getAttribute('href')).toBe('/project-sales/p1');
  });

  it('opens a site without a name, value or link for a viewer without amounts', () => {
    render(<TownLightbox snapshot={REDACTED as never} target={{ kind: 'site', key: 'opaque-site-1' }} onClose={() => undefined} />);
    expect(screen.getByRole('dialog').querySelector('h2')?.textContent).toBe('Project site');
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
    expect(screen.getByRole('dialog').querySelector('h2')?.textContent).toBe('33 open projects');
    const row = (label: string) => screen.getByText(label).closest('tr')?.textContent;
    expect(row('On the map')).toBe('On the map1');
    expect(row('More')).toBe('More32');
    expect(row('Dormant')).toBe('Dormant3');
    // a site's stage and state on lines of their own, never joined with a dot
    const site = screen.getByText('Residensi Alpha').closest('tr') as HTMLElement;
    expect(site.querySelectorAll('td:last-child > div')).toHaveLength(2);
    // crew pass 6d4572c6: the value cell never wraps word by word ("PO / Received / State not / set"); the name truncates instead
    expect((site.querySelector('td:last-child') as HTMLElement).className).toMatch(/whitespace-nowrap/);
    expect(screen.getByRole('dialog').textContent).not.toMatch(/·/);
  });

  it('names sites and trading houses in the tooltip only when the snapshot carries the name', () => {
    expect(townTip(FULL as never, { kind: 'site', site: SITE as never })).toEqual({
      title: 'Residensi Alpha', detail: 'Code: P-0101\nStage: Quoted\nFinal negotiation: Yes\nBuilding: frame going up',
    });
    expect(townTip(REDACTED as never, { kind: 'site', site: REDACTED.projects.sites[0] as never }).title).toBe('Project site');
    expect(townTip(FULL as never, { kind: 'trading_house', row: TH as never })).toEqual({ title: 'TH Alpha Trading', detail: 'Open projects: 4\nProject invoice today: Yes' });
    expect(townTip(REDACTED as never, { kind: 'trading_house', row: REDACTED.trading_houses.rows[0] as never }).title).toBe('Trading house');
  });

  it('names a stage exactly as the CRM does, even one the map has never heard of (crew pass, 11 Nov)', () => {
    const custom = { ...SITE, stage: 'sponsorship_form', stage_label: 'Sponsorship Form', stage_color: '#7c3aed' };
    const renamed = { ...SITE, key: 'p2', stage: 'specified', stage_label: 'Quotation', stage_color: null };
    const snap = { ...FULL, projects: { ...FULL.projects, sites: [custom, renamed] } };
    render(<TownLightbox snapshot={snap as never} target={{ kind: 'site', key: 'p1' }} onClose={() => undefined} />);
    expect(screen.getAllByText('Sponsorship Form').length).toBeGreaterThan(0);
    expect(stageLabel(renamed)).toBe('Quotation');
    expect(stageLabel({ stage: 'final_negotiation' })).toBe('Final negotiation');
    expect(stageLabel({ stage: null })).toBe('Stage not set');
    expect(townTip(snap as never, { kind: 'site', site: custom as never }).detail).toMatch(/^Code: P-0101\nStage: Sponsorship Form\n/);
  });

  it("colours a stage's flag with the CRM's colour, else a known default, else grey", () => {
    expect(stageColor({ stage: 'x', stage_color: '#7c3aed' })).toBe(0x7c3aed);
    expect(stageColor({ stage: 'quoted', stage_color: null })).toBe(0xf59e0b);
    expect(stageColor({ stage: 'sponsorship_form', stage_color: 'not-a-colour' })).toBe(0x9ca3af);
  });

  it('lists anonymous sites in the projects popup without duplicate React keys', () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const two = { ...REDACTED, projects: { ...REDACTED.projects, sites: [REDACTED.projects.sites[0], { ...REDACTED.projects.sites[0], key: 'opaque-site-2' }] } };
    render(<TownLightbox snapshot={two as never} target={{ kind: 'projects' }} onClose={() => undefined} />);
    expect(error.mock.calls.flat().join(' ')).not.toMatch(/same key/);
    error.mockRestore();
  });

  it('clamps a long project title: 2 lines as the popup title, 1 line in a list, the full text on hover (owner rule, 28 Oct)', () => {
    const long = 'Cadangan Pembangunan '.repeat(27).trim();
    const snap = { ...FULL, projects: { ...FULL.projects, sites: [{ ...SITE, name: long }] } };
    const { unmount } = render(<TownLightbox snapshot={snap as never} target={{ kind: 'site', key: 'p1' }} onClose={() => undefined} />);
    const title = screen.getByRole('dialog').querySelector('h2 [title]') as HTMLElement;
    expect(title.className).toMatch(/line-clamp-2/);
    expect(title.getAttribute('title')).toBe(long);
    // crew pass (12 Nov): the code has its own row, so no clamp can cut it
    expect(screen.getByText('P-0101')).toBeTruthy();
    unmount();
    render(<TownLightbox snapshot={snap as never} target={{ kind: 'projects' }} onClose={() => undefined} />);
    const row = Array.from(screen.getByRole('dialog').querySelectorAll('td [title]')).find((el) => el.getAttribute('title') === long) as HTMLElement;
    expect(row.className).toMatch(/truncate/);
    expect(row.getAttribute('title')).toBe(long);
  });

  it('lists the dealers bought today without duplicate React keys when names are hidden', () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const shops = Array.from({ length: 4 }, (_, i) => ({ key: `opaque-shop-${i}`, kind: 'shop', account_label: null, today_docs: 1 }));
    const snap = { ...REDACTED, shops, today: { ...REDACTED.today, dealer_customer_count: 4 } };
    render(<TownLightbox snapshot={snap as never} target={{ kind: 'bought' }} onClose={() => undefined} />);
    expect(error.mock.calls.flat().join(' ')).not.toMatch(/same key/);
    error.mockRestore();
  });

  it('always lists the estimated value for a full viewer, "-" when the project has none', () => {
    const snap = { ...FULL, projects: { ...FULL.projects, sites: [{ ...SITE, estimated_value: null }] } };
    render(<TownLightbox snapshot={snap as never} target={{ kind: 'site', key: 'p1' }} onClose={() => undefined} />);
    const row = screen.getByText('Estimated value').closest('tr') as HTMLElement;
    expect(row.textContent).toMatch(/Estimated value-$/);
  });

  it('never joins two values with a dot in any tooltip: one fact per line (owner rule, crew 12 Nov)', () => {
    const snap = {
      ...FULL,
      incoming: { incoming: 3, late: 2, next_eta: null, shipments: [] },
    };
    const subjects: TipSubject[] = [
      { kind: 'sales' }, { kind: 'port' }, { kind: 'projects' }, { kind: 'coaster' },
      { kind: 'site', site: SITE as never }, { kind: 'trading_house', row: TH as never },
      { kind: 'shipment', row: { shipment_number: 'ZZT-1', eta: '2026-11-09', products: 2, supplier: 'Acme Trading', late: true } as never },
      { kind: 'lorry', customer: { key: null, name: 'Acme Trading', orders: 2 } as never },
    ];
    for (const s of subjects) {
      const tip = townTip(snap as never, s);
      expect(`${tip.title}\n${tip.detail}`).not.toMatch(/·/);
    }
    expect(townTip(snap as never, { kind: 'sales' }).detail).toBe('Sold: RM 480\nInvoices: 6');
    expect(townTip(snap as never, { kind: 'port' }).detail).toBe('Incoming: 3\nLate: 2');
  });
});
