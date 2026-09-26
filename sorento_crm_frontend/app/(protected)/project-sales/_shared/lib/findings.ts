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

/**
 * What holds Publish, and the ONE rule for it (owner lesson (e), S6 hand test): this order's
 * own hard findings with no `acknowledged_at`. The server's `blocking_findings`
 * (`project_so_draft_service.py`) filters the same three things, so the count under Publish,
 * the "Need attention" rows and the server's refusal cannot disagree. A schedule-level finding
 * never blocks: the server keys those to the (PO, schedule) pair, never to an order.
 */
export function publishBlockers(orderFindings: ProjectSalesOrderFinding[]): ProjectSalesOrderFinding[] {
  return orderFindings.filter((finding) => finding.severity === 'hard' && !finding.acknowledged_at);
}

/** Where a finding was raised: on this sales order, or on the schedule it was split from. */
export type FindingSource = 'sales_order' | 'schedule';

export const FINDING_SOURCE_LABEL: Record<FindingSource, string> = {
  sales_order: 'Sales order',
  schedule: 'Schedule',
};

export interface FlagMember {
  finding: ProjectSalesOrderFinding;
  source: FindingSource;
}

/** One entry in a row's Flag: one or more findings cleared by one Dismiss. */
export interface FlagItem {
  key: string;
  /** The most severe member's severity. */
  severity: FindingSeverity;
  /** False once dismissed; a dismissed item keeps its reason readable and loses its action. */
  open: boolean;
  members: FlagMember[];
  /** The sales order line the item sits on, or null for a row of its own. */
  lineId: string | null;
}

const SEVERITY_RANK: Record<FindingSeverity, number> = { hard: 3, warn: 2, info: 1 };

function mostSevere(members: FlagMember[]): FindingSeverity {
  return members.reduce<FindingSeverity>(
    (worst, member) =>
      SEVERITY_RANK[member.finding.severity] > SEVERITY_RANK[worst] ? member.finding.severity : worst,
    'info',
  );
}

function normalisedCode(value: unknown): string {
  return typeof value === 'string' ? value.toUpperCase().replace(/[^A-Z0-9]/g, '') : '';
}

/**
 * Every finding on the sales order page as the Flag items its rows carry (S7-3).
 *
 * Open findings collapse per `collapseFindings` within their own source. R23 then folds a
 * schedule's unmapped column (`unresolved_product`, keyed by `customer_code_raw`) into the
 * order's `schedule_short` finding for the product that column names, since the column is why
 * the schedule places nothing: one item, both sentences, one Dismiss. Where two products fit
 * one column the longer code wins (CB1178A over CB1178). Dismissed findings stay one item each.
 */
export function buildFlagItems(
  orderFindings: ProjectSalesOrderFinding[],
  scheduleFindings: ProjectSalesOrderFinding[],
): FlagItem[] {
  const toItems = (findings: ProjectSalesOrderFinding[], source: FindingSource): FlagItem[] => {
    const byId = new Map(findings.map((finding) => [finding.id, finding]));
    return collapseFindings(findings).map((row) => {
      const members = row.ids.map((id) => ({ finding: byId.get(id) as ProjectSalesOrderFinding, source }));
      return {
        key: `${source}:${row.key}`,
        severity: mostSevere(members),
        open: true,
        members,
        lineId: members[0].finding.line_id ?? null,
      };
    });
  };

  const orderItems = toItems(orderFindings.filter((finding) => !finding.acknowledged_at), 'sales_order');
  const scheduleItems = toItems(scheduleFindings.filter((finding) => !finding.acknowledged_at), 'schedule');

  const shortByCode = orderItems
    .filter((item) => item.members[0].finding.code === 'schedule_short')
    .map((item) => ({ item, code: normalisedCode(item.members[0].finding.detail_json?.product_code) }))
    .filter((entry) => entry.code.length > 0)
    .sort((a, b) => b.code.length - a.code.length);

  const unpaired = scheduleItems.filter((item) => {
    const first = item.members[0].finding;
    if (first.code !== 'unresolved_product') return true;
    const column = normalisedCode(first.detail_json?.customer_code_raw);
    const cause = column ? shortByCode.find((entry) => column.includes(entry.code)) : undefined;
    if (!cause) return true;
    cause.item.members.push(...item.members);
    cause.item.severity = mostSevere(cause.item.members);
    return false;
  });

  const dismissed: FlagItem[] = [
    ...orderFindings.map((finding) => ({ finding, source: 'sales_order' as const })),
    ...scheduleFindings.map((finding) => ({ finding, source: 'schedule' as const })),
  ]
    .filter((member) => Boolean(member.finding.acknowledged_at))
    .map((member) => ({
      key: `${member.source}:dismissed:${member.finding.id}`,
      severity: member.finding.severity,
      open: false,
      members: [member],
      lineId: member.finding.line_id ?? null,
    }));

  return [...orderItems, ...unpaired, ...dismissed];
}

/** An item a person has to act on: open, and not merely for information. */
export function needsAttention(item: FlagItem): boolean {
  return item.open && item.severity !== 'info';
}

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
