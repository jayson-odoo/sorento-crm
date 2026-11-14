/** Answer wording shared by the job page and the jobs list. */
const ANSWERS: Record<string, string> = {
  covered: 'Covered',
  expired: 'Expired',
  defect_not_covered: 'Defect not covered',
  no_term: 'No term',
  unknown: 'Unknown',
};

const SUMMARIES: Record<string, string> = {
  covered: 'Covered',
  partly_covered: 'Partly covered',
  not_covered: 'Not covered',
  unknown: 'Unknown',
};

function humanize(code: string): string {
  const text = code.replace(/_/g, ' ').trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : '-';
}

export function answerLabel(verdict: string): string {
  return ANSWERS[verdict] ?? humanize(verdict);
}

export function summaryLabel(summary: string | null): string {
  if (!summary) return '-';
  return SUMMARIES[summary] ?? humanize(summary);
}

export const SUMMARY_OPTIONS = Object.entries(SUMMARIES).map(([value, label]) => ({ value, label }));
