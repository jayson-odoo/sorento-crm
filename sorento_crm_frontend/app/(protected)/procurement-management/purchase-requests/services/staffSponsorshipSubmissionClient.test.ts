/**
 * PROJECT-STAGE-ACTIONS: the salesperson's sponsorship form, written by staff, talks to the
 * staff routes on behalf of the project's salesperson.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));

import { createStaffSponsorshipClient } from './staffSponsorshipSubmissionClient';

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

const project = { id: 'p1', owner_name: 'Ann Sales', owner_contact_id: 'c-ann' };

function bodyOf(call: unknown[]) {
  return JSON.parse(String((call[1] as RequestInit).body));
}

beforeEach(() => apiFetch.mockReset());

describe('staff sponsorship client', () => {
  it('speaks as the project salesperson', async () => {
    const me = await createStaffSponsorshipClient(project).fetchMe();
    expect(me.contact_id).toBe('c-ann');
    expect(me.name).toBe('Ann Sales');
  });

  it("pre-selects a set's admin default, as the salesperson's form does", async () => {
    apiFetch.mockResolvedValueOnce(
      json({ set_key: 'procurement_sales_type', options: [{ value: 'project', label: 'Project', keywords: [], is_active: true }], default_value: 'project' }),
    );
    const result = await createStaffSponsorshipClient(project).lookupSet('procurement_sales_type');
    expect(apiFetch.mock.calls[0][0]).toBe('/api/v1/lookup/by-binding?table=purchase_requests&column=sales_type');
    expect(result).toEqual({ options: [{ value: 'project', label: 'Project' }], defaultValue: 'project' });
  });

  it('Save draft creates a sponsorship form through the staff create, owned by the salesperson', async () => {
    apiFetch.mockResolvedValueOnce(json({ id: 'sf-1', status: 'draft' }, 201));
    const saved = await createStaffSponsorshipClient(project).saveDraft(
      'sponsorship_form',
      { customer_name: 'Acme', requested_by_contact_id: 'c-ann', project_id: 'p1' },
      [{ item_code: 'A-1', quantity: '2', unit_price: '10', total: '20' }],
    );
    expect(saved.id).toBe('sf-1');
    const [url, init] = apiFetch.mock.calls[0];
    expect(url).toBe('/api/v1/procurement/purchase-requests');
    expect((init as RequestInit).method).toBe('POST');
    expect(bodyOf(apiFetch.mock.calls[0])).toEqual({
      customer_name: 'Acme',
      requested_by_contact_id: 'c-ann',
      project_id: 'p1',
      request_type: 'sponsorship_form',
      contact_id: 'c-ann',
      products: [{ item_code: 'A-1', quantity: '2', unit_price: '10', total: '20' }],
    });
  });

  it('Save draft on a saved draft updates it', async () => {
    apiFetch.mockResolvedValueOnce(json({ id: 'sf-1' }));
    await createStaffSponsorshipClient(project).saveDraft('sponsorship_form', {}, undefined, 'sf-1');
    expect(apiFetch.mock.calls[0][0]).toBe('/api/v1/procurement/purchase-requests/sf-1');
    expect((apiFetch.mock.calls[0][1] as RequestInit).method).toBe('PUT');
  });

  it('Submit saves the latest values, then submits through the staff submit', async () => {
    apiFetch.mockResolvedValueOnce(json({ id: 'sf-1' })).mockResolvedValueOnce(json({ id: 'sf-1', status: 'submitted' }));
    const done = await createStaffSponsorshipClient(project).submitDraft('sponsorship_form', 'sf-1', { pic: 'Bob' }, []);
    expect(done.status).toBe('submitted');
    expect(apiFetch.mock.calls[0][0]).toBe('/api/v1/procurement/purchase-requests/sf-1');
    expect(apiFetch.mock.calls[1][0]).toBe('/api/v1/procurement/purchase-requests/sf-1/submit');
    expect((apiFetch.mock.calls[1][1] as RequestInit).method).toBe('POST');
  });

  it('a refused line keeps its line reference, so the form can say "Line 1: ..."', async () => {
    apiFetch.mockResolvedValueOnce(
      json({ message: 'Unit price is required.', detail: 'line:0', code: 'SPONSORSHIP_UNIT_PRICE_REQUIRED' }, 422),
    );
    const error = await createStaffSponsorshipClient(project)
      .saveDraft('sponsorship_form', {}, [{ item_code: 'A-1', quantity: '1' }])
      .catch((e: unknown) => e as Error & { fields?: string[] });
    expect(error.message).toBe('Unit price is required.');
    expect(error.fields).toEqual(['line:0']);
  });

  it('offers no AI Extract: there is no staff extract route for this form', () => {
    expect(createStaffSponsorshipClient(project).aiExtract).toBe(false);
  });

  it('Cancel and Submit go back to the project Sponsorship Form tab', () => {
    const paths = createStaffSponsorshipClient(project).paths!;
    expect(paths.home('sponsorship_form')).toBe('/project-sales/p1?tab=sponsorships');
    expect(paths.detail('sponsorship_form', 'sf-1')).toBe('/procurement-management/sponsorship-forms/sf-1');
  });
});
