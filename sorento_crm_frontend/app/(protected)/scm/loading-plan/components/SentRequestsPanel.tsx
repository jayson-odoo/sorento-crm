'use client';

import { useState } from 'react';
import { Check, Download, LoaderCircle, Link2, Mail, MessageCircle, Send } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { formatDateInMalaysia } from '@/lib/helpers';
import { cn } from '@/lib/utils';
import { EM_DASH, fmtOpens } from '../../lib/format';
import {
  getNoticeDocumentUrl,
  type NoticeChatRecipient,
  type SupplierNotice,
} from '../../services/fulfilmentService';
import { copyPublicLink } from './copyPublicLink';

/**
 * The Sent tab (S2): what has already gone out for this plan, promoted out of
 * `ContainerRequestSection`'s inline `noticesCard` so it can be its own tab body rather than a
 * card at the foot of the Lines table.
 *
 * `notices` is handed down already built and filtered to `notice_type: 'container_request'` -
 * `LoadingPlanView` runs `useSupplierNotices` once for the tab's own badge count and for
 * `Copy link`'s "the last live one" search, so this panel reads that same list rather than
 * asking the query a second time.
 */

const NOTICE_STATUS_LABEL: Record<SupplierNotice['status'], string> = {
  pending: 'Queued',
  sent: 'Sent',
  failed: 'Failed',
  skipped: 'Not sent',
};

const NOTICE_CHANNEL_LABEL: Record<SupplierNotice['channel'], string> = {
  email: 'Email',
  // A chat send is a WeChat send (R10) - the factories are in China. The column says the
  // channel it actually went out on, not the internal name of the column it is stored in.
  chat: 'WeChat',
};

const NOTICE_CHANNEL_ICON: Record<SupplierNotice['channel'], typeof Mail> = {
  email: Mail,
  chat: MessageCircle,
};

/**
 * Everybody this send named, in one line (AC-C2).
 *
 * An email notice holds addresses; a chat notice holds the one WeChat contact, by name -
 * "who read it" is a person on a phone, not a `respond_contacts` id (no UUIDs in the UI).
 * `recipient` is the pre-442 single-address column, kept as the fallback so a notice sent
 * before the send dialog existed still says where it went.
 */
function noticeRecipients(notice: SupplierNotice): string {
  const named = notice.recipients;
  if (Array.isArray(named) && named.length > 0) {
    return named
      .map((r) =>
        typeof r === 'string' ? r : (r as NoticeChatRecipient).name || 'Unnamed contact',
      )
      .join(', ');
  }
  return notice.recipient ?? '';
}

