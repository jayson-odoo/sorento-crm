'use client';

import type { POAnnotation, POVersionLine } from '../../_shared/types/poIntake.types';
import { formatMyrExact, formatQty } from '../../_shared/lib/money';

/**
 * What accepting this note will do, in the line numbers and money on this document.
 *
 * This file used to also export the grid that listed document-level notes (ones naming no
 * line) below the PDF on the Documents tab. That grid is gone (owner hand test 25 Sep 2026,
 * item 4: "why does this exist? just show me the entire document") - a line-tied note now
 * lives only on its own line's popover in `POIntakeLinesGrid`, and a note naming no line has
 * nowhere left to review, so it neither blocks Confirm nor shows anywhere. This helper stayed
 * because both that popover and the accept confirmation dialog still need to say, in one
 * sentence, what accepting a note actually changes.
 */
export function describeAnnotationEffect(
  annotation: POAnnotation,
  // Defaults to none: a note naming no line has no lines to look up here, and neither of the
  // two remaining callers of this in `POIntakeLinesGrid` ever has one it does not already
  // pass explicitly.
  lines: POVersionLine[] = [],
): string {
  const json = (annotation.interpretation_json ?? {}) as Record<string, unknown>;
  const lineNos = Array.isArray(json.line_nos)
    ? (json.line_nos as unknown[]).map(Number).filter((value) => Number.isFinite(value))
    : annotation.refers_to_lines;
  const list = joinLineNos(lineNos);

  switch (annotation.interpretation) {
    case 'cancel_line': {
      if (lineNos.length === 0)
        return 'Cancels a line, but the line number was not read.';
      const named = lines.filter((line) => lineNos.includes(line.line_no));
      const detail = named
        .map(
          (line) =>
            `line ${line.line_no} (${line.stock_code_raw ?? 'no code'}, ${formatQty(line.qty)} ${line.uom_raw ?? ''}`.trim() +
            `, ${formatMyrExact(line.amount)})`,
        )
        .join('; ');
      return `Cancels ${detail || list}. The line stays on the record, marked cancelled, and drops out of our total.`;
    }
    case 'amend_code': {
      const code = typeof json.code === 'string' ? json.code : '';
      return code
        ? `Changes the code on ${list} to ${code}.`
        : `Changes the code on ${list}, but the new code was not read.`;
    }
    case 'amend_description': {
      const description = typeof json.description === 'string' ? json.description : '';
      return description
        ? `Changes the description on ${list} to "${description}".`
        : `Changes the description on ${list}, but the new wording was not read.`;
    }
    case 'successor_po': {
      const poNumber = typeof json.po_number === 'string' ? json.po_number : '';
      return poNumber
        ? `Records ${poNumber} as the PO that replaces this one. The link is made when that PO is uploaded.`
        : 'Names a replacement PO, but the number was not read.';
    }
    case 'signature':
      return 'Recorded as a signature. No line changes.';
    default:
      return 'Recorded as written. No line changes.';
  }
}

function joinLineNos(lineNos: number[]): string {
  if (lineNos.length === 0) return 'no lines';
  if (lineNos.length === 1) return `line ${lineNos[0]}`;
  const head = lineNos.slice(0, -1).join(', ');
  return `lines ${head} and ${lineNos[lineNos.length - 1]}`;
}
