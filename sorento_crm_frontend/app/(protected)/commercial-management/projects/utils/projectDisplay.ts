/** Display code for project headers (no backend numbering yet). */
export function formatProjectDisplayCode(projectId: string): string {
  const compact = projectId.replace(/-/g, '').slice(0, 10).toUpperCase();
  return `PRJ-${compact}`;
}

/** Badge-style classes for workflow stage chips (detail + edit headers). */
export function projectStageHeaderClass(stageCode: string | null | undefined): string {
  const c = (stageCode || '').toLowerCase();
  if (c.includes('complet')) return 'border-0 bg-emerald-100 text-emerald-800 hover:bg-emerald-100';
  if (c.includes('cancel') || c.includes('inactive')) return 'border-0 bg-[#ffe2e2] text-[#9f0712] hover:bg-[#ffe2e2]';
  if (c.includes('plan') || c.includes('progress') || c.includes('active'))
    return 'border-0 bg-[#dbeafe] text-[#1447e6] hover:bg-[#dbeafe]';
  return 'border-0 bg-zinc-100 text-zinc-800 hover:bg-zinc-100';
}
