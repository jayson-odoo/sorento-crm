'use client';

import { SoCustomerProject, soCustomerProjectLabel } from '@/components/common/SoCustomerProject';
import { RecordCardSlot } from '@/app/(protected)/sla-management/_shared/RecordCardSlot';
import { useMemo, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { type ColumnDef, type ExpandedState } from '@tanstack/react-table';
import {
  CalendarClock,
  ChevronDown,
  ChevronRight,
  Link2,
  PackageCheck,
  Printer,
  Settings2,
  Trash2,
} from 'lucide-react';
import { toast } from '@/lib/toast';
import { DatePicker } from '@/components/ui/date-picker';
import { toIsoDate } from '@/components/ui/date-range-picker';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { DropdownMenuItem } from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import AuditTrail from '@/components/audit/AuditTrail';
import DetailActions from '@/components/common/DetailActions';
import { DetailActionsMenu } from '@/components/common/DetailActionsMenu';
import { PanelDataGrid } from '@/components/common/PanelDataGrid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import { useEffectiveUserId } from '@/hooks/useEffectiveUserId';
import { useHasPermission } from '@/hooks/usePermissions';
import { useRequestScope } from '@/hooks/useRequestScope';
import { MyRequestClientProvider } from '@/components/common/MyRequestPortalForm';
import PortalSampleRequestForm from '@/app/(auth)/portal/components/SampleRequestForm';
import { formatDateInMalaysia, todayMalaysiaYyyyMmDd } from '@/lib/helpers';
import { dateAnswerProblem, dateAnswerText } from '@/lib/sample-request-tracking';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import {
  DELIVERY_MODE_LABELS,
  GOODS_FROM_LABELS,
  type SampleRequestDetail as Detail,
  type SampleRequestLine,
  type SampleRequestStatus,
} from '@/types/sampleRequest';
import { OrderInquiryStockGrid } from '../../_shared/components/OrderInquiryStockGrid';
import { useReviewOriginHref } from '../../_shared/hooks/useReviewOrigin';
import { withReviewOrigin } from '../../_shared/lib/reviewOrigin';
import { projectFromOrigin, projectPagerQuery } from './SampleRequestPageHeader';
import {
  sampleRequestsPagerQuery,
  useSampleRequestMutations,
  useSampleRequestQuery,
} from '../hooks/useSampleRequests';
import {
  downloadSampleRequestPdf,
  searchSampleRequestConsignments,
} from '../services/sampleRequestService';

const BASE_PATH = '/project-sales/sample-requests';

interface Move {
  to: SampleRequestStatus;
  label: string;
  /** Who may make it: `process` holders, or the request's owner too (`either`). */
  needs: 'process' | 'either';
  /** `answer`: Start processing carries the date answer (PS-SAMPLE-TRACKING rule 2). */
  ask?: 'date' | 'reason' | 'answer';
  tone: 'emerald' | 'primary' | 'destructive';
}

/**
 * The moves the card allows from each status (rule 10); the server is the authority. Owner ruling
 * 11 Nov ~19:55: Submitted -> Processing -> Delivered, and Delivered comes ONLY from linking the
 * AutoCount consignment (the Consignment card below), so there is no Customer confirmed and no
 * "Mark delivered" button.
 */
const MOVES: Record<SampleRequestStatus, Move[]> = {
  draft: [{ to: 'cancelled', label: 'Cancel request', needs: 'either', tone: 'destructive' }],
  submitted: [
    {
      to: 'processing',
      label: 'Change to processing',
      needs: 'process',
      ask: 'answer',
      tone: 'emerald',
    },
    { to: 'cancelled', label: 'Cancel request', needs: 'either', tone: 'destructive' },
  ],
  processing: [
    {
      to: 'cancelled',
      label: 'Cancel request',
      needs: 'process',
      ask: 'reason',
      tone: 'destructive',
    },
  ],
  // Retired (migration srv2_0002 moved every such row to Processing); kept for the type only.
  customer_confirmed: [],
  delivered: [],
  cancelled: [],
};

const MOVE_CLASS: Record<Move['tone'], string> = {
  emerald: 'bg-emerald-600 text-white hover:bg-emerald-700',
  primary: '',
  destructive: 'border-destructive text-destructive hover:bg-destructive/10',
};

/** Where a consignment's delivered date came from (PS-SAMPLE-TRACKING, crew b). */
const DELIVERED_SOURCE_LABELS = {
  tracking: 'Order Tracking',
  consignment: 'consignment date',
} as const;

const day = (value: string | null | undefined) => (value ? formatDateInMalaysia(value) : '');

/** One label / value cell of the document card; an empty value reads as `empty`. */
function Field({
  label,
  children,
  empty = 'None',
  wide = false,
}: {
  label: string;
  children?: ReactNode;
  empty?: string;
  wide?: boolean;
}) {
  return (
    <div className={wide ? 'sm:col-span-2' : undefined}>
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="font-medium whitespace-pre-wrap">{children || empty}</p>
    </div>
  );
}

function AskDialog({
  move,
  busy,
  onCancel,
  onConfirm,
}: {
  move: Move;
  busy: boolean;
  onCancel: () => void;
  onConfirm: (value: string) => void;
}) {
  const [value, setValue] = useState('');
  const ready = value.trim().length > 0;
  return (
    <Dialog open onOpenChange={(next) => !next && onCancel()}>
      <DialogContent className="w-full max-w-md">
        <DialogHeader>
          <DialogTitle>{move.label}</DialogTitle>
          <DialogDescription className="sr-only">
            {move.ask === 'date' ? 'Enter the date.' : 'Enter the reason.'}
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-1.5">
          {move.ask === 'date' ? (
            <>
              <Label htmlFor="sr-move-date">Date *</Label>
              <Input
                id="sr-move-date"
                type="date"
                value={value}
                onChange={(e) => setValue(e.target.value)}
              />
            </>
          ) : (
            <>
              <Label htmlFor="sr-move-reason">Reason *</Label>
              <Textarea
                id="sr-move-reason"
                rows={3}
                value={value}
                onChange={(e) => setValue(e.target.value)}
              />
            </>
          )}
        </DialogBody>
        <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
          <Button variant="outline" onClick={onCancel}>
            Back
          </Button>
          <Button disabled={!ready || busy} onClick={() => onConfirm(value.trim())}>
            {move.label}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export interface DateAnswerValue {
  date_feasible: boolean;
  proposed_delivery_date?: string;
  date_note?: string;
}

/**
 * Can the sample team meet the requested date? Yes, or No with the date it can (rule 2). Used
 * by Start processing and by "Change date answer".
 */
export function DateAnswerDialog({
  title,
  confirmLabel,
  requested,
  initial,
  busy,
  onCancel,
  onConfirm,
}: {
  title: string;
  confirmLabel: string;
  requested: string | null;
  initial?: Pick<Detail, 'date_feasible' | 'proposed_delivery_date' | 'date_note'>;
  busy: boolean;
  onCancel: () => void;
  onConfirm: (value: DateAnswerValue) => void;
}) {
  const [feasible, setFeasible] = useState<boolean | null>(initial?.date_feasible ?? null);
  const [proposed, setProposed] = useState(initial?.proposed_delivery_date ?? '');
  const [note, setNote] = useState(initial?.date_note ?? '');
  const today = todayMalaysiaYyyyMmDd();
  const problem = dateAnswerProblem(feasible, proposed, today);
  const send = () => {
    if (problem || feasible === null) return;
    onConfirm({
      date_feasible: feasible,
      ...(feasible ? {} : { proposed_delivery_date: proposed }),
      ...(note.trim() ? { date_note: note.trim() } : {}),
    });
  };
  return (
    <Dialog open onOpenChange={(next) => !next && onCancel()}>
      <DialogContent className="w-full max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription className="sr-only">Answer the requested delivery date.</DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4">
          <div className="space-y-2">
            <p className="text-sm font-medium">
              Can we deliver by {requested ? formatDateInMalaysia(requested) : 'the requested date'}? *
            </p>
            <RadioGroup
              value={feasible === null ? '' : feasible ? 'yes' : 'no'}
              onValueChange={(v) => setFeasible(v === 'yes')}
              className="flex flex-col gap-3"
            >
              <div className="flex items-center gap-2">
                <RadioGroupItem value="yes" id="sr-answer-yes" />
                <Label htmlFor="sr-answer-yes" className="font-normal">
                  Yes, we can meet it
                </Label>
              </div>
              <div className="flex items-center gap-2">
                <RadioGroupItem value="no" id="sr-answer-no" />
                <Label htmlFor="sr-answer-no" className="font-normal">
                  No, propose a new date
                </Label>
              </div>
            </RadioGroup>
          </div>
          {feasible === false && (
            <div className="space-y-1.5">
              <Label htmlFor="sr-answer-date">Proposed date *</Label>
              {/* The shared DD/MM/YYYY picker (standing rule); a date before today is refused below. */}
              <DatePicker
                id="sr-answer-date"
                ariaLabel="Proposed date"
                portal
                value={proposed ? new Date(`${proposed}T00:00:00`) : undefined}
                onChange={(d) => setProposed(toIsoDate(d) ?? '')}
              />
            </div>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="sr-answer-note">Note</Label>
            <Textarea
              id="sr-answer-note"
              rows={2}
              maxLength={255}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>
          {feasible === false && proposed && problem && (
            <p className="text-sm text-destructive">{problem}</p>
          )}
        </DialogBody>
        <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
          <Button variant="outline" onClick={onCancel}>
            Back
          </Button>
          <Button disabled={Boolean(problem) || busy} onClick={send}>
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Stage 2: the sample team picks the AutoCount consignment that delivered the request. */
export function ConsignmentDialog({
  request,
  busy,
  onCancel,
  onLink,
}: {
  request: Detail;
  busy: boolean;
  onCancel: () => void;
  onLink: (consignmentOrderId: string) => void;
}) {
  const current = request.consignment;
  const [picked, setPicked] = useState<SearchableSelectOption | null>(
    current ? { value: current.id, label: current.so_number } : null,
  );
  const fetchOptions = async (q: string) =>
    (await searchSampleRequestConsignments(request.id, q)).map((c) => ({
      value: c.id,
      label: c.so_number,
      description: [
        c.debtor_code,
        soCustomerProjectLabel(c.customer_name ?? c.debtor_name, c.project_label),
        c.order_date ? day(c.order_date) : null,
      ]
        .filter(Boolean)
        .join(' - '),
    }));
  return (
    <Dialog open onOpenChange={(next) => !next && onCancel()}>
      <DialogContent className="w-full max-w-md">
        <DialogHeader>
          <DialogTitle>Link consignment</DialogTitle>
          <DialogDescription className="sr-only">
            Choose the AutoCount consignment that delivered this request.
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-1.5">
          <Label htmlFor="sr-consignment-pick">Consignment *</Label>
          <SearchableSelect
            id="sr-consignment-pick"
            value={picked?.value ?? ''}
            selectedOption={picked ?? undefined}
            onChange={() => undefined}
            onOptionChange={setPicked}
            fetchOptions={fetchOptions}
            placeholder="Search CG number or debtor"
            triggerClassName="w-full"
          />
        </DialogBody>
        <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
          <Button variant="outline" onClick={onCancel}>
            Back
          </Button>
          <Button
            disabled={!picked || picked.value === current?.id || busy}
            onClick={() => picked && onLink(picked.value)}
          >
            Link
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function InternalDialog({
  request,
  busy,
  onCancel,
  onSave,
}: {
  request: Detail;
  busy: boolean;
  onCancel: () => void;
  onSave: (value: { consignment_no: string | null; po_no: string | null }) => void;
}) {
  const [consignment, setConsignment] = useState(request.consignment_no ?? '');
  const [poNo, setPoNo] = useState(request.po_no ?? '');
  return (
    <Dialog open onOpenChange={(next) => !next && onCancel()}>
      <DialogContent className="w-full max-w-md">
        <DialogHeader>
          <DialogTitle>Set consignment / PO no</DialogTitle>
          <DialogDescription className="sr-only">
            Enter the consignment and PO numbers.
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="sr-consignment">Consignment no</Label>
            <Input
              id="sr-consignment"
              // A linked consignment owns the number (Link consignment changes it).
              disabled={Boolean(request.consignment)}
              value={consignment}
              onChange={(e) => setConsignment(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="sr-po">PO no</Label>
            <Input id="sr-po" value={poNo} onChange={(e) => setPoNo(e.target.value)} />
          </div>
        </DialogBody>
        <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
          <Button variant="outline" onClick={onCancel}>
            Back
          </Button>
          <Button
            disabled={busy}
            onClick={() =>
              onSave({ consignment_no: consignment.trim() || null, po_no: poNo.trim() || null })
            }
          >
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * A salesperson limited to their own sample requests (PORTAL-P4-REQUESTS R3, form parity) views
 * theirs in the portal's own form, read-only exactly as the portal shows it; everyone else the
 * staff detail, unchanged.
 */
export default function SampleRequestDetail({ requestId }: { requestId: string }) {
  const { limited } = useRequestScope('sample_request');
  if (limited) {
    return (
      <MyRequestClientProvider>
        <PortalSampleRequestForm requestId={requestId} />
      </MyRequestClientProvider>
    );
  }
  return <StaffSampleRequestDetail requestId={requestId} />;
}

function StaffSampleRequestDetail({ requestId }: { requestId: string }) {
  const router = useRouter();
  const origin = useReviewOriginHref();
  const originProject = projectFromOrigin(origin);
  const { data: request, isLoading, isError, error } = useSampleRequestQuery(requestId);
  const { submit, move, saveInternal, answerDate, linkConsignment } =
    useSampleRequestMutations();
  const canProcess = useHasPermission('projects.sample_requests.process');
  const canCreate = useHasPermission('projects.sample_requests.create');
  // The history endpoint answers only admins and `view` holders; a salesperson who holds
  // just `create` would get a 403 toast on every page.
  const canViewRecord = useHasPermission('projects.sample_requests.view');
  const userId = useEffectiveUserId();
  const [asking, setAsking] = useState<Move | null>(null);
  const [internalOpen, setInternalOpen] = useState(false);
  const [answerOpen, setAnswerOpen] = useState(false);
  const [consignmentOpen, setConsignmentOpen] = useState(false);
  const [expanded, setExpanded] = useState<ExpandedState>({});

  // Delete draft asks nothing (D7): a countdown takes the primary area, Cancel is the way back.
  const deletion = useDeferredAction({
    actionKey: 'sample_request.delete',
    entityType: 'sample_request',
    entityId: requestId,
    verb: 'Deleting',
    subject: request?.request_no ?? 'this draft',
    surface: 'inline',
    watchFromMount: true,
    successMessage: 'Draft deleted',
    invalidateKeys: [['sample-requests']],
    onCommitted: () => router.push(origin ?? BASE_PATH),
  });

  const lineColumns = useMemo<ColumnDef<SampleRequestLine>[]>(
    () => [
      {
        id: 'line_no',
        accessorKey: 'line_no',
        header: ({ column }) => <DataGridColumnHeader title="No" column={column} />,
        size: 80,
        cell: ({ row }) => (
          <button
            type="button"
            className="inline-flex items-center gap-1"
            aria-label={`Stock for line ${row.original.line_no}`}
            aria-expanded={row.getIsExpanded()}
            onClick={(event) => {
              event.stopPropagation();
              row.toggleExpanded();
            }}
          >
            {row.getIsExpanded() ? (
              <ChevronDown className="size-4" />
            ) : (
              <ChevronRight className="size-4" />
            )}
            {row.original.line_no}
          </button>
        ),
        meta: {
          headerTitle: 'No',
          expandedContent: (line: SampleRequestLine) => (
            <div className="px-2 pb-3">
              <OrderInquiryStockGrid productId={line.product_id} location="BRW" />
            </div>
          ),
        },
      },
      {
        id: 'brand_name',
        accessorFn: (row) => row.brand_name ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Brand" column={column} />,
        size: 140,
        cell: ({ row }) => (
          <span className="truncate" title={row.original.brand_name ?? undefined}>
            {row.original.brand_name || '-'}
          </span>
        ),
        meta: { headerTitle: 'Brand' },
      },
      {
        id: 'model',
        accessorFn: (row) => row.product_code ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Model" column={column} />,
        size: 170,
        cell: ({ row }) => (
          <div className="flex min-w-0 flex-wrap items-center gap-1.5">
            <span className="truncate" title={row.original.product_code ?? undefined}>
              {row.original.product_code || '-'}
            </span>
            {!row.original.product_active && <Badge variant="secondary">Inactive</Badge>}
          </div>
        ),
        meta: { headerTitle: 'Model' },
      },
      {
        id: 'description',
        accessorFn: (row) => row.product_name ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Description" column={column} />,
        size: 240,
        cell: ({ row }) => (
          <span className="truncate" title={row.original.product_name ?? undefined}>
            {row.original.product_name || '-'}
          </span>
        ),
        meta: { headerTitle: 'Description' },
      },
      {
        id: 'qty',
        accessorKey: 'qty',
        header: ({ column }) => <DataGridColumnHeader title="Qty" column={column} />,
        size: 80,
        cell: ({ row }) => row.original.qty,
        meta: { headerTitle: 'Qty' },
      },
      {
        id: 'remark',
        accessorFn: (row) => row.remark ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Remark" column={column} />,
        size: 200,
        cell: ({ row }) => (
          <span className="truncate" title={row.original.remark ?? undefined}>
            {row.original.remark || '-'}
          </span>
        ),
        meta: { headerTitle: 'Remark' },
      },
    ],
    [],
  );

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }
  if (isError || !request) {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-10 text-center text-sm">
        {error instanceof Error ? error.message : 'This sample request could not be loaded.'}
      </div>
    );
  }

  const r: Detail = request;
  const isDraft = r.status === 'draft';
  const isOwner = Boolean(userId) && r.salesperson_id === userId;
  const ownerActs = isOwner && canCreate;
  const busy = move.isPending || submit.isPending;
  const allowed = (m: Move) => canProcess || (m.needs === 'either' && ownerActs);
  const moves = MOVES[r.status].filter(allowed);

  const run = async (m: Move, value?: string, answer?: DateAnswerValue) => {
    try {
      await move.mutateAsync({
        id: r.id,
        body: {
          to: m.to,
          ...(m.ask === 'date' && value ? { date: value } : {}),
          ...(m.ask === 'reason' && value ? { reason: value } : {}),
          ...(m.ask === 'answer' && answer ? answer : {}),
        },
      });
      setAsking(null);
    } catch {
      // the mutation's own onError toast names the refusal
    }
  };

  const stamp = r.submitted_at ?? r.created_at;
  const answerText = dateAnswerText(r, formatDateInMalaysia);
  const canLink = canProcess && ['processing', 'delivered'].includes(r.status);
  const canAnswer = canProcess && r.status === 'processing';
  const project = r.project_id
    ? [r.project_code, r.project_name].filter(Boolean).join(' - ')
    : r.project_name;
  const shipTo = [r.ship_to_name, r.ship_to_address].filter(Boolean).join(', ');
  const siteContact = [r.site_contact_name, r.site_contact_phone, r.site_contact_note]
    .filter(Boolean)
    .join(', ');

  return (
    <div className="space-y-6">
      {/* Above the tab strip, on every tab, so prev/next works from any tab (NAV-KEEP-TAB). */}
      <RecordCardSlot>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 space-y-1">
          <h2 className="break-words text-2xl font-bold">Sample Request - {r.request_no}</h2>
          {/* Separate items, no dot delimiter (owner hand test 12 Nov). */}
          <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
            <span>
              {r.submitted_at ? 'Submitted' : 'Created'}: {stamp ? formatDateInMalaysia(stamp) : '-'}
            </span>
            <span className={`${STATUS_PILL_BASE} ${statusPillClass(r.status)}`}>
              {r.status_label}
            </span>
          </div>
        </div>
        <DetailActions
          pager={{
            // From a project's tab, prev/next walks that project's requests (owner 11 Nov 19:40).
            ...(originProject && origin
              ? projectPagerQuery(originProject, origin)
              : sampleRequestsPagerQuery),
            detailPath: BASE_PATH,
            currentId: requestId,
            ariaLabel: 'sample request',
          }}
          gearLabel="Sample request actions"
          pendingAction={deletion.countdown}
          gear={
            <DetailActionsMenu ariaLabel="Sample request actions">
              <DropdownMenuItem
                onSelect={() => {
                  void downloadSampleRequestPdf(r.id, r.request_no).catch((e) =>
                    toast.error(e instanceof Error ? e.message : 'Failed to download the PDF'),
                  );
                }}
              >
                <Printer className="size-4" />
                Print / Download PDF
              </DropdownMenuItem>
              <DropdownMenuItem
                onSelect={() => {
                  void navigator.clipboard
                    .writeText(window.location.href)
                    .then(() => toast.success('Link copied'))
                    .catch(() => toast.error('Could not copy the link'));
                }}
              >
                <Link2 className="size-4" />
                Copy link
              </DropdownMenuItem>
              {canLink && (
                <DropdownMenuItem onSelect={() => setConsignmentOpen(true)}>
                  <PackageCheck className="size-4" />
                  Link consignment
                </DropdownMenuItem>
              )}
              {canAnswer && (
                <DropdownMenuItem onSelect={() => setAnswerOpen(true)}>
                  <CalendarClock className="size-4" />
                  Change date answer
                </DropdownMenuItem>
              )}
              {canProcess && r.status !== 'cancelled' && (
                <DropdownMenuItem onSelect={() => setInternalOpen(true)}>
                  <Settings2 className="size-4" />
                  Set consignment / PO no
                </DropdownMenuItem>
              )}
              {isDraft && ownerActs && (
                <DropdownMenuItem
                  variant="destructive"
                  disabled={deletion.isBlocked}
                  onSelect={() => deletion.start()}
                >
                  <Trash2 className="size-4" />
                  Delete draft
                </DropdownMenuItem>
              )}
            </DetailActionsMenu>
          }
          primary={
            <div className="flex flex-wrap items-center gap-2">
              {isDraft && ownerActs && (
                <Button
                  disabled={busy}
                  onClick={() =>
                    submit.mutate(r.id, {
                      onSuccess: (done) =>
                        toast.success(`Sample request ${done?.request_no ?? r.request_no} submitted`),
                    })
                  }
                >
                  Submit
                </Button>
              )}
              {moves.map((m) => (
                <Button
                  key={m.to}
                  variant={m.tone === 'destructive' ? 'outline' : 'primary'}
                  className={MOVE_CLASS[m.tone]}
                  disabled={busy}
                  onClick={() => (m.ask ? setAsking(m) : void run(m))}
                >
                  {m.label}
                </Button>
              ))}
              {isDraft && ownerActs && (
                <Button variant="outline" asChild>
                  <Link href={withReviewOrigin(`${BASE_PATH}/${r.id}/edit`, origin)}>Edit</Link>
                </Button>
              )}
            </div>
          }
        />
      </div>
      </RecordCardSlot>

      <Card className="border-2 shadow-sm">
        <CardContent className="px-5 pb-8 pt-6 sm:px-10">
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <Badge variant="secondary">{r.source === 'portal' ? 'Portal' : 'Staff'}</Badge>
            <span className={`${STATUS_PILL_BASE} ${statusPillClass(r.status)}`}>
              {r.status_label}
            </span>
          </div>
          <h2 className="mb-6 border-b border-border pb-4 text-center text-xl font-semibold tracking-tight">
            Sample Request
          </h2>
          <div className="grid grid-cols-1 gap-x-10 gap-y-5 sm:grid-cols-2 [&>div]:min-w-0 [&_p]:break-words">
            <Field label="Requested by">{r.salesperson_name}</Field>
            <div>
              <p className="text-sm text-muted-foreground">Customer</p>
              <p className="flex flex-wrap items-center gap-2 font-medium">
                {[r.customer_code, r.customer_name].filter(Boolean).join(' - ') || 'None'}
                {!r.customer_code && r.customer_name && (
                  <Badge variant="secondary">No debtor code</Badge>
                )}
              </p>
            </div>
            <Field label="Project" wide>
              <span className="line-clamp-2 break-words" title={project ?? undefined}>
                {project}
                {!r.project_id && r.project_name ? ' (not registered)' : ''}
              </span>
            </Field>
            {r.quotation_ref && <Field label="Quotation">{r.quotation_ref}</Field>}
            {/* Removed from the form (SAMPLE-REQUEST-V2 rule 3): only an old request that had it shows it. */}
            {r.scope_note && <Field label="For (scope)">{r.scope_note}</Field>}
            <Field label="Request Delivery Date">
              {day(r.delivery_date)}
            </Field>
            <div>
              <p className="text-sm text-muted-foreground">Sample team</p>
              <p className="flex flex-wrap items-center gap-2 font-medium">
                {answerText ?? 'Not answered yet'}
                {r.date_feasible === false && <Badge variant="warning">New date</Badge>}
              </p>
              {r.date_note && (
                <p className="text-sm whitespace-pre-wrap text-muted-foreground">{r.date_note}</p>
              )}
            </div>
            <Field label="Delivery">
              {r.delivery_mode ? DELIVERY_MODE_LABELS[r.delivery_mode] : null}
            </Field>
            <Field label="Ship to" wide>
              {shipTo}
            </Field>
            <Field label="Site contact" wide>
              {siteContact}
            </Field>
            <Field label="Sample board" wide>
              {r.board_mounting ? `Mount & label: ${r.board_label ?? ''}` : null}
            </Field>
            <Field label="Loan Period">
              {r.loan_value ? `${r.loan_value} ${r.loan_unit}` : null}
            </Field>
            <Field label="Goods Taken From">
              {r.goods_from ? GOODS_FROM_LABELS[r.goods_from] : null}
            </Field>
            <Field label="Purpose" wide>
              {r.purpose}
            </Field>
            {r.delivered_at && (
              <Field label="Delivered">
                {day(r.delivered_at)}
                {/* The source is worked out live; name it only while it still gives the stored date. */}
                {r.consignment?.delivered_source &&
                r.consignment.delivered_on === r.delivered_at
                  ? ` (${DELIVERED_SOURCE_LABELS[r.consignment.delivered_source]})`
                  : ''}
              </Field>
            )}
            {r.return_due && <Field label="Return due">{day(r.return_due)}</Field>}
            {r.cancel_reason && (
              <Field label="Cancel reason" wide>
                {r.cancel_reason}
              </Field>
            )}
            <div>
              <p className="text-sm text-muted-foreground">Consignment No</p>
              <p className="flex flex-wrap items-center gap-2 font-medium">
                {r.consignment
                  ? [r.consignment.so_number, day(r.consignment.order_date)]
                      .filter(Boolean)
                      .join(' - ')
                  : r.consignment_no || 'Not linked'}
                {r.consignment?.status === 'cancelled' && (
                  <Badge variant="destructive">Voided in AutoCount</Badge>
                )}
              </p>
              <SoCustomerProject
                customer={r.consignment?.customer_name}
                project={r.consignment?.project_label}
                className="text-sm"
              />
            </div>
            <Field label="PO No (internal)" empty="Not set">
              {r.po_no}
            </Field>
          </div>

          <div className="mt-8">
            <p className="mb-3 text-sm font-medium">Line items</p>
            <PanelDataGrid
              columns={lineColumns}
              rows={r.lines}
              getRowId={(row) => row.id}
              // Column preferences are keyed by a slug the reader holds: view for the
              // coordinator, create for the owning salesperson (list_query._can_view_listing_key).
              listingKey={
                canViewRecord
                  ? 'projects.sample_requests.view::sample-request-lines'
                  : 'projects.sample_requests.create::sample-request-lines'
              }
              emptyTitle="No items"
              paginate={false}
              expanded={expanded}
              onExpandedChange={setExpanded}
            />
          </div>
        </CardContent>
      </Card>

      {canViewRecord && (
        <AuditTrail entityType="project_sample_requests" entityId={requestId} title="Audit Trail" />
      )}

      {asking?.ask === 'answer' && (
        <DateAnswerDialog
          title={asking.label}
          confirmLabel={asking.label}
          requested={r.delivery_date ?? null}
          busy={move.isPending}
          onCancel={() => setAsking(null)}
          onConfirm={(answer) => void run(asking, undefined, answer)}
        />
      )}
      {consignmentOpen && (
        <ConsignmentDialog
          request={r}
          busy={linkConsignment.isPending}
          onCancel={() => setConsignmentOpen(false)}
          onLink={(consignmentOrderId) =>
            linkConsignment.mutate(
              { id: r.id, consignmentOrderId },
              { onSuccess: () => setConsignmentOpen(false) },
            )
          }
        />
      )}
      {answerOpen && (
        <DateAnswerDialog
          title="Change date answer"
          confirmLabel="Save"
          requested={r.delivery_date ?? null}
          initial={r}
          busy={answerDate.isPending}
          onCancel={() => setAnswerOpen(false)}
          onConfirm={(body) =>
            answerDate.mutate({ id: r.id, body }, { onSuccess: () => setAnswerOpen(false) })
          }
        />
      )}
      {asking && asking.ask !== 'answer' && (
        <AskDialog
          move={asking}
          busy={move.isPending}
          onCancel={() => setAsking(null)}
          onConfirm={(value) => void run(asking, value)}
        />
      )}
      {internalOpen && (
        <InternalDialog
          request={r}
          busy={saveInternal.isPending}
          onCancel={() => setInternalOpen(false)}
          onSave={(body) =>
            saveInternal.mutate({ id: r.id, body }, { onSuccess: () => setInternalOpen(false) })
          }
        />
      )}
    </div>
  );
}
