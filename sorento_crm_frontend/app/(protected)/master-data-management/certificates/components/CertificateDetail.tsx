'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { AlertTriangle, CopyCheck, FileText, History, Package, Pencil, Split, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { useBackToListHref } from '@/components/common/BackToList';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import RecordEntityRegistrar from '@/components/common/RecordEntityRegistrar';
import DetailActions from '@/components/common/DetailActions';
import { certificatesPagerQuery } from '../hooks/useCertificates';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
// The backend serializes datetimes as NAIVE UTC (no trailing Z), so `new
// Date(str)` would parse them as local time and render 8 hours early. The
// Malaysia formatters parse as UTC first, then display in Asia/Kuala_Lumpur.
// valid_from / valid_until / issued_at are DATE columns, so they go through
// formatDateInMalaysia, which keeps a civil date stable on any machine.
import { formatDateInMalaysia, formatDateTimeInMalaysia } from '@/lib/helpers';
import { useCertificate, useDeleteCertificate } from '../hooks/useCertificates';
import {
  STATUS_LABELS,
  VALIDITY_STATE_LABELS,
  reviewReasonLabel,
} from '../lib/certificateDisplay';
import CertificateCoveredProducts from './CertificateCoveredProducts';
import CertificateFormDialog from './CertificateFormDialog';
import CertificateMergeDialog from './CertificateMergeDialog';
import CertificateRevisionTimeline from './CertificateRevisionTimeline';
import AttachmentDetailModal from '@/app/(protected)/resource-management/attachments/components/AttachmentDetailModal';

const LIST_PATH = '/master-data-management/certificates';


