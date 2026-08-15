'use client';

/**
 * One warranty policy, on its own page (CRUD standard: view = dedicated page).
 *
 * Every section renders unconditionally with its own empty state and next step -
 * a policy with no source document and no text is exactly the policy somebody
 * needs to be told about, and hiding those cards is how it reads as complete.
 */
import { use, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowLeft, Layers, Pencil, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { useCompany } from '@/app/providers/CompanyProvider';
import { PolicyFormDialog, type PolicyDialogMode } from '../../components/PolicyFormDialog';
import { TermsByKindSection } from '../../components/TermsByKindSection';
import {
  useDeletePolicy,
  usePolicy,
  useSupersedePolicy,
  useUpdatePolicy,
} from '../../hooks/useWarrantyConfig';
import {
  POLICY_LIFECYCLE_BADGE,
  POLICY_LIFECYCLE_LABEL,
  formatCivilDate,
  policyLifecycle,
} from '../../lib/warrantyLabels';
import type { WarrantyPolicyWrite } from '../../types/warranty-config.types';

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <p className="text-sm text-muted-foreground">{label}</p>
      <div className="font-medium break-words">{value}</div>
    </div>
  );
}

export default function WarrantyPolicyDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const { activeCompany } = useCompany();

  const [dialogMode, setDialogMode] = useState<PolicyDialogMode | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const policy = usePolicy(id);
  const updatePolicy = useUpdatePolicy();
  const supersede = useSupersedePolicy();
  const deletePolicy = useDeletePolicy();

  if (policy.isLoading) {
    return (
      <div className="flex flex-col gap-4 p-4 sm:p-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (policy.isError || !policy.data) {
    return (
      <div className="flex flex-col gap-4 p-4 sm:p-6">
        <Button variant="outline" size="sm" asChild className="w-fit">
          <Link href="/warranty-management">
            <ArrowLeft className="size-4" /> Back to warranty configuration
          </Link>
        </Button>
        <p className="text-sm text-muted-foreground">
          {(policy.error as Error)?.message ?? 'Warranty policy not found.'}
        </p>
      </div>
    );
  }

  const data = policy.data;

  const submit = async (body: WarrantyPolicyWrite) => {
    setFormError(null);
    try {
      if (dialogMode === 'supersede') {
        const result = await supersede.mutateAsync({ id, body });
        setDialogMode(null);
        router.push(`/warranty-management/policies/${result.created.id}`);
        return;
      }
      await updatePolicy.mutateAsync({ id, body });
      setDialogMode(null);
    } catch (e) {
      setFormError(e instanceof Error ? e.message : 'Save failed');
    }
  };

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-2">
          <Button variant="ghost" size="icon" asChild>
            <Link href="/warranty-management" aria-label="Back to warranty configuration">
              <ArrowLeft className="size-4" />
            </Link>
          </Button>
          <h1 className="min-w-0 text-xl font-semibold break-words">{data.version}</h1>
          <Badge
            variant={POLICY_LIFECYCLE_BADGE[policyLifecycle(data)]}
            appearance="light"
            size="md"
          >
            {POLICY_LIFECYCLE_LABEL[policyLifecycle(data)]}
          </Badge>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            onClick={() => {
              setFormError(null);
              setDialogMode('supersede');
            }}
          >
            <Layers className="size-4" /> Supersede
          </Button>
          <Button
            variant="outline"
            onClick={() => {
              setFormError(null);
              setDialogMode('edit');
            }}
          >
            <Pencil className="size-4" /> Edit
          </Button>
          <Button variant="outline" onClick={() => setDeleteOpen(true)}>
            <Trash2 className="size-4 text-destructive" /> Delete
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Effective period</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <Field label="Company" value={activeCompany?.name ?? 'No company selected'} />
          <Field label="Effective from" value={formatCivilDate(data.effective_from)} />
          <Field
            label="Effective to"
            value={
              data.effective_to ? (
                formatCivilDate(data.effective_to)
              ) : (
                <span className="text-muted-foreground">Open ended</span>
              )
            }
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Source document</CardTitle>
        </CardHeader>
        <CardContent>
          {/* No CTA on the empty state: nothing in this slice can attach a
              document (the write payload carries no attachment, and the terms
              themselves live in Policy text), so an "Edit policy" button here
              would be a promise the app cannot keep. */}
          {data.source_attachment_name ? (
            <p className="font-medium break-words">{data.source_attachment_name}</p>
          ) : (
            <p className="text-sm text-muted-foreground">
              No source document attached to this policy.
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Policy text</CardTitle>
        </CardHeader>
        <CardContent>
          {data.policy_text ? (
            <pre className="max-h-96 overflow-auto rounded-md bg-muted/40 p-3 text-sm whitespace-pre-wrap break-words">
              {data.policy_text}
            </pre>
          ) : (
            <div className="flex flex-col items-start gap-2">
              <p className="text-sm text-muted-foreground">No policy text recorded.</p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setFormError(null);
                  setDialogMode('edit');
                }}
              >
                Add policy text
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      <TermsByKindSection policyId={id} />

      <PolicyFormDialog
        open={dialogMode !== null}
        onOpenChange={(o) => {
          if (!o) {
            setDialogMode(null);
            setFormError(null);
          }
        }}
        mode={dialogMode ?? 'edit'}
        initial={dialogMode === 'edit' ? data : null}
        incumbent={dialogMode === 'supersede' ? data : null}
        onSubmit={submit}
        isSubmitting={updatePolicy.isPending || supersede.isPending}
        error={formError}
      />

      <ConfirmDeleteDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Confirm delete"
        description={
          <>
            This action cannot be undone. Policy <strong>{data.version}</strong> will be permanently
            removed
            {data.term_count > 0 ? (
              <>
                {' '}
                along with the <strong>{data.term_count}</strong> term
                {data.term_count === 1 ? '' : 's'} published under it
              </>
            ) : (
              <>. It has no terms under it</>
            )}
            .
          </>
        }
        successMessage="Policy deleted"
        onDelete={async () => {
          await deletePolicy.mutateAsync(id);
        }}
        onSuccess={() => router.push('/warranty-management')}
      />
    </div>
  );
}
