'use client';

import Link from 'next/link';
import { Download, Eye, FileText, FileWarning } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
// Backend datetimes are NAIVE UTC, so they must be parsed as UTC before being
// displayed (or handed to timeAgo, which subtracts from now) or every stamp
// reads 8 hours early. Validity dates are DATE columns: civil, never converted.
import {
  formatDateInMalaysia,
  formatDateTimeInMalaysia,
  parseDateTimeAsUTC,
  timeAgo,
} from '@/lib/helpers';
import { accessLevelLabel } from '../lib/certificateDisplay';
import type { CertificateRevision } from '../types/certificate.types';

/**
 * FE-6: revision history reads like delivery tracking - newest first, one node
 * per event, on the shared rail-and-dot pattern from ActivityTimeline. FE-6a:
 * every node carries what happened, when (relative + absolute), the revision
 * number, the validity window, the file, and that revision's access levels.
 */
export default function CertificateRevisionTimeline({
  revisions,
  currentAccessLevels,
  onOpenAttachment,
}: {
  revisions: CertificateRevision[];
  currentAccessLevels: string[];
  /** Opens the file in the shared resource-management attachment modal - the
   *  same affordance a product / promotion / packing-list detail page gives.
   *  Omitted, or a revision with no `attachment_id`, renders plain text. */
  onOpenAttachment?: (attachmentId: string) => void;
}) {
  if (revisions.length === 0) {
    return (
      <Card className="shadow-none">
        <CardContent className="flex flex-col items-center justify-center gap-3 p-10 text-center">
          <div className="flex size-12 items-center justify-center rounded-full bg-muted">
            <FileWarning className="size-6 text-muted-foreground" />
          </div>
          <div>
            <p className="font-medium">No revision on file</p>
            <p className="text-sm text-muted-foreground">
              This certificate has no document behind it yet.
            </p>
          </div>
          <Button asChild variant="outline" size="sm">
            <Link href="/resource-management/attachment-directories">Upload the document</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  const ordered = [...revisions].sort((a, b) => b.revision_no - a.revision_no);

  return (
    <ol className="relative space-y-4 ps-4 before:absolute before:inset-y-1 before:start-[5px] before:w-px before:bg-border">
      {ordered.map((revision) => (
        <RevisionNode
          key={revision.id}
          revision={revision}
          currentAccessLevels={currentAccessLevels}
          onOpenAttachment={onOpenAttachment}
        />
      ))}
    </ol>
  );
}

function RevisionNode({
  revision,
  currentAccessLevels,
  onOpenAttachment,
}: {
  revision: CertificateRevision;
  currentAccessLevels: string[];
  onOpenAttachment?: (attachmentId: string) => void;
}) {
  const eventLabel = revision.revision_no === 1 ? 'Issued' : 'Renewed';
  const dotClass = revision.is_current ? 'bg-primary' : 'bg-muted-foreground/40';
  // The backend sends `access_levels: null` for a revision with no attachment, and
  // the create form files exactly that. Treating null as [] keeps the golden path
  // from white-screening on a `.length` read.
  const accessLevels = revision.access_levels ?? [];
  const accessDiffers =
    !revision.is_current &&
    (accessLevels.length !== currentAccessLevels.length ||
      accessLevels.some((level) => !currentAccessLevels.includes(level)));

  return (
    <li className="relative ps-6">
      <span
        className={`absolute start-0 top-1.5 size-2.5 rounded-full ring-4 ring-background ${dotClass}`}
        aria-hidden
      />
      <Card className="shadow-none">
        <CardContent className="flex flex-col gap-3 p-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{eventLabel}</span>
              <Badge variant="secondary" appearance="light" size="sm">
                Revision {revision.revision_no}
              </Badge>
              {revision.is_current ? (
                <Badge variant="primary" appearance="light" size="sm">
                  Current
                </Badge>
              ) : (
                <Badge variant="secondary" appearance="light" size="sm">
                  Superseded
                </Badge>
              )}
              {revision.needs_review && (
                <Badge variant="warning" appearance="light" size="sm">
                  Needs review
                </Badge>
              )}
            </div>

            <p className="text-sm text-muted-foreground">
              {revision.valid_from
                ? formatDateInMalaysia(revision.valid_from)
                : 'Start not recorded'}
              {' to '}
              {revision.valid_until
                ? formatDateInMalaysia(revision.valid_until)
                : 'no expiry recorded'}

            </p>

            {revision.attachment_filename ? (
              revision.attachment_is_deleted ? (
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="destructive" appearance="light" size="sm">
                    <FileWarning className="size-3" />
                    File removed
                  </Badge>
                  <span
                    className="truncate text-sm text-muted-foreground"
                    title={revision.attachment_filename}
                  >
                    {revision.attachment_filename}
                  </span>
                </div>
              ) : (
                <div className="flex flex-wrap items-center gap-2">
                  {/* The filename is the way into resource management, matching
                      how a product / promotion / packing-list detail page opens
                      its files. A revision with no attachment_id (filed before
                      its document, or the file hard-deleted) stays plain text
                      rather than becoming a button that goes nowhere. */}
                  {onOpenAttachment && revision.attachment_id ? (
                    <button
                      type="button"
                      onClick={() => onOpenAttachment(revision.attachment_id as string)}
                      className="inline-flex max-w-full items-center gap-1 truncate text-sm text-primary hover:underline"
                      title={`Open ${revision.attachment_filename} in Resource Management`}
                    >
                      <span className="truncate">{revision.attachment_filename}</span>
                      <FileText className="size-3.5 shrink-0" />
                    </button>
                  ) : (
                    <span className="truncate text-sm" title={revision.attachment_filename}>
                      {revision.attachment_filename}
                    </span>
                  )}
                  {/* Only the CURRENT revision is url-resolved, so superseded rows
                      show the filename without controls rather than a dead link. */}
                  {revision.preview_url ? (
                    <Button asChild variant="outline" size="sm">
                      <a href={revision.preview_url} target="_blank" rel="noreferrer">
                        <Eye className="size-3.5" />
                        Preview
                      </a>
                    </Button>
                  ) : null}
                  {revision.download_url ? (
                    <Button asChild variant="outline" size="sm">
                      <a href={revision.download_url} download>
                        <Download className="size-3.5" />
                        Download
                      </a>
                    </Button>
                  ) : null}
                </div>
              )
            ) : (
              <p className="text-sm text-muted-foreground">No file attached to this revision.</p>
            )}

            <div className="flex flex-wrap items-center gap-1.5">
              {accessLevels.length === 0 ? (
                <span className="text-sm text-muted-foreground">No access level recorded</span>
              ) : (
                accessLevels.map((level) => (
                  <Badge key={level} variant="secondary" appearance="light" size="sm">
                    {accessLevelLabel(level)}
                  </Badge>
                ))
              )}
            </div>

            {accessDiffers && (
              <p className="text-sm text-amber-700">
                Visibility changed at the current revision.
              </p>
            )}
          </div>

          <div className="shrink-0 text-start sm:text-end">
            {/* timeAgo subtracts from `now`, so it must be handed a UTC-parsed
                Date - the raw naive string would read 8 hours stale. */}
            <div className="text-xs font-medium">
              {timeAgo(parseDateTimeAsUTC(revision.created_at))}
            </div>
            <div
              className="text-xs text-muted-foreground"
              title={formatDateTimeInMalaysia(revision.created_at)}
            >
              {formatDateTimeInMalaysia(revision.created_at)}
            </div>
          </div>
        </CardContent>
      </Card>
    </li>
  );
}
