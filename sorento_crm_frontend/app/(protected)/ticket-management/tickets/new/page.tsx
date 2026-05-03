'use client';

import { useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { Paperclip, X } from 'lucide-react';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Container } from '@/components/common/container';
import {
  Toolbar,
  ToolbarActions,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';
import { uploadAttachment } from '@/app/(protected)/resource-management/attachments/services/attachmentService';
import { createTicket } from '../services/ticketService';
import {
  TICKET_CATEGORIES,
  TICKET_PRIORITIES,
  type TicketCategory,
  type TicketPriority,
} from '../types/ticket.types';

interface PendingFile {
  /** Stable per-pick id so removing one doesn't disturb others. */
  key: string;
  file: File;
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export default function NewTicketPage() {
  const router = useRouter();
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState<TicketPriority>('medium');
  const [category, setCategory] = useState<TicketCategory>('question');
  const [dueDate, setDueDate] = useState('');
  const [files, setFiles] = useState<PendingFile[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function addFiles(picked: FileList | File[] | null) {
    if (!picked) return;
    const arr = Array.from(picked);
    if (arr.length === 0) return;
    setFiles((prev) => [
      ...prev,
      ...arr.map((file) => ({
        key: `${file.name}-${file.size}-${file.lastModified}-${Math.random().toString(36).slice(2, 8)}`,
        file,
      })),
    ]);
  }

  function removeFile(key: string) {
    setFiles((prev) => prev.filter((p) => p.key !== key));
  }

  function onDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer?.files) addFiles(e.dataTransfer.files);
  }

  function onDragOver(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
    if (!dragActive) setDragActive(true);
  }

  function onDragLeave(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
    if (e.currentTarget === e.target) setDragActive(false);
  }

  async function uploadAllPending(): Promise<string[]> {
    if (files.length === 0) return [];
    const ids: string[] = [];
    for (const p of files) {
      // entity_type / entity_id intentionally omitted: ticket doesn't exist
      // yet. Backend create_ticket links each attachment_id below into
      // EntityAttachmentLink with the new ticket id.
      const att = await uploadAttachment(p.file, { entityType: 'ticket' });
      ids.push(att.id);
    }
    return ids;
  }

  async function submit(saveAsDraft: boolean) {
    if (!title.trim()) {
      toast.error('Title is required');
      return;
    }
    setSubmitting(true);
    try {
      const attachment_ids = await uploadAllPending();
      const t = await createTicket({
        title: title.trim(),
        description_text: description || null,
        description_html: description
          ? `<p>${description.replace(/\n/g, '<br>')}</p>`
          : null,
        priority,
        category,
        due_date: dueDate || null,
        save_as_draft: saveAsDraft,
        attachment_ids,
      });
      toast.success(
        saveAsDraft ? 'Draft saved' : `${t.ticket_number ?? 'Ticket'} submitted`,
      );
      router.push(`/ticket-management/tickets/${t.id}`);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Create ticket</ToolbarTitle>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink href="/">Home</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbLink href="/ticket-management/tickets">
                    Ticket Management
                  </BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>New</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
          <ToolbarActions />
        </Toolbar>
      </Container>

      <Container>
        <div className="max-w-3xl flex flex-col gap-5 rounded-md border bg-card p-6">
          <div className="flex flex-col gap-2">
            <Label htmlFor="title">Title *</Label>
            <Input
              id="title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Short summary of the issue…"
              maxLength={255}
              autoFocus
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="flex flex-col gap-2">
              <Label>Priority</Label>
              <Select
                value={priority}
                onValueChange={(v) => setPriority(v as TicketPriority)}
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {TICKET_PRIORITIES.map((p) => (
                    <SelectItem key={p} value={p}>
                      {p.charAt(0).toUpperCase() + p.slice(1)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-2">
              <Label>Category</Label>
              <Select
                value={category}
                onValueChange={(v) => setCategory(v as TicketCategory)}
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {TICKET_CATEGORIES.map((c) => (
                    <SelectItem key={c} value={c}>
                      {c.charAt(0).toUpperCase() + c.slice(1)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="due">Due date</Label>
              <Input
                id="due"
                type="date"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
              />
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="description">Description</Label>
            <Textarea
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={8}
              placeholder="What's happening? Steps to reproduce, expected behaviour…"
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label>Attachments</Label>
            <div
              className={`rounded-md border-2 border-dashed p-4 text-sm flex flex-col items-center justify-center gap-2 cursor-pointer transition-colors ${
                dragActive ? 'border-primary bg-primary/5' : 'border-input'
              }`}
              onClick={() => fileInputRef.current?.click()}
              onDrop={onDrop}
              onDragOver={onDragOver}
              onDragLeave={onDragLeave}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  fileInputRef.current?.click();
                }
              }}
            >
              <Paperclip className="size-5 text-muted-foreground" />
              <p className="text-muted-foreground">
                Drag &amp; drop files here, or click to choose. Screenshots welcome.
              </p>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                className="hidden"
                onChange={(e) => {
                  addFiles(e.target.files);
                  e.target.value = '';
                }}
              />
            </div>
            {files.length > 0 && (
              <ul className="flex flex-col gap-1 text-sm">
                {files.map((p) => (
                  <li
                    key={p.key}
                    className="flex items-center justify-between rounded-md border bg-muted/30 px-3 py-2"
                  >
                    <span className="truncate flex-1 mr-2">{p.file.name}</span>
                    <span className="text-xs text-muted-foreground mr-2">
                      {formatBytes(p.file.size)}
                    </span>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 px-2 text-muted-foreground hover:text-destructive"
                      onClick={() => removeFile(p.key)}
                      disabled={submitting}
                      aria-label={`Remove ${p.file.name}`}
                    >
                      <X className="size-3" />
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2 pt-2 border-t">
            <Button
              variant="outline"
              onClick={() => router.push('/ticket-management/tickets')}
              disabled={submitting}
            >
              Cancel
            </Button>
            <div className="ms-auto flex gap-2">
              <Button
                variant="outline"
                disabled={submitting}
                onClick={() => submit(true)}
              >
                Save Draft
              </Button>
              <Button disabled={submitting} onClick={() => submit(false)}>
                {submitting ? 'Submitting…' : 'Submit'}
              </Button>
            </div>
          </div>
        </div>
      </Container>
    </>
  );
}
