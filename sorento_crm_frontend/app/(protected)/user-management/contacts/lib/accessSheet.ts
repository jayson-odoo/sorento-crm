import type {
  AccessSheetBlock,
  AccessSheetConfirmed,
  AccessSheetResult,
} from '@/services/contactAccessSheetService';

/** Per dealer block key: is it confirmed, and which account ids are ticked. Opaque to callers. */
export type AccessSheetSelection = {
  confirmed: Record<string, boolean>;
  ticked: Record<string, string[]>;
};

/** Proposed accounts ticked; nothing confirmed (U11: an unconfirmed dealer is skipped). */
export function initialSelection(preview: AccessSheetResult): AccessSheetSelection {
  const ticked: Record<string, string[]> = {};
  const confirmed: Record<string, boolean> = {};
  for (const block of preview.blocks) {
    ticked[block.key] = block.accounts.filter((a) => a.proposed).map((a) => a.customer_id);
    confirmed[block.key] = false;
  }
  return { confirmed, ticked };
}

export function confirmAllExact(preview: AccessSheetResult, sel: AccessSheetSelection): AccessSheetSelection {
  const confirmed = { ...sel.confirmed };
  for (const block of preview.blocks) if (block.status === 'exact') confirmed[block.key] = true;
  return { ...sel, confirmed };
}

export function setConfirmed(sel: AccessSheetSelection, key: string, value: boolean): AccessSheetSelection {
  return { ...sel, confirmed: { ...sel.confirmed, [key]: value } };
}

export function setTicked(sel: AccessSheetSelection, key: string, ids: string[]): AccessSheetSelection {
  return { ...sel, ticked: { ...sel.ticked, [key]: ids } };
}

export function toggleTicked(sel: AccessSheetSelection, key: string, id: string): AccessSheetSelection {
  const current = sel.ticked[key] ?? [];
  return setTicked(sel, key, current.includes(id) ? current.filter((i) => i !== id) : [...current, id]);
}

export function toConfirmedPayload(sel: AccessSheetSelection): AccessSheetConfirmed {
  const out: AccessSheetConfirmed = {};
  for (const [key, on] of Object.entries(sel.confirmed)) if (on) out[key] = [...(sel.ticked[key] ?? [])];
  return out;
}

export function allExactConfirmed(preview: AccessSheetResult, sel: AccessSheetSelection): boolean {
  const exact = preview.blocks.filter((b) => b.status === 'exact');
  return exact.length > 0 && exact.every((b) => sel.confirmed[b.key]);
}

function cell(value: unknown): string {
  let text = value === null || value === undefined ? '' : String(value);
  if (/^[=+\-@]/.test(text)) text = `'${text}`;
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function show(value: unknown): string {
  return Array.isArray(value) ? value.join('; ') : value === null || value === undefined ? '' : String(value);
}

const HEADER = ['Line', 'Name', 'Phone', 'Dealer', 'Status', 'Reason', 'Template', 'Changes', 'Warnings', 'Not applied'];

/** The result as a CSV for download. Cells starting with = + - @ are prefixed with a quote. */
export function resultCsv(result: AccessSheetResult): string {
  const lines = [HEADER.map(cell).join(',')];
  for (const block of result.blocks as AccessSheetBlock[]) {
    for (const c of block.contacts) {
      lines.push(
        [
          c.line,
          c.name,
          c.phone,
          block.dealer,
          c.status,
          c.skip_reason ?? '',
          c.template,
          c.changes.map((ch) => `${ch.facet}: ${show(ch.before)} -> ${show(ch.after)}`).join(' | '),
          c.warnings.join('; '),
          c.not_applied.join('; '),
        ]
          .map(cell)
          .join(','),
      );
    }
  }
  for (const e of result.errors) lines.push([e.line, '', '', '', 'skipped', 'row_error', '', e.reason, '', ''].map(cell).join(','));
  return lines.join('\n');
}
