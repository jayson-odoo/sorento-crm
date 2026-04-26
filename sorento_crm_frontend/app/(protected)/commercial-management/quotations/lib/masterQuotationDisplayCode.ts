/** Matches detail header: `QT-…-NN` when a working revision exists (same as quotation-revisions `revisionDisplayCode`). */

export function masterQuotationDisplayCode(row: {
  quotation_code: string;
  current_working_revision_number?: number | null;
}): string {
  const n = row.current_working_revision_number;
  if (n != null && Number.isFinite(Number(n))) {
    return `${row.quotation_code}-${n}`;
  }
  return row.quotation_code;
}
