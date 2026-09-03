'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { toast } from '@/lib/toast';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { RichTextEditor } from '@/components/ui/rich-text-editor';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { FileDropzone } from '@/components/common/FileDropzone';
import { uploadAttachment } from '@/app/(protected)/resource-management/attachments/services/attachmentService';
import { createTicket } from '../services/ticketService';
import {
  TICKET_CATEGORIES,
  TICKET_PRIORITIES,
  type TicketCategory,
  type TicketPriority,
} from '../types/ticket.types';

function htmlToText(html: string): string {
  if (typeof window === 'undefined') return html.replace(/<[^>]+>/g, '').trim();
  const doc = new DOMParser().parseFromString(html || '', 'text/html');
  return (doc.body.textContent || '').trim();
}

export default function NewTicketPage() {
  const router = useRouter();
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState<TicketPriority>('medium');
  const [category, setCategory] = useState<TicketCategory>('question');
  const [dueDate, setDueDate] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [submitting, setSubmitting] = useState(false);

  async function uploadAllPending(): Promise<string[]> {
    if (files.length === 0) return [];
    const ids: string[] = [];
    for (const file of files) {
      // entity_type / entity_id intentionally omitted: ticket doesn't exist
      // yet. Backend create_ticket links each attachment_id below into
      // EntityAttachmentLink with the new ticket id.
      const att = await uploadAttachment(file, { entityType: 'ticket' });
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
      const descriptionHtml = description || null;
      const descriptionText = description ? htmlToText(description) || null : null;
      const t = await createTicket({
        title: title.trim(),
        description_text: descriptionText,
        description_html: descriptionHtml,
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
        <PageHeader
          title="Create ticket"
          crumbs={[
            { title: 'Tickets', path: '/ticket-management/tickets' },
            { title: 'Create ticket' },
          ]}
        />
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
              <SearchableSelect
                value={priority}
                onChange={(v) => setPriority(v as TicketPriority)}
                options={TICKET_PRIORITIES.map((p) => ({
                  value: p,
                  label: p.charAt(0).toUpperCase() + p.slice(1),
                }))}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label>Category</Label>
              <SearchableSelect
                value={category}
                onChange={(v) => setCategory(v as TicketCategory)}
                options={TICKET_CATEGORIES.map((c) => ({
                  value: c,
                  label: c.charAt(0).toUpperCase() + c.slice(1),
                }))}
              />
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
            <RichTextEditor
              value={description}
              onChange={setDescription}
              placeholder="What's happening? Steps to reproduce, expected behaviour…"
              minHeight={200}
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label>Attachments</Label>
            <FileDropzone
              multiple
              disabled={submitting}
              files={files}
              onFilesChange={setFiles}
              title="Drag and drop files here, or click to choose"
              hint="Screenshots welcome"
              aria-label="Ticket attachments"
            />
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
                {submitting ? 'Submitting…' : 'Submit ticket'}
              </Button>
            </div>
          </div>
        </div>
      </Container>
    </>
  );
}
