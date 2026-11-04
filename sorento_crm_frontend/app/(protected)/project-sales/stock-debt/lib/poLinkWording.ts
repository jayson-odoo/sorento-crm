/**
 * AC-LINK-CRM-UI: what a PO link answer and the Decide menu say, in plain words (owner, Lavish
 * mock v1: "dont use jargon"). The Shared Service's codes are branched on here and never shown.
 */
import type { PoLinkCapabilities, PoLinkResult } from '../types/stockDebtSnapshot.types';

export type PoLinkKind = 'link' | 'unlink' | 'relink';

export interface PoLinkResultText {
  tone: 'ok' | 'warn' | 'error';
  title: string;
  text: string;
  /** The one follow-up the result offers: move the new line to its location, or resume. */
  action: 'relocate' | 'resume' | null;
}

const DONE_TITLE: Record<PoLinkKind, string> = {
  link: 'Linked',
  unlink: 'Unlinked',
  relink: 'Moved',
};
const FAIL_TITLE: Record<PoLinkKind, string> = {
  link: 'Not linked',
  unlink: 'Not unlinked',
  relink: 'Not moved',
};

function soLabel(r: PoLinkResult): string {
  if (!r.so_number) return 'This line';
  return r.so_line_no != null ? `${r.so_number} line ${r.so_line_no}` : r.so_number;
}

function poLabel(r: PoLinkResult): string {
  const qty = r.qty != null ? ` (${r.qty.toLocaleString()})` : '';
  return r.po_number ? `PO ${r.po_number}${qty}` : `the PO${qty}`;
}

/** One line's answer as a callout: title, sentence and the follow-up it offers. */
export function poLinkResultText(r: PoLinkResult, kind: PoLinkKind): PoLinkResultText {
  const so = soLabel(r);
  if (r.outcome === 'done') {
    const text =
      kind === 'unlink'
        ? `${so} is no longer covered by ${poLabel(r)}.`
        : `${so} now covered by ${poLabel(r)}.`;
    if (r.warnings.includes('LOCATION_NOT_MOVED')) {
      return {
        tone: 'warn',
        title: `${DONE_TITLE[kind]}, location not moved`,
        text: `${text} AutoCount kept the PO line at its old location.`,
        action: r.po_line_id ? 'relocate' : null,
      };
    }
    return { tone: 'ok', title: DONE_TITLE[kind], text, action: null };
  }
  if (r.outcome === 'needs_attention' || r.outcome === 'pending_verification') {
    return {
      tone: 'error',
      title: 'Needs attention',
      text: `${so}: AutoCount stopped part way.`,
      action: r.operation_id && r.po_line_id ? 'resume' : null,
    };
  }
  if (r.outcome === 'recovered') {
    return {
      tone: 'error',
      title: FAIL_TITLE[kind],
      text: `${so}: AutoCount put the PO line back as it was.`,
      action: null,
    };
  }
  let reason: string;
  if (r.error_code === 'VENDOR_UNSUPPORTED') reason = 'AutoCount cannot do this yet. Nothing was changed.';
  else if (r.error_code === 'WRITE_DISABLED' || r.error_code === 'WRITE_NOT_ALLOWED')
    reason = 'Changes to AutoCount are switched off here. Nothing was changed.';
  else if (r.error_code === 'DOC_STALE')
    reason = 'The PO changed in AutoCount since it was read. Nothing was changed; try again.';
  else if (r.error_code === 'ROW_ALREADY_LINKED') reason = 'The PO line is already linked. Nothing was changed.';
  else if (r.message) reason = r.message;
  else reason = 'AutoCount did not accept it. Nothing was changed.';
  return { tone: 'error', title: FAIL_TITLE[kind], text: `${so}: ${reason}`, action: null };
}

export interface MenuItemState {
  enabled: boolean;
  reason: string | null;
}

/** The Decide menu's PO items: on, or greyed with the reason (never hidden). */
export function poLinkMenu(input: {
  ticked: number;
  /** Ticked lines that already have a PO linked. */
  linked: number;
  capabilities: PoLinkCapabilities | null;
  loading: boolean;
}): { link: MenuItemState; unlink: MenuItemState; relink: MenuItemState } {
  const off = (reason: string): MenuItemState => ({ enabled: false, reason });
  if (input.ticked === 0) {
    const none = off('Tick the lines to decide on');
    return { link: none, unlink: none, relink: none };
  }
  if (!input.capabilities) {
    const wait = off(input.loading ? 'Checking AutoCount…' : 'Could not reach AutoCount');
    return { link: wait, unlink: wait, relink: wait };
  }
  const caps = input.capabilities;
  const from = (cap: { enabled: boolean; reason: string | null }, needsLink: boolean): MenuItemState => {
    if (!cap.enabled) return off(cap.reason ?? 'Waiting for AutoCount');
    if (needsLink && input.linked === 0) return off('No PO linked to the ticked lines');
    return { enabled: true, reason: null };
  };
  return {
    link: from(caps.split_link, false),
    unlink: from(caps.unlink_row, true),
    relink: from(caps.relink_row, true),
  };
}
