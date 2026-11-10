/**
 * UIUX-QUICK-WINS item 5: why the quotation form's Save button is disabled, in plain words,
 * shown under the button (playbook "blocked action says why"; no pulse, minimal UI). Null when
 * nothing blocks it. Saving itself is not a block: the button already reads "Saving...".
 */
export function quotationSaveBlockedReason(state: {
  viewOnly: boolean;
  discarding: boolean;
  failed: boolean;
  loading: boolean;
  letterReady: boolean;
  columnsBusy: boolean;
}): string | null {
  if (state.viewOnly) return 'This draft is open somewhere else. Reload to edit it here.';
  if (state.discarding) return 'This draft is being discarded.';
  if (state.failed) return 'This quotation could not be loaded.';
  if (state.loading) return 'Still loading the quotation.';
  if (!state.letterReady) return 'Still loading the cover letter.';
  if (state.columnsBusy) return 'Waiting for the column change to finish.';
  return null;
}
