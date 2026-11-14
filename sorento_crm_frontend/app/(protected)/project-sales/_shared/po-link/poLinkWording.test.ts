/**
 * AC-LINK-CRM-UI: the result of a PO link, in plain words (owner, Lavish v1: no system terms).
 * Written before `poLinkWording.ts` exists.
 */
import { describe, expect, it } from 'vitest';
import { poLinkResultText, poLinkMenu } from './poLinkWording';
import type { PoLinkCapabilities, PoLinkResult } from '../../stock-debt/types/stockDebtSnapshot.types';

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

describe('poLinkMenu: move', () => {
  it('Move PO needs a linked line and the relink capability', () => {
    const menu = poLinkMenu({ ticked: 2, linked: 1, capabilities: CAPS, loading: false });
    expect(menu.relink).toEqual({ enabled: false, reason: 'Waiting for AutoCount' });
    const on = { ...CAPS, relink_row: { enabled: true, reason: null } };
    expect(poLinkMenu({ ticked: 2, linked: 0, capabilities: on, loading: false }).relink)
      .toEqual({ enabled: false, reason: 'No PO linked to the ticked lines' });
    expect(poLinkMenu({ ticked: 2, linked: 1, capabilities: on, loading: false }).relink.enabled).toBe(true);
  });
});

describe('Change PO answers (STOCKDEBT-LIVE-ACTIONS review, unlink first)', () => {
  it('a link refused after the old PO was unlinked says the line is now uncovered', () => {
    const text = poLinkResultText(
      result({ outcome: 'refused', error_code: 'DOC_STALE', action: 'link', unlinked_po: 'PO-OLD' }),
      'link',
    );
    expect(text.title).toBe('Not linked');
    expect(text.text).toMatch(/It was unlinked from PO PO-OLD, so the line is now uncovered\.$/);
  });

  it('a link that stopped part way says so, and still offers Resume', () => {
    const text = poLinkResultText(
      result({ outcome: 'needs_attention', operation_id: 'op-1', action: 'link', unlinked_po: 'PO-OLD' }),
      'link',
    );
    expect(text.text).toBe(
      'SO425045 line 140: AutoCount stopped part way. It was unlinked from PO PO-OLD, so the line is now uncovered.',
    );
    expect(text.action).toBe('resume');
  });

  it('a done answer adds nothing', () => {
    expect(poLinkResultText(result({ action: 'link', unlinked_po: null }), 'link').text).toBe(
      'SO425045 line 140 now covered by PO 202609-S0029 (120).',
    );
  });
});

describe('poLinkMenu: one manage state (owner, 13 Nov 18:55)', () => {
  it('returns manage and relink, not link / change / unlink', () => {
    const menu = poLinkMenu({ ticked: 1, linked: 0, capabilities: CAPS, loading: false }) as unknown as Record<string, unknown>;
    expect(Object.keys(menu).sort()).toEqual(['manage', 'relink']);
  });

  it('manage is on whenever AutoCount answered, whatever the individual capabilities say', () => {
    const menu = poLinkMenu({ ticked: 2, linked: 0, capabilities: CAPS, loading: false }) as unknown as Record<string, { enabled: boolean }>;
    expect(menu.manage.enabled).toBe(true);
  });

  it('a fully covered line is not a reason to grey it', () => {
    const menu = poLinkMenu({
      ticked: 1, linked: 1, capabilities: CAPS, loading: false, coveredBy: ['202609-S0029'],
    }) as unknown as Record<string, { enabled: boolean }>;
    expect(menu.manage.enabled).toBe(true);
  });

  it('is greyed with the reason when nothing is ticked, while AutoCount is checked, or when it cannot be reached', () => {
    const none = poLinkMenu({ ticked: 0, linked: 0, capabilities: CAPS, loading: false }) as unknown as Record<string, unknown>;
    expect(none.manage).toEqual({ enabled: false, reason: 'Tick the lines to decide on' });
    const loading = poLinkMenu({ ticked: 1, linked: 0, capabilities: null, loading: true }) as unknown as Record<string, unknown>;
    // OI-PO-LINK B: the popup reads only the CRM copies, so the wait is not on AutoCount.
    expect(loading.manage).toEqual({ enabled: false, reason: 'Getting the PO lines' });
    const down = poLinkMenu({ ticked: 1, linked: 0, capabilities: null, loading: false }) as unknown as Record<string, unknown>;
    expect(down.manage).toEqual({ enabled: false, reason: 'Could not load the PO lines' });
  });
});
