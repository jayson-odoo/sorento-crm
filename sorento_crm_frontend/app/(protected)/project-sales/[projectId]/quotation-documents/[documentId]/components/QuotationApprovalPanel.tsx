'use client';

import * as React from 'react';
import { ShieldAlert, ShieldCheck } from 'lucide-react';
import { isBlockedByApproval, isWithManager } from '../../../../_shared/lib/quotationDecision';
import type { QuotationDocument } from '../../../../_shared/services/quotationDocumentService';

/** The RIGHT to decide a quotation approval; who decides each request is its routed approver. */
export const APPROVE_PERMISSION = 'projects.quotations.approve';

export { isBlockedByApproval };

function BlockLine({ children }: { children: React.ReactNode }) {
  return <p className="min-w-0 text-sm text-foreground">{children}</p>;
}

/**
 * The quotation approval gate, stated on the screen it blocks (PS-QUOTE-RULES).
 *
 * A quotation needs approval when a line is priced below its default price (any discount) or
 * sits outside the project's series. The reasons sentence comes from the server
 * (`approval_reasons`), so the banner and the refusal on Issue say the same thing. Each request
 * goes to ONE routed approver, named here while it waits.
 *
 * Information only: every action (Send for approval, Approve, Reject) is the header's one
 * primary slot, so this banner never carries a button.
 *
 * Renders NOTHING at all for the ordinary quotation, so the common case gains no chrome.
 */
export function QuotationApprovalPanel({ document }: { document: QuotationDocument }) {
  const statusKey = document.approval_status_key ?? null;
  const withManager = isWithManager(document);
  const belowFloor = document.below_floor_line_count ?? 0;
  const discounted = document.discounted_line_count ?? 0;
  const offSeries = document.off_series_line_count ?? 0;
  // PS-PROPOSAL-QUOTATION: a quotation line below the proposal it came from (a further discount).
  const belowProposal = document.below_proposal_count ?? 0;
  const blocked = isBlockedByApproval(document);

  if (
    !document.requires_approval &&
    belowFloor === 0 &&
    discounted === 0 &&
    offSeries === 0 &&
    belowProposal === 0
  ) {
    return null;
  }

  // The server's sentence names every reason (discount, minimum price, series, proposal). The
  // fallback covers an older payload that only carries the counts.
  const priced =
    document.approval_reasons ||
    [
      belowFloor === 0
        ? null
        : belowFloor === 1
          ? 'One line is priced below minimum price'
          : `${belowFloor} lines are priced below minimum price`,
      belowProposal === 0
        ? null
        : belowProposal === 1
          ? 'one line is priced below the proposal'
          : `${belowProposal} lines are priced below the proposal`,
    ]
      .filter(Boolean)
      .join(' and ')
      .replace(/^o/, 'O');
  // Named only while it waits: whoever decides may be someone above the routed approver, so
  // the decided sentences do not credit a name.
  const who = document.approver_name || 'a manager';

  const tone = blocked
    ? 'border-amber-500/40 bg-amber-500/5'
    : 'border-emerald-500/40 bg-emerald-500/5';

  return (
    <div className={`rounded-lg border px-4 py-3 ${tone}`}>
      <div className="flex min-w-0 gap-2.5">
        {blocked ? (
          <ShieldAlert className="mt-0.5 size-4 shrink-0 text-amber-600" aria-hidden />
        ) : (
          <ShieldCheck className="mt-0.5 size-4 shrink-0 text-emerald-600" aria-hidden />
        )}
        <div className="min-w-0 space-y-1">
          {withManager && (
            <BlockLine>
              {`${priced}, so this quotation is with ${who} for approval. It cannot be sent to the customer until they decide.`}
            </BlockLine>
          )}
          {statusKey === 'rejected' && (
            <>
              <BlockLine>
                A manager sent this back. Change the lines they asked about, then ask again.
              </BlockLine>
              {document.approval_rejected_reason && (
                <p className="min-w-0 break-words text-sm text-muted-foreground">
                  {`Their reason: ${document.approval_rejected_reason}`}
                </p>
              )}
            </>
          )}
          {statusKey === 'approved' && (
            <BlockLine>
              {`${priced}, and a manager has approved it. It can be sent to the customer.`}
            </BlockLine>
          )}
          {blocked && !withManager && statusKey !== 'rejected' && (
            <BlockLine>
              {`${priced}, so this quotation needs a manager's approval before it can be sent to the customer.`}
            </BlockLine>
          )}
        </div>
      </div>
    </div>
  );
}
