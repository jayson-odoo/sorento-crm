/**
 * Access model S6 (AC-AM-2, AC-AM-4b, AC-AM-7). Red test: lib/chatbot-access/tree.ts does not exist.
 *
 * Contract pinned here for the coder:
 *   buildTree(registry, { roles, overrides }) -> Section[]
 *   Section = { key:'domains'|'reports', label, rows: Row[] }
 *   Row = { key, label, kind:'domain'|'report', checked, indeterminate, blocked, needs?,
 *           source:'role'|'added'|'removed'|null, roleNames:string[], children: Child[] }
 *   Child = { key, label, checked, source, roleNames }
 *   Domain row key = registry domain name; child/report key = field key.
 *   Role grants: role.domains (domain names), role.fields (field keys).
 *   Override: { domain_name, field_key: string|null, granted } (field_key null = the domain itself).
 *   diffGrants(initial, current) -> { count, payload:{domains,fields} }.
 */
import { describe, it, expect } from 'vitest';

import { buildTree, diffGrants } from './tree';

const registry = {
  domains: [
    { name: 'inventory', label: 'Stock', supported: true, access_section: null, escalation_agent_code: 'warehouse', escalation_team_code: 'wh',
      fields: [
        { key: 'inventory.sellable', label: 'Outstanding SO on stock (sellable)', kind: 'field' },
        { key: 'inventory.on_order', label: 'PO on order qty', kind: 'field' },
        { key: 'low_stock', label: 'Low stock report', kind: 'report' },
      ] },
    { name: 'order', label: 'Orders / DO', supported: true, access_section: null, escalation_agent_code: 'cs', escalation_team_code: 'cs',
      fields: [{ key: 'so_outstanding', label: 'Outstanding SO report', kind: 'report' }] },
    { name: 'incoming', label: 'Incoming stock', supported: true, access_section: null, escalation_agent_code: 'inc', escalation_team_code: 'inc',
      fields: [
        { key: 'incoming.eta', label: 'ETA', kind: 'field' },
        { key: 'incoming.consignee', label: 'Consignee', kind: 'field' },
      ] },
    { name: 'sales', label: 'Sales report', supported: true, access_section: 'reports', escalation_agent_code: 'cs', escalation_team_code: 'cs', fields: [] },
  ],
};

const purchasing = { id: 'r1', code: 'purchasing', name: 'Purchasing', domains: ['inventory', 'incoming'], fields: ['incoming.eta', 'inventory.sellable', 'inventory.on_order'] };

function sec(tree: ReturnType<typeof buildTree>, key: string) {
  return tree.find((s) => s.key === key)!;
}
function row(tree: ReturnType<typeof buildTree>, section: string, key: string) {
  return sec(tree, section).rows.find((r) => r.key === key)!;
}

