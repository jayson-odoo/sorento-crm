'use client';

import { use, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { RichTextEditor } from '@/components/ui/rich-text-editor';
import { Container } from '@/components/common/container';
import {
  Toolbar,
  ToolbarActions,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';
import EntityActivitiesLayout from '@/components/common/ActivitiesNotesPanel/EntityActivitiesLayout';
import FormDetailWithSLATabs from '@/app/(protected)/sla-management/_shared/FormDetailWithSLATabs';
import {
  cancelTicketDraft,
  changeTicketStatus,
  deleteTicket,
  getTicket,
  submitTicketDraft,
  updateTicket,
  updateTicketResolution,
  updateTicketResolutionAndReply,
  updateTicketResponse,
  updateTicketResponseAndReply,
} from '../services/ticketService';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { Trash2 } from 'lucide-react';
import {
  TICKET_CATEGORIES,
  TICKET_PRIORITIES,
  TICKET_STATUSES,
  type Ticket,
  type TicketCategory,
  type TicketPriority,
  type TicketStatus,
} from '../types/ticket.types';
import {
  TicketPriorityBadge,
  TicketStatusBadge,
} from '../components/TicketStatusBadge';
import TicketWatchersSection from '../components/TicketWatchersSection';
import TicketSourceCard from '../components/TicketSourceCard';

function htmlToText(html: string): string {
  if (typeof window === 'undefined') return html.replace(/<[^>]+>/g, '').trim();
  const doc = new DOMParser().parseFromString(html || '', 'text/html');
  return (doc.body.textContent || '').trim();
}

function formatDuration(hours: number | string | null | undefined): string {
  if (hours === null || hours === undefined) return '—';
  const n = typeof hours === 'string' ? parseFloat(hours) : hours;
  if (!Number.isFinite(n)) return '—';
  if (n < 1) return `${Math.round(n * 60)}m`;
  return `${n.toFixed(1)}h`;
}

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function TicketDetailPage({ params }: PageProps) {
  const { id } = use(params);
  const router = useRouter();
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [loading, setLoading] = useState(true);
  const [responseDraft, setResponseDraft] = useState('');
  const [editingResponse, setEditingResponse] = useState(false);
  const [resolutionDraft, setResolutionDraft] = useState('');
  const [editingResolution, setEditingResolution] = useState(false);
  const [editingDetails, setEditingDetails] = useState(false);
  const [titleDraft, setTitleDraft] = useState('');
  const [descriptionDraft, setDescriptionDraft] = useState('');
  const [priorityDraft, setPriorityDraft] = useState<TicketPriority>('medium');
  const [categoryDraft, setCategoryDraft] = useState<TicketCategory>('bug');
  const [busy, setBusy] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  async function reload() {
    setLoading(true);
    try {
      const t = await getTicket(id);
      setTicket(t);
      setResponseDraft(t.response_html ?? '');
      setResolutionDraft(t.resolution_html ?? '');
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void reload();
     
  }, [id]);

  async function changeStatus(newStatus: TicketStatus) {
    if (!ticket) return;
    setBusy(true);
    try {
      const updated = await changeTicketStatus(ticket.id, { new_status: newStatus });
      setTicket(updated);
      toast.success(`Status → ${newStatus}`);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function submitDraft() {
    if (!ticket) return;
    setBusy(true);
    try {
      const updated = await submitTicketDraft(ticket.id);
      setTicket(updated);
      toast.success('Ticket submitted to IT admin');
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function startEditDetails() {
    if (!ticket) return;
    setTitleDraft(ticket.title);
    setDescriptionDraft(ticket.description_html ?? ticket.description_text ?? '');
    setPriorityDraft(ticket.priority);
    setCategoryDraft(ticket.category);
    setEditingDetails(true);
  }

  async function saveDetails() {
    if (!ticket) return;
    const title = titleDraft.trim();
    if (!title) {
      toast.error('Title is required');
      return;
    }
    setBusy(true);
    try {
      const updated = await updateTicket(ticket.id, {
        title,
        description_html: descriptionDraft || null,
        description_text: htmlToText(descriptionDraft) || null,
        priority: priorityDraft,
        category: categoryDraft,
      });
      setTicket(updated);
      setEditingDetails(false);
      toast.success('Ticket updated');
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function cancelDraft() {
    if (!ticket) return;
    if (!window.confirm('Cancel this draft? This cannot be undone.')) return;
    setBusy(true);
    try {
      await cancelTicketDraft(ticket.id);
      toast.success('Draft cancelled');
      router.push('/ticket-management/tickets');
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function saveResponse(reply: boolean) {
    if (!ticket) return;
    setBusy(true);
    try {
      const payload = {
        response_text: htmlToText(responseDraft),
        response_html: responseDraft,
      };
      const updated = reply
        ? await updateTicketResponseAndReply(ticket.id, payload)
        : await updateTicketResponse(ticket.id, payload);
      setTicket(updated);
      setEditingResponse(false);
      toast.success(reply ? 'Response sent and ticket marked responded' : 'Response saved');
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function saveResolution(reply: boolean) {
    if (!ticket) return;
    setBusy(true);
    try {
      const payload = {
        resolution_text: htmlToText(resolutionDraft),
        resolution_html: resolutionDraft,
      };
      const updated = reply
        ? await updateTicketResolutionAndReply(ticket.id, payload)
        : await updateTicketResolution(ticket.id, payload);
      setTicket(updated);
      setEditingResolution(false);
      toast.success(reply ? 'Resolution sent and ticket marked resolved' : 'Resolution saved');
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (loading || !ticket) {
    return (
      <Container>
        <div className="py-8">
          <Skeleton className="h-8 w-64 mb-4" />
          <Skeleton className="h-32 w-full" />
        </div>
      </Container>
    );
  }

  return (
    <>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>{ticket.ticket_number ?? 'Ticket'}</ToolbarTitle>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink href="/">Home</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbLink href="/ticket-management/tickets">
                    Tickets
                  </BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>{ticket.ticket_number ?? ticket.id}</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
          <ToolbarActions>
            <Button variant="outline" onClick={() => router.push('/ticket-management/tickets')}>
              Back to list
            </Button>
            <Button
              variant="destructive"
              onClick={() => setDeleteOpen(true)}
              disabled={busy}
            >
              <Trash2 className="size-4" />
              Delete
            </Button>
          </ToolbarActions>
        </Toolbar>
      </Container>

      <EntityActivitiesLayout entityType="ticket" entityId={ticket.id}>
        <Container>
          <FormDetailWithSLATabs sourceEntityType="ticket" sourceEntityId={ticket.id}>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* main column */}
            <div className="lg:col-span-2 min-w-0 flex flex-col gap-4">
              <Card className="p-5">
                <div className="flex items-center gap-2 mb-3">
                  <TicketStatusBadge status={ticket.status} />
                  <TicketPriorityBadge priority={ticket.priority} />
                  <span className="text-sm text-muted-foreground capitalize">{ticket.category}</span>
                  <span className="ms-auto text-xs text-muted-foreground">
                    Updated {new Date(ticket.updated_at).toLocaleString()}
                  </span>
                  {!editingDetails && ticket.status === 'draft' && (
                    <Button variant="ghost" size="sm" onClick={startEditDetails}>
                      Edit
                    </Button>
                  )}
                </div>
                {editingDetails ? (
                  <div className="flex flex-col gap-3">
                    <div className="flex flex-col gap-1">
                      <Label htmlFor="ticket-title">Title</Label>
                      <Input
                        id="ticket-title"
                        value={titleDraft}
                        onChange={(e) => setTitleDraft(e.target.value)}
                        disabled={busy}
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div className="flex flex-col gap-1">
                        <Label>Priority</Label>
                        <Select
                          value={priorityDraft}
                          onValueChange={(v) => setPriorityDraft(v as TicketPriority)}
                          disabled={busy}
                        >
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {TICKET_PRIORITIES.map((p) => (
                              <SelectItem key={p} value={p} className="capitalize">
                                {p}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="flex flex-col gap-1">
                        <Label>Category</Label>
                        <Select
                          value={categoryDraft}
                          onValueChange={(v) => setCategoryDraft(v as TicketCategory)}
                          disabled={busy}
                        >
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {TICKET_CATEGORIES.map((c) => (
                              <SelectItem key={c} value={c} className="capitalize">
                                {c}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                    <div className="flex flex-col gap-1">
                      <Label>Description</Label>
                      <RichTextEditor
                        value={descriptionDraft}
                        onChange={setDescriptionDraft}
                        placeholder="What is wrong?"
                        minHeight={140}
                      />
                    </div>
                    <div className="flex gap-2 justify-end">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setEditingDetails(false)}
                        disabled={busy}
                      >
                        Cancel
                      </Button>
                      <Button size="sm" onClick={saveDetails} disabled={busy || !titleDraft.trim()}>
                        Save
                      </Button>
                    </div>
                  </div>
                ) : (
                  <>
                    <h2 className="text-xl font-semibold mb-2">{ticket.title}</h2>
                    {ticket.description_html ? (
                      <div
                        className="prose prose-sm max-w-none text-sm break-words [&_pre]:whitespace-pre-wrap [&_pre]:break-all [&_code]:break-all"
                        dangerouslySetInnerHTML={{ __html: ticket.description_html }}
                      />
                    ) : ticket.description_text ? (
                      <div className="prose prose-sm max-w-none whitespace-pre-wrap break-words text-sm">{ticket.description_text}</div>
                    ) : (
                      <span className="text-muted-foreground text-sm">No description.</span>
                    )}
                  </>
                )}
              </Card>

              <TicketSourceCard ticket={ticket} />

              {ticket.status === 'draft' && (
                <Card className="p-4 flex flex-col gap-3 border-primary/40 bg-primary/5">
                  <div className="text-sm">
                    <span className="font-medium">Draft ticket.</span>{' '}
                    Review the details above. Click <strong>Submit to IT admin</strong> to send it to the team
                    (round-robin assigns a tier-1 IT admin and starts the SLA timer). Click{' '}
                    <strong>Cancel</strong> to discard this draft.
                  </div>
                  <div className="flex gap-2 justify-end">
                    <Button variant="outline" size="sm" onClick={cancelDraft} disabled={busy}>
                      Cancel
                    </Button>
                    <Button size="sm" onClick={submitDraft} disabled={busy}>
                      Submit to IT admin
                    </Button>
                  </div>
                </Card>
              )}

              {/* SLA strip */}
              <Card className="p-4 flex flex-wrap items-center gap-4 text-sm">
                <div>
                  <span className="text-muted-foreground">Response time:</span>{' '}
                  <span className={ticket.is_overdue_response ? 'text-destructive font-medium' : ''}>
                    {ticket.first_response_at
                      ? formatDuration(ticket.response_time_hours ?? null)
                      : ticket.is_overdue_response
                      ? 'Overdue'
                      : 'Awaiting response'}
                  </span>
                </div>
                <div>
                  <span className="text-muted-foreground">Resolution time:</span>{' '}
                  <span className={ticket.is_overdue_resolution ? 'text-destructive font-medium' : ''}>
                    {ticket.resolved_at
                      ? formatDuration(ticket.resolution_time_hours ?? null)
                      : ticket.is_overdue_resolution
                      ? 'Overdue'
                      : 'Awaiting resolution'}
                  </span>
                </div>
              </Card>

              {ticket.status !== 'draft' && (<>
              {/* Response card */}
              <Card className="p-5">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-sm font-semibold">Response</h3>
                  {!editingResponse && (
                    <Button variant="ghost" size="sm" onClick={() => setEditingResponse(true)}>
                      Edit
                    </Button>
                  )}
                </div>
                {editingResponse ? (
                  <div className="flex flex-col gap-2">
                    <RichTextEditor
                      value={responseDraft}
                      onChange={setResponseDraft}
                      placeholder="Your reply to the submitter…"
                      minHeight={140}
                    />
                    <div className="flex gap-2 justify-end">
                      <Button variant="outline" size="sm" onClick={() => { setEditingResponse(false); setResponseDraft(ticket.response_html ?? ''); }} disabled={busy}>
                        Cancel
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => saveResponse(false)} disabled={busy || !htmlToText(responseDraft)}>
                        Save
                      </Button>
                      <Button size="sm" onClick={() => saveResponse(true)} disabled={busy || !htmlToText(responseDraft)}>
                        Update &amp; Reply
                      </Button>
                    </div>
                  </div>
                ) : ticket.response_html ? (
                  <div
                    className="text-sm prose prose-sm max-w-none break-words [&_pre]:whitespace-pre-wrap [&_pre]:break-all [&_code]:break-all"
                    dangerouslySetInnerHTML={{ __html: ticket.response_html }}
                  />
                ) : (
                  <div className="text-sm text-muted-foreground">No response yet.</div>
                )}
                {ticket.responded_by_user && (
                  <div className="text-xs text-muted-foreground mt-2">
                    by {ticket.responded_by_user.display_name}
                    {ticket.responded_at && ` · ${new Date(ticket.responded_at).toLocaleString()}`}
                  </div>
                )}
              </Card>

              {/* Resolution card */}
              <Card className="p-5">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-sm font-semibold">Resolution</h3>
                  {!editingResolution && (
                    <Button variant="ghost" size="sm" onClick={() => setEditingResolution(true)}>
                      Edit
                    </Button>
                  )}
                </div>
                {editingResolution ? (
                  <div className="flex flex-col gap-2">
                    <RichTextEditor
                      value={resolutionDraft}
                      onChange={setResolutionDraft}
                      placeholder="How was this resolved?"
                      minHeight={140}
                    />
                    <div className="flex gap-2 justify-end">
                      <Button variant="outline" size="sm" onClick={() => { setEditingResolution(false); setResolutionDraft(ticket.resolution_html ?? ''); }} disabled={busy}>
                        Cancel
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => saveResolution(false)} disabled={busy || !htmlToText(resolutionDraft)}>
                        Save
                      </Button>
                      <Button size="sm" onClick={() => saveResolution(true)} disabled={busy || !htmlToText(resolutionDraft)}>
                        Update &amp; Reply
                      </Button>
                    </div>
                  </div>
                ) : ticket.resolution_html ? (
                  <div
                    className="text-sm prose prose-sm max-w-none break-words [&_pre]:whitespace-pre-wrap [&_pre]:break-all [&_code]:break-all"
                    dangerouslySetInnerHTML={{ __html: ticket.resolution_html }}
                  />
                ) : (
                  <div className="text-sm text-muted-foreground">Not resolved yet.</div>
                )}
                {ticket.resolved_by_user && (
                  <div className="text-xs text-muted-foreground mt-2">
                    by {ticket.resolved_by_user.display_name}
                    {ticket.resolved_at && ` · ${new Date(ticket.resolved_at).toLocaleString()}`}
                  </div>
                )}
              </Card>
              </>)}
            </div>

            {/* sidebar */}
            <Card className="p-5 flex flex-col gap-4 h-fit">
              <div>
                <h4 className="text-xs font-semibold uppercase text-muted-foreground mb-2">Details</h4>
                <div className="flex flex-col gap-3 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Status</span>
                    <Select
                      value={ticket.status}
                      onValueChange={(v) => changeStatus(v as TicketStatus)}
                      disabled={busy}
                    >
                      <SelectTrigger className="w-[140px] h-8">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {TICKET_STATUSES.map((s) => (
                          <SelectItem key={s} value={s}>
                            {s.charAt(0).toUpperCase() + s.slice(1)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Reporter</span>
                    <span>
                      {ticket.raised_by_actor?.display_name
                        ?? ticket.raised_by_user?.display_name
                        ?? '—'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Assignee</span>
                    <span>{ticket.assigned_to_user?.display_name ?? <span className="text-muted-foreground">Unassigned</span>}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Priority</span>
                    <TicketPriorityBadge priority={ticket.priority} />
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Category</span>
                    <span className="capitalize">{ticket.category}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Due date</span>
                    <span>{ticket.due_date ?? '—'}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Created</span>
                    <span>{new Date(ticket.created_at).toLocaleString()}</span>
                  </div>
                </div>
              </div>

              <TicketWatchersSection ticket={ticket} onChange={setTicket} />

              <div>
                <h4 className="text-xs font-semibold uppercase text-muted-foreground mb-2">
                  Attachments ({ticket.attachments.length})
                </h4>
                {ticket.attachments.length === 0 ? (
                  <span className="text-sm text-muted-foreground">None.</span>
                ) : (
                  <ul className="flex flex-col gap-1 text-sm">
                    {ticket.attachments.map((a) => (
                      <li key={a.id} className="font-mono text-xs">{a.attachment_id}</li>
                    ))}
                  </ul>
                )}
              </div>
            </Card>
          </div>
          </FormDetailWithSLATabs>
        </Container>
      </EntityActivitiesLayout>

      <ConfirmDeleteDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        description={
          <>
            Permanently delete ticket <strong>{ticket.ticket_number ?? ticket.id}</strong>? This action cannot be undone.
          </>
        }
        onDelete={async () => {
          await deleteTicket(ticket.id);
        }}
        successMessage="Ticket deleted"
        onSuccess={() => router.push('/ticket-management/tickets')}
      />
    </>
  );
}
