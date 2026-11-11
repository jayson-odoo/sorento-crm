/**
 * AC-LINK-CRM-UI: the result of a PO link, in plain words (owner, Lavish v1: no system terms).
 * Written before `poLinkWording.ts` exists.
 */
import { describe, expect, it } from 'vitest';
import { poLinkResultText, poLinkMenu } from './poLinkWording';
import type { PoLinkCapabilities, PoLinkResult } from '../types/stockDebtSnapshot.types';

function result(over: Partial<PoLinkResult>): PoLinkResult {
  return {
    sales_order_line_id: 'x',
    so_number: 'SO425045',
    so_line_no: 140,
    po_number: '202609-S0029',
    qty: 120,
    outcome: 'done',
    error_code: null,
    warnings: [],
    message: '',
    operation_id: null,
    company_code: 'SRT',
    po_line_id: 'pol-new',
    ...over,
  };
}

const CAPS: PoLinkCapabilities = {
  split_link: { enabled: true, reason: null },
  link_row: { enabled: false, reason: 'Waiting for AutoCount' },
  unlink_row: { enabled: false, reason: 'Waiting for AutoCount' },
  relink_row: { enabled: false, reason: 'Waiting for AutoCount' },
};

describe('poLinkResultText', () => {
  it('done reads "Linked" with the SO line and the PO', () => {
    expect(poLinkResultText(result({}), 'link')).toEqual({
      tone: 'ok',
      title: 'Linked',
      text: 'SO425045 line 140 now covered by PO 202609-S0029 (120).',
      action: null,
    });
  });

  it('a location that did not move is a warning with Move', () => {
    const out = poLinkResultText(result({ warnings: ['LOCATION_NOT_MOVED'] }), 'link');
    expect(out.tone).toBe('warn');
    expect(out.title).toBe('Linked, location not moved');
    expect(out.action).toBe('relocate');
  });

  it('waiting for AutoCount says nothing changed', () => {
    const out = poLinkResultText(
      result({ outcome: 'refused', error_code: 'VENDOR_UNSUPPORTED' }),
      'link',
    );
    expect(out).toMatchObject({ tone: 'error', title: 'Not linked', action: null });
    expect(out.text).toBe('SO425045 line 140: AutoCount cannot do this yet. Nothing was changed.');
  });

  it('needs attention offers Resume', () => {
    const out = poLinkResultText(
      result({ outcome: 'needs_attention', operation_id: 'op-9' }),
      'link',
    );
    expect(out).toMatchObject({ tone: 'error', title: 'Needs attention', action: 'resume' });
  });

  it('a refusal shows AutoCount own message when it gives one', () => {
    const out = poLinkResultText(
      result({ outcome: 'vendor_error', error_code: 'VENDOR_REFUSED', message: 'Line is received' }),
      'link',
    );
    expect(out.text).toBe('SO425045 line 140: Line is received');
  });

  it('unlink and move use their own words', () => {
    expect(poLinkResultText(result({}), 'unlink').title).toBe('Unlinked');
    expect(poLinkResultText(result({}), 'relink').title).toBe('Moved');
  });

  it('never prints a system code', () => {
    for (const r of [
      result({ outcome: 'refused', error_code: 'ROW_ALREADY_LINKED' }),
      result({ outcome: 'pending_verification', error_code: 'READBACK_MISMATCH' }),
    ]) {
      const out = poLinkResultText(r, 'link');
      expect(`${out.title} ${out.text}`).not.toMatch(/[A-Z]{3,}_[A-Z]/);
    }
  });
});

describe('poLinkMenu', () => {
  it('nothing ticked: every item greyed with "Tick the lines to decide on"', () => {
    const menu = poLinkMenu({ ticked: 0, linked: 0, capabilities: CAPS, loading: false });
    expect(menu.link).toEqual({ enabled: false, reason: 'Tick the lines to decide on' });
  });

  it('link follows split_link; unlink and move need a linked line and the capability', () => {
    const menu = poLinkMenu({ ticked: 2, linked: 1, capabilities: CAPS, loading: false });
    expect(menu.link).toEqual({ enabled: true, reason: null });
    expect(menu.unlink).toEqual({ enabled: false, reason: 'Waiting for AutoCount' });
    expect(menu.relink).toEqual({ enabled: false, reason: 'Waiting for AutoCount' });
  });

  it('unlink on lines with no PO says so', () => {
    const on = { ...CAPS, unlink_row: { enabled: true, reason: null } };
    const menu = poLinkMenu({ ticked: 2, linked: 0, capabilities: on, loading: false });
    expect(menu.unlink).toEqual({ enabled: false, reason: 'No PO linked to the ticked lines' });
  });

  it('every ticked line already covered: Link greyed "Already covered by PO …"', () => {
    const menu = poLinkMenu({
      ticked: 1, linked: 1, capabilities: CAPS, loading: false, coveredBy: ['FXT-1104d-1'],
    });
    expect(menu.link).toEqual({ enabled: false, reason: 'Already covered by PO FXT-1104d-1' });
  });

  it('while AutoCount is being asked, items wait', () => {
    const menu = poLinkMenu({ ticked: 1, linked: 0, capabilities: null, loading: true });
    expect(menu.link).toEqual({ enabled: false, reason: 'Checking AutoCount…' });
    expect(menu.change).toEqual({ enabled: false, reason: 'Checking AutoCount…' });
  });

  it('Change PO needs link and unlink from AutoCount, and one PO line on every ticked line', () => {
    const on = { ...CAPS, unlink_row: { enabled: true, reason: null } };
    expect(poLinkMenu({ ticked: 2, linked: 2, singleLinked: 2, capabilities: CAPS, loading: false }).change)
      .toEqual({ enabled: false, reason: 'Waiting for AutoCount' });
    expect(poLinkMenu({ ticked: 2, linked: 2, singleLinked: 1, capabilities: on, loading: false }).change)
      .toEqual({ enabled: false, reason: 'Each ticked line needs exactly one PO linked' });
    expect(poLinkMenu({ ticked: 2, linked: 2, singleLinked: 2, capabilities: on, loading: false }).change)
      .toEqual({ enabled: true, reason: null });
    // A covered line greys Link but not Change.
    const menu = poLinkMenu({
      ticked: 1, linked: 1, singleLinked: 1, capabilities: on, loading: false, coveredBy: ['202609-S0029'],
    });
    expect(menu.link.enabled).toBe(false);
    expect(menu.change.enabled).toBe(true);
  });
});