export default function CertificateDetail({ certificateId }: { certificateId: string }) {
  const router = useRouter();
  const backHref = useBackToListHref(LIST_PATH);
  const { data: certificate, isLoading } = useCertificate(certificateId);
  const deleteMutation = useDeleteCertificate();

  const [editOpen, setEditOpen] = useState(false);
  const [mergeOpen, setMergeOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  // The revision file opens in the shared resource-management modal rather
  // than routing away, so the reader keeps their place in the timeline.
  const [attachmentModalId, setAttachmentModalId] = useState<string | null>(null);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!certificate) {
    return (
      <div className="py-12 text-center">
        <p className="text-muted-foreground">Certificate not found</p>
        <Button variant="outline" className="mt-4" onClick={() => router.push(LIST_PATH)}>
          Back to Certificates
        </Button>
      </div>
    );
  }

  const revisions = certificate.revisions ?? [];
  const products = certificate.products ?? [];
  const unmatched = certificate.unmatched_products ?? [];
  const currentAccessLevels = certificate.current_revision?.access_levels ?? [];
  const title = `${certificate.scheme} ${certificate.certificate_number}`;

  return (
    <div className="space-y-6">
      <RecordEntityRegistrar entityType="certificate" id={certificateId} />

      {/* Header (FE-9) */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 space-y-1">
          <h1 className="break-words text-2xl font-bold">{title}</h1>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-muted-foreground">{certificate.certifying_body}</span>
            <span className={`${STATUS_PILL_BASE} ${statusPillClass(certificate.validity_state)}`}>
              {VALIDITY_STATE_LABELS[certificate.validity_state]}
            </span>
            <span className={`${STATUS_PILL_BASE} ${statusPillClass(certificate.status)}`}>
              {STATUS_LABELS[certificate.status]}
            </span>
            {certificate.needs_review && (
              <Badge variant="warning" appearance="light" size="sm">
                <AlertTriangle className="size-3" />
                Needs review
              </Badge>
            )}
          </div>
        </div>
        <DetailActions
          pager={{
            ...certificatesPagerQuery,
            detailPath: LIST_PATH,
            currentId: certificate.id,
            ariaLabel: 'certificate',
          }}
          actions={[
            {
              key: 'certificate.merge',
              label: 'Merge as revision of...',
              icon: Split,
              run: () => setMergeOpen(true),
            },
            {
              key: 'certificate.delete',
              label: 'Delete certificate',
              icon: Trash2,
              kind: 'destructive' as const,
              run: () => setDeleteOpen(true),
            },
          ]}
          gearLabel="Certificate options"
          primary={
            <Button onClick={() => setEditOpen(true)}>
              <Pencil className="size-4" />
              Edit
            </Button>
          }
        />
      </div>

      {/*
        Tabs, not one long scroll. Only sections with something to say are
        rendered: an unflagged certificate shows no "Review flags" card, a fully
        matched one shows no "Unmatched product codes" card, and one with no near
        match shows no duplicate card. An empty state is for a section that is
        ALWAYS relevant (coverage, revisions) - not for a warning that is not
        firing, which is just noise.
      */}
      <Tabs defaultValue="overview">
        <TabsList variant="line" className="mb-5">
          <TabsTrigger value="overview">
            <FileText />
            <span>Overview</span>
          </TabsTrigger>
          <TabsTrigger value="products">
            <Package />
            <span>Products ({certificate.covered_product_count})</span>
          </TabsTrigger>
          <TabsTrigger value="revisions">
            <History />
            <span>Revisions ({revisions.length})</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Certificate</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Field label="Scheme" value={certificate.scheme} />
              <Field label="Certificate number" value={certificate.certificate_number} />
              <Field label="Certifying body" value={certificate.certifying_body} />
              <Field label="Issuer" value={certificate.issuer} />
              <Field label="Title" value={certificate.title} />
              <Field
                label="Valid from"
                value={certificate.valid_from ? formatDateInMalaysia(certificate.valid_from) : null}
              />
              <Field
                label="Valid until"
                value={
                  certificate.valid_until ? formatDateInMalaysia(certificate.valid_until) : null
                }
              />
              <Field
                label="Days until expiry"
                value={
                  certificate.days_until_expiry == null
                    ? null
                    : certificate.days_until_expiry < 0
                      ? `Expired ${Math.abs(certificate.days_until_expiry)} days ago`
                      : `${certificate.days_until_expiry} days`
                }
              />
              <Field label="Covered products" value={String(certificate.covered_product_count)} />
              <Field label="Revisions" value={String(revisions.length)} />
              <Field label="Filed" value={formatDateTimeInMalaysia(certificate.created_at)} />
              <Field
                label="Last updated"
                value={formatDateTimeInMalaysia(certificate.updated_at)}
              />
            </CardContent>
          </Card>

          {/* Only when a rule actually fired. */}
          {certificate.review_reasons.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="min-w-0 break-words">Review flags</CardTitle>
                <Button variant="outline" size="sm" onClick={() => setEditOpen(true)}>
                  <Pencil className="size-4" />
                  Fix the details
                </Button>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2">
                  {certificate.review_reasons.map((reason, index) => (
                    <li
                      // The reason is an object, so it cannot be the key itself.
                      key={typeof reason === 'string' ? reason : (reason?.code ?? index)}
                      className="flex items-start gap-2 text-sm"
                    >
                      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600" />
                      <span>{reviewReasonLabel(reason)}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}

          {/* Only when the reader produced a code that matched nothing. */}
          {unmatched.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="min-w-0 break-words">Unmatched product codes</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex flex-wrap gap-2">
                  {unmatched.map((value) => (
                    <span
                      key={value}
                      className="inline-flex max-w-full items-center rounded-md border border-dashed border-amber-400 bg-amber-50 px-2 py-1 text-sm text-amber-900"
                      title={value}
                    >
                      <span className="truncate">{value}</span>
                    </span>
                  ))}
                </div>
                <p className="text-sm text-muted-foreground">
                  Add the matching product under Products.
                </p>
              </CardContent>
            </Card>
          )}

          {/* Only when a near match was actually found. */}
          {certificate.possible_duplicate_of && (
            <Card>
              <CardHeader>
                <CardTitle className="min-w-0 break-words">Suspected duplicate</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <p className="text-sm">
                    May be a renewal of{' '}
                    <Link
                      href={`${LIST_PATH}/${certificate.possible_duplicate_of.id}`}
                      className="font-medium underline"
                    >
                      {certificate.possible_duplicate_of.scheme}{' '}
                      {certificate.possible_duplicate_of.certificate_number}
                    </Link>
                    .
                  </p>
                  <Button variant="outline" size="sm" onClick={() => setMergeOpen(true)}>
                    <CopyCheck className="size-4" />
                    Merge as revision of...
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="products">
          <CertificateCoveredProducts certificateId={certificate.id} products={products} />
        </TabsContent>

        <TabsContent value="revisions">
          <Card>
            <CardContent className="pt-6">
              <CertificateRevisionTimeline
                revisions={revisions}
                currentAccessLevels={currentAccessLevels}
                onOpenAttachment={setAttachmentModalId}
              />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Prev/next walks the revision files of THIS certificate - a renewal and
          the issue it replaced sit side by side, which is the comparison the
          reader is usually making. */}
      <AttachmentDetailModal
        open={attachmentModalId != null}
        onOpenChange={(open) => !open && setAttachmentModalId(null)}
        attachmentId={attachmentModalId}
        neighbourItems={revisions
          .filter((r) => r.attachment_id && !r.attachment_is_deleted)
          .map((r) => ({ id: r.attachment_id as string }))}
        onAttachmentChange={setAttachmentModalId}
      />

      {editOpen && (
        <CertificateFormDialog
          open={editOpen}
          onOpenChange={setEditOpen}
          certificateId={certificate.id}
        />
      )}

      <CertificateMergeDialog
        open={mergeOpen}
        onOpenChange={setMergeOpen}
        certificate={certificate}
        onMerged={(targetId) => router.push(`${LIST_PATH}/${targetId}`)}
      />

      <ConfirmDeleteDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Confirm delete"
        description={
          <>
            Delete {title}, its {revisions.length} revision
            {revisions.length === 1 ? '' : 's'} and its {certificate.covered_product_count} covered
            product link{certificate.covered_product_count === 1 ? '' : 's'}. The uploaded files are
            kept. This action cannot be undone.
          </>
        }
        successMessage="Certificate deleted"
        onDelete={async () => {
          await deleteMutation.mutateAsync(certificate.id);
        }}
        onSuccess={() => router.push(backHref)}
        queryKeysToInvalidate={[['certificates']]}
      />
    </div>
  );
}

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="min-w-0">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="break-words font-medium">{value || 'Not recorded'}</p>
    </div>
  );
}
