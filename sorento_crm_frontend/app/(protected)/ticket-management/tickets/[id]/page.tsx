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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { Container } from '@/components/common/container';
import {
  Toolbar,
  ToolbarActions,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';
import EntityActivitiesLayout from '@/components/common/ActivitiesNotesPanel/EntityActivitiesLayout';
import {
  changeTicketStatus,
  getTicket,
  updateTicketResolution,
  updateTicketResponse,
} from '../services/ticketService';
import {
  TICKET_STATUSES,
  type Ticket,
  type TicketStatus,
} from '../types/ticket.types';
import {
  TicketPriorityBadge,
  TicketStatusBadge,
} from '../components/TicketStatusBadge';
import TicketWatchersSection from '../components/TicketWatchersSection';

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
  const [busy, setBusy] = useState(false);

  async function reload() {
    setLoading(true);
    try {
      const t = await getTicket(id);
      setTicket(t);
      setResponseDraft(t.response_text ?? '');
      setResolutionDraft(t.resolution_text ?? '');
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

  async function saveResponse() {
    if (!ticket) return;
    setBusy(true);
    try {
      const updated = await updateTicketResponse(ticket.id, {
        response_text: responseDraft,
        response_html: `<p>${responseDraft.replace(/\n/g, '<br>')}</p>`,
      });
      setTicket(updated);
      setEditingResponse(false);
      toast.success('Response saved');
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function saveResolution() {
    if (!ticket) return;
    setBusy(true);
    try {
      const updated = await updateTicketResolution(ticket.id, {
        resolution_text: resolutionDraft,
        resolution_html: `<p>${resolutionDraft.replace(/\n/g, '<br>')}</p>`,
      });
      setTicket(updated);
      setEditingResolution(false);
      toast.success('Resolution saved');
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
          </ToolbarActions>
        </Toolbar>
      </Container>

      <EntityActivitiesLayout entityType="ticket" entityId={ticket.id}>
        <Container>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* main column */}
            <div className="lg:col-span-2 flex flex-col gap-4">
              <Card className="p-5">
                <div className="flex items-center gap-2 mb-3">
                  <TicketStatusBadge status={ticket.status} />
                  <TicketPriorityBadge priority={ticket.priority} />
                  <span className="text-sm text-muted-foreground capitalize">{ticket.category}</span>
                  <span className="ms-auto text-xs text-muted-foreground">
                    Updated {new Date(ticket.updated_at).toLocaleString()}
                  </span>
                </div>
                <h2 className="text-xl font-semibold mb-2">{ticket.title}</h2>
                <div className="prose prose-sm max-w-none whitespace-pre-wrap text-sm">
                  {ticket.description_text ?? <span className="text-muted-foreground">No description.</span>}
                </div>
              </Card>

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
                    <Textarea
                      rows={5}
                      value={responseDraft}
                      onChange={(e) => setResponseDraft(e.target.value)}
                      placeholder="Your reply to the submitter…"
                    />
                    <div className="flex gap-2 justify-end">
                      <Button variant="outline" size="sm" onClick={() => { setEditingResponse(false); setResponseDraft(ticket.response_text ?? ''); }} disabled={busy}>
                        Cancel
                      </Button>
                      <Button size="sm" onClick={saveResponse} disabled={busy || !responseDraft.trim()}>
                        Save
                      </Button>
                    </div>
                  </div>
                ) : ticket.response_text ? (
                  <div className="text-sm whitespace-pre-wrap">{ticket.response_text}</div>
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
                    <Textarea
                      rows={5}
                      value={resolutionDraft}
                      onChange={(e) => setResolutionDraft(e.target.value)}
                      placeholder="How was this resolved?"
                    />
                    <div className="flex gap-2 justify-end">
                      <Button variant="outline" size="sm" onClick={() => { setEditingResolution(false); setResolutionDraft(ticket.resolution_text ?? ''); }} disabled={busy}>
                        Cancel
                      </Button>
                      <Button size="sm" onClick={saveResolution} disabled={busy || !resolutionDraft.trim()}>
                        Save
                      </Button>
                    </div>
                  </div>
                ) : ticket.resolution_text ? (
                  <div className="text-sm whitespace-pre-wrap">{ticket.resolution_text}</div>
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
                    <span>{ticket.raised_by_user?.display_name ?? '—'}</span>
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
        </Container>
      </EntityActivitiesLayout>
    </>
  );
}