describe('buildTree', () => {
  it('AC-AM-4b has Domains and Reports sections; a reports-section domain lists under Reports', () => {
    const t = buildTree(registry, { roles: [], overrides: [] });
    expect(t.map((s) => s.key)).toEqual(['domains', 'reports']);
    expect(sec(t, 'domains').rows.map((r) => r.key)).not.toContain('sales');
    expect(sec(t, 'reports').rows.map((r) => r.key)).toContain('sales');
  });

  it('AC-AM-4b a report-kind field lists under Reports with needs = owning domain label, not under its domain', () => {
    const t = buildTree(registry, { roles: [], overrides: [] });
    const low = row(t, 'reports', 'low_stock');
    expect(low.needs).toBe('Stock');
    expect(low.label).toBe('Low stock report');
    expect(row(t, 'domains', 'inventory').children.map((c) => c.key)).toEqual(['inventory.sellable', 'inventory.on_order']);
    expect(row(t, 'reports', 'so_outstanding').needs).toBe('Orders / DO');
  });

  it('AC-AM-4b a report is blocked while its owning domain is not granted; granting the report never grants the domain', () => {
    const t = buildTree(registry, { roles: [{ ...purchasing, domains: [], fields: ['low_stock'] }], overrides: [] });
    expect(row(t, 'reports', 'low_stock').blocked).toBe(true);
    expect(row(t, 'domains', 'inventory').checked).toBe(false);
    const t2 = buildTree(registry, { roles: [{ ...purchasing, fields: ['low_stock'] }], overrides: [] });
    expect(row(t2, 'reports', 'low_stock').blocked).toBe(false);
    expect(row(t2, 'reports', 'low_stock').checked).toBe(true);
  });

  it('AC-AM-7 role ticks carry source "role" and the role name', () => {
    const t = buildTree(registry, { roles: [purchasing], overrides: [] });
    const inv = row(t, 'domains', 'inventory');
    expect(inv.checked).toBe(true);
    expect(inv.source).toBe('role');
    expect(inv.roleNames).toEqual(['Purchasing']);
    expect(row(t, 'domains', 'order').checked).toBe(false);
    expect(row(t, 'domains', 'order').source).toBeNull();
  });

  it('AC-AM-7 an add override on a field no role grants is source "added"', () => {
    const t = buildTree(registry, {
      roles: [purchasing],
      overrides: [{ domain_name: 'incoming', field_key: 'incoming.consignee', granted: true }],
    });
    const kids = row(t, 'domains', 'incoming').children;
    expect(kids.find((c) => c.key === 'incoming.consignee')).toMatchObject({ checked: true, source: 'added' });
    expect(kids.find((c) => c.key === 'incoming.eta')).toMatchObject({ checked: true, source: 'role', roleNames: ['Purchasing'] });
  });

  it('AC-AM-5 a remove override on a role-granted field is unchecked and source "removed"', () => {
    const t = buildTree(registry, {
      roles: [purchasing],
      overrides: [{ domain_name: 'inventory', field_key: 'inventory.on_order', granted: false }],
    });
    expect(row(t, 'domains', 'inventory').children.find((c) => c.key === 'inventory.on_order')).toMatchObject({
      checked: false,
      source: 'removed',
    });
  });

  it('AC-AM-5 a domain-level remove override beats the role add', () => {
    const t = buildTree(registry, {
      roles: [purchasing],
      overrides: [{ domain_name: 'inventory', field_key: null, granted: false }],
    });
    expect(row(t, 'domains', 'inventory')).toMatchObject({ checked: false, source: 'removed' });
  });

  it('AC-AM-2 a granted domain with some fields unticked is indeterminate; all ticked is not', () => {
    const t = buildTree(registry, { roles: [purchasing], overrides: [] });
    expect(row(t, 'domains', 'incoming').indeterminate).toBe(true);
    expect(row(t, 'domains', 'inventory').indeterminate).toBe(false);
  });

  it('AC-AM-2 several roles list every granting role name', () => {
    const other = { id: 'r2', code: 'wh', name: 'Warehouse', domains: ['inventory'], fields: [] };
    const t = buildTree(registry, { roles: [purchasing, other], overrides: [] });
    expect(row(t, 'domains', 'inventory').roleNames).toEqual(['Purchasing', 'Warehouse']);
  });
});

describe('diffGrants', () => {
  it('AC-AM-2 counts only changed rows and returns the full-replace payload', () => {
    const initial = { domains: ['inventory'], fields: ['incoming.eta'] };
    const current = { domains: ['inventory', 'order'], fields: ['incoming.eta', 'incoming.consignee'] };
    const d = diffGrants(initial, current);
    expect(d.count).toBe(2);
    expect([...d.payload.domains].sort()).toEqual(['inventory', 'order']);
    expect([...d.payload.fields].sort()).toEqual(['incoming.consignee', 'incoming.eta']);
  });

  it('AC-AM-2 an untick counts as a change and no change counts zero', () => {
    const s = { domains: ['inventory', 'order'], fields: [] };
    expect(diffGrants(s, { domains: ['inventory'], fields: [] }).count).toBe(1);
    expect(diffGrants(s, { ...s }).count).toBe(0);
  });
});
