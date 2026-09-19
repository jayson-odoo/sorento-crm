/**
 * ONE rule for "does this compare summary count as a perfect match", shared by
 * `AutocountPullReview.compareSummaryLine` and `PullCompareTab.summaryHeadline` (captain
 * ruling, Phase 3 fix round, V-1) - a batch missing rows entirely (`only_in_excel` /
 * `only_in_pull` > 0) is never "100% match" even when every row that DID line up agreed.
 */
export interface CompareMatchSummary {
  matched: number;
  total: number;
  only_in_excel: number;
  only_in_pull: number;
}

export function isCompareFullMatch(summary: CompareMatchSummary): boolean {
  return (
    summary.matched === summary.total &&
    summary.only_in_excel === 0 &&
    summary.only_in_pull === 0
  );
}
