/**
 * PM-SIMPLIFY AC-P2: the PO page's one header button is whatever comes next, in order:
 * confirm the PO, add or confirm the delivery schedule, build the sales orders, publish
 * them. Nothing once every order from this PO is out. Replaces the next-step card whose
 * links dropped the PO and made the user pick it again (D4).
 */

export type PONextStep =
  | { kind: 'confirm-po'; label: string; versionId: string }
  | { kind: 'upload-schedule'; label: string }
  | { kind: 'confirm-schedule'; label: string; versionId: string }
  | { kind: 'build'; label: string; scheduleVersionId: string }
  | { kind: 'publish'; label: string; count: number }
  | { kind: 'none' };

interface VersionLike {
  id: string;
  version_no: number;
  confirmed_at?: string | null;
  created_at?: string | null;
}

/** Newest by upload time, then by number: schedule revisions can come from two schedules. */
export function latestVersion<T extends VersionLike>(versions: T[]): T | null {
  if (versions.length === 0) return null;
  return [...versions].sort(
    (a, b) =>
      (b.created_at ?? '').localeCompare(a.created_at ?? '') || b.version_no - a.version_no,
  )[0];
}

export function poNextStep({
  poVersions,
  scheduleVersions,
  salesOrderStatuses,
  hasLines,
}: {
  poVersions: VersionLike[];
  scheduleVersions: VersionLike[];
  /** Status of every sales order built from this PO. */
  salesOrderStatuses: string[];
  /** A hand-keyed PO (no document) needs its lines before anything else. */
  hasLines: boolean;
}): PONextStep {
  const latestPo = latestVersion(poVersions);
  if (latestPo && !latestPo.confirmed_at) {
    return { kind: 'confirm-po', label: 'Confirm PO', versionId: latestPo.id };
  }
  if (!latestPo && !hasLines) return { kind: 'none' };

  const latestSchedule = latestVersion(scheduleVersions);
  if (!latestSchedule) return { kind: 'upload-schedule', label: 'Upload delivery schedule' };
  if (!latestSchedule.confirmed_at) {
    return {
      kind: 'confirm-schedule',
      label: 'Confirm schedule',
      versionId: latestSchedule.id,
    };
  }

  if (salesOrderStatuses.length === 0) {
    return {
      kind: 'build',
      label: 'Build sales orders',
      scheduleVersionId: latestSchedule.id,
    };
  }
  const live = new Set(['published', 'amended', 'adopted']);
  const unpublished = salesOrderStatuses.filter((status) => !live.has(status)).length;
  if (unpublished > 0) {
    return {
      kind: 'publish',
      label: `Publish ${unpublished} sales order${unpublished === 1 ? '' : 's'}`,
      count: unpublished,
    };
  }
  return { kind: 'none' };
}
