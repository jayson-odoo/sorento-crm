/**
 * UIUX-QUICK-WINS item 1: which OI detail header button is the ONE filled main action
 * (DESIGN-LANGUAGE.md section 6, one CTA per page). The other one shown renders outline.
 *
 * Reserve wins once something is staged (the staging is waiting to be sent) or when there is
 * nothing left to confirm; otherwise Confirm, the step every new OI waits for first.
 */
export function orderInquiryMainAction(state: {
  showConfirm: boolean;
  confirmDisabled: boolean;
  showReserve: boolean;
  stagedCount: number;
}): 'confirm' | 'reserve' | null {
  const { showConfirm, confirmDisabled, showReserve, stagedCount } = state;
  if (!showConfirm) return showReserve ? 'reserve' : null;
  if (!showReserve) return 'confirm';
  return stagedCount > 0 || confirmDisabled ? 'reserve' : 'confirm';
}