export function SentRequestsPanel({
  supplierName,
  notices,
  onSend,
  sendDisabled,
  sendDisabledReason,
}: {
  supplierName: string;
  /** Already filtered to this plan's `container_request` notices, `created_at` newest first. */
  notices: SupplierNotice[];
  /** Opens the same Send dialog the toolbar's gear does (AC-B4's empty-state Send button). */
  onSend: () => void;
  sendDisabled?: boolean;
  sendDisabledReason?: string;
}) {
  const [openingDocId, setOpeningDocId] = useState<string | null>(null);
  const [copiedNoticeId, setCopiedNoticeId] = useState<string | null>(null);

  async function openDocument(notice: SupplierNotice, kind: 'pdf' | 'xlsx') {
    setOpeningDocId(`${notice.id}:${kind}`);
    try {
      const { url } = await getNoticeDocumentUrl(notice.id, kind);
      window.open(url, '_blank', 'noopener');
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setOpeningDocId(null);
    }
  }

  // The link the supplier already has in their inbox, copied so Ms Tee can paste it into
  // WeChat herself - which is how she reaches the factories that never open email.
  async function copyLink(notice: SupplierNotice) {
    if (!(await copyPublicLink(notice.public_url))) return;
    setCopiedNoticeId(notice.id);
    window.setTimeout(() => setCopiedNoticeId(null), 2000);
  }

  return (
    <Card className="p-4" data-testid="requests-sent">
      <h3 className="text-sm font-semibold">Requests sent to {supplierName}</h3>
      {notices.length === 0 ? (
        <div className="mt-2 flex flex-col items-center gap-3 rounded-lg border border-dashed border-border p-6 text-center">
          <p className="text-xs text-muted-foreground">Nothing sent yet.</p>
          <Button size="sm" onClick={onSend} disabled={sendDisabled} title={sendDisabledReason}>
            <Send className="size-4" />
            Send to supplier
          </Button>
        </div>
      ) : (
        <div className="mt-2 divide-y divide-border rounded-lg border">
          {notices.map((n) => (
            <div
              key={n.id}
              className="flex flex-col gap-2 p-3 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  {(() => {
                    const ChannelIcon = NOTICE_CHANNEL_ICON[n.channel];
                    return <ChannelIcon className="size-3.5 text-muted-foreground" />;
                  })()}
                  <span className="text-xs font-medium">{NOTICE_CHANNEL_LABEL[n.channel]}</span>
                  <span className={cn(STATUS_PILL_BASE, statusPillClass(n.status))}>
                    {NOTICE_STATUS_LABEL[n.status]}
                  </span>
                  {noticeRecipients(n) ? (
                    <span
                      className="truncate text-2xs text-muted-foreground"
                      title={noticeRecipients(n)}
                    >
                      {noticeRecipients(n)}
                    </span>
                  ) : null}
                </div>
                <p className="mt-0.5 text-2xs text-muted-foreground">
                  {n.last_error ||
                    n.status_reason ||
                    (n.sent_at ? `Sent ${formatDateInMalaysia(n.sent_at)}` : EM_DASH)}
                </p>
                {/* Whether the supplier has actually looked at it (AC-C8). Its own line,
                    beside the send, because "sent" and "read" are two different facts and
                    the second one is the one that decides whether to chase. */}
                <p className="mt-0.5 text-2xs text-muted-foreground" data-testid="notice-opens">
                  {fmtOpens(n.open_count, n.last_opened_at)}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <span className="text-2xs text-muted-foreground">{n.line_count} products</span>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={!n.has_document || openingDocId === `${n.id}:pdf`}
                  onClick={() => openDocument(n, 'pdf')}
                >
                  {openingDocId === `${n.id}:pdf` ? (
                    <LoaderCircle className="size-4 animate-spin" />
                  ) : (
                    <Download className="size-4" />
                  )}
                  PDF
                </Button>
                {/* Their own stock list with the quantity to load filled in (AC-C4). Absent
                    on notices sent before F4, which is why the button is conditional rather
                    than merely disabled. */}
                {n.has_xlsx ? (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={openingDocId === `${n.id}:xlsx`}
                    onClick={() => openDocument(n, 'xlsx')}
                  >
                    {openingDocId === `${n.id}:xlsx` ? (
                      <LoaderCircle className="size-4 animate-spin" />
                    ) : (
                      <Download className="size-4" />
                    )}
                    XLSX
                  </Button>
                ) : null}
                {/* On EVERY row of the current send (R23), because the link is one credential
                    delivered two ways and the chat row is the one she copies from for WeChat.
                    A row whose token has run out says so instead of falling silent: no button
                    (a copied dead link is worse than none) but not the same blank as a row
                    that never carried a link at all. */}
                {n.public_url ? (
                  <Button size="sm" variant="outline" onClick={() => copyLink(n)}>
                    {copiedNoticeId === n.id ? (
                      <Check className="size-4" />
                    ) : (
                      <Link2 className="size-4" />
                    )}
                    Copy link
                  </Button>
                ) : n.link_retired ? (
                  <span
                    className="text-2xs text-muted-foreground"
                    title="A later request replaced this link, or it passed its 30 days."
                  >
                    Link retired
                  </span>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

export default SentRequestsPanel;
