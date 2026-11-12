/**
 * AC-QTSO-CRM: the fixed sentences the screens show around an AutoCount write. The answer's own
 * wording (done, refused, stale) is composed by the server and arrives in the result's message,
 * so the codes are branched on there and never shown here.
 */
export const AUTOCOUNT_WAITING_TEXT = 'Waiting for AutoCount';
export const AUTOCOUNT_SWITCHED_OFF_HERE = 'Changes to AutoCount are switched off here';
export const AUTOCOUNT_UNREACHABLE_TEXT = 'Could not reach AutoCount';
export const AUTOCOUNT_PENDING_TEXT =
  'Sent; AutoCount has not confirmed yet. It will show after the next sync.';
export const AUTOCOUNT_NOT_ACCEPTED_TEXT = 'The customer has not accepted this quotation yet';
export const AUTOCOUNT_NOT_IN_AUTOCOUNT_TEXT = 'Not in AutoCount yet';
export const AUTOCOUNT_ALREADY_CANCELLED_TEXT = 'Already cancelled in AutoCount';
