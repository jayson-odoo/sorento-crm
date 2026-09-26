/**
 * The shared pieces every review screen's findings render with (R3, R20, S3): one severity
 * set with its label and colour, and a collapse rule so duplicates about the same subject
 * read as one row with a count instead of a card each. There is never a second findings
 * surface to keep in sync with this one - a screen's own table renders the row directly.
 */
import type { FindingSeverity, ProjectSalesOrderFinding } from '../types/projectSalesOrder.types';

/** The three-severity pill's words (S3-1), the only ones a Flag cell ever shows. */
export const FINDING_SEVERITY_LABEL: Record<FindingSeverity, string> = {
  hard: 'Blocks publish',
  warn: 'Needs acknowledgement',
  info: 'Info',
};

/** The Badge variant behind each pill - set directly rather than inferred from the label text. */
export const FINDING_SEVERITY_BADGE_VARIANT: Record<FindingSeverity, 'destructive' | 'warning' | 'secondary'> = {
  hard: 'destructive',
  warn: 'warning',
  info: 'secondary',
};

export interface CollapsedFinding {
  /** The collapse key: `${code}::${subjectKey}`, or the lone finding's own id when it has no subject key. */
  key: string;
  code: string;
  severity: FindingSeverity;
  /** The first member's sentence - the collapsed row's own text. */
  detail: string;
  /** Every underlying finding id this row stands for, in the order they were passed in. */
  ids: string[];
  count: number;
}

/**
 * The subject a finding is about, first present wins (S3-3): `line_id`, then
 * `detail_json.customer_code_raw` (a schedule column - a code repeated across areas keeps
 * one row per area because each area's column carries its own raw customer code), then
 * `detail_json.product_code`, then `detail_json.line_no`. `null` when none is present, which
 * keeps the finding out of every collapse.
 */
function subjectKeyOf(finding: ProjectSalesOrderFinding): string | null {
  if (finding.line_id) return `line:${finding.line_id}`;
  const detailJson = finding.detail_json;
  const customerCode = typeof detailJson?.customer_code_raw === 'string' ? detailJson.customer_code_raw : null;
  if (customerCode) return `customer_code:${customerCode}`;
  const productCode = typeof detailJson?.product_code === 'string' ? detailJson.product_code : null;
  if (productCode) return `product_code:${productCode}`;
  const lineNo = detailJson?.line_no;
  if (typeof lineNo === 'number') return `line_no:${lineNo}`;
  return null;
}

/**
 * One row per distinct (code, subject) pair, each carrying every underlying finding id it
 * stands for. A finding with no subject key never collapses, even with an identical code.
 */
export function collapseFindings(findings: ProjectSalesOrderFinding[]): CollapsedFinding[] {
  const order: string[] = [];
  const groups = new Map<string, ProjectSalesOrderFinding[]>();

  findings.forEach((finding, index) => {
    const subjectKey = subjectKeyOf(finding);
    const key = subjectKey ? `${finding.code}::${subjectKey}` : `__no-collapse-${index}-${finding.id}`;
    const group = groups.get(key);
    if (group) {
      group.push(finding);
    } else {
      groups.set(key, [finding]);
      order.push(key);
    }
  });

  return order.map((key) => {
    const members = groups.get(key) as ProjectSalesOrderFinding[];
    const first = members[0];
    return {
      key,
      code: first.code,
      severity: first.severity,
      detail: first.detail,
      ids: members.map((member) => member.id),
      count: members.length,
    };
  });
}
