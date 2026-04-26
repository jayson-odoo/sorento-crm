'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { QuotationReactQuill } from '@/components/commercial/QuotationReactQuill';
import {
  listQuotationEmailTemplates,
  previewQuotationEmail,
  sendQuotationEmail,
  type QuotationEmailTemplateRow,
} from '@/app/(protected)/commercial-management/quotation-revisions/services/quotationPrintEmailService';

function splitEmails(raw: string): string[] {
  return raw
    .split(/[,;\s]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function QuotationEmailSendDialog(props: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  revisionId: string | null;
}) {
  const { open, onOpenChange, revisionId } = props;
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [templates, setTemplates] = useState<QuotationEmailTemplateRow[]>([]);
  const [templateId, setTemplateId] = useState<string>('');
  const [to, setTo] = useState('');
  const [cc, setCc] = useState('');
  const [bcc, setBcc] = useState('');
  const [subject, setSubject] = useState('');
  const [bodyHtml, setBodyHtml] = useState('');
  const [pdfName, setPdfName] = useState('');

  useEffect(() => {
    if (!open || !revisionId) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const rows = await listQuotationEmailTemplates();
        if (cancelled) return;
        setTemplates(rows);
        const def = rows.find((r) => r.is_default);
        const tid = def?.id ?? rows[0]?.id ?? '';
        setTemplateId(tid);
        const prev = await previewQuotationEmail(revisionId, tid || null);
        if (cancelled) return;
        setTo(prev.default_to || '');
        setSubject(prev.subject || '');
        setBodyHtml(prev.body_html || '');
        setPdfName(prev.pdf_attachment_filename || 'quotation.pdf');
      } catch (e) {
        if (!cancelled) toast.error(e instanceof Error ? e.message : 'Could not prepare email');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, revisionId]);

  const templateOptions = useMemo(
    () =>
      templates.map((t) => (
        <SelectItem key={t.id} value={t.id}>
          {t.name}
        </SelectItem>
      )),
    [templates],
  );

  const onApplyTemplate = useCallback(async () => {
    if (!revisionId) return;
    setLoading(true);
    try {
      const prev = await previewQuotationEmail(revisionId, templateId || null);
      setSubject(prev.subject || '');
      setBodyHtml(prev.body_html || '');
      setPdfName(prev.pdf_attachment_filename || 'quotation.pdf');
      if (!to.trim() && prev.default_to) setTo(prev.default_to);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to apply template');
    } finally {
      setLoading(false);
    }
  }, [revisionId, templateId, to]);

  const onSend = async () => {
    if (!revisionId) return;
    const toList = splitEmails(to);
    if (!toList.length) {
      toast.error('Add at least one recipient');
      return;
    }
    setSending(true);
    try {
      await sendQuotationEmail({
        revisionId,
        to: toList,
        cc: splitEmails(cc),
        bcc: splitEmails(bcc),
        subject: subject.trim(),
        body_html: bodyHtml,
      });
      toast.success('Email sent');
      onOpenChange(false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Send failed');
    } finally {
      setSending(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Send quotation by email</DialogTitle>
        </DialogHeader>

        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label>Template</Label>
            <div className="flex flex-wrap gap-2">
              <Select
                value={templateId || undefined}
                onValueChange={(v) => setTemplateId(v)}
                disabled={loading || !templates.length}
              >
                <SelectTrigger className="w-[280px]">
                  <SelectValue placeholder="Choose template" />
                </SelectTrigger>
                <SelectContent>{templateOptions}</SelectContent>
              </Select>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => void onApplyTemplate()}
                disabled={loading}
              >
                Apply template
              </Button>
            </div>
          </div>

          <div className="grid gap-2">
            <Label>To</Label>
            <Input
              value={to}
              onChange={(e) => setTo(e.target.value)}
              placeholder="email@example.com"
              disabled={loading}
            />
          </div>
          <div className="grid gap-2">
            <Label>CC</Label>
            <Input value={cc} onChange={(e) => setCc(e.target.value)} placeholder="Optional" disabled={loading} />
          </div>
          <div className="grid gap-2">
            <Label>BCC</Label>
            <Input value={bcc} onChange={(e) => setBcc(e.target.value)} placeholder="Optional" disabled={loading} />
          </div>
          <div className="grid gap-2">
            <Label>Subject</Label>
            <Input value={subject} onChange={(e) => setSubject(e.target.value)} disabled={loading} />
          </div>

          <div className="rounded-md border border-dashed bg-muted/30 px-3 py-2 text-sm text-muted-foreground">
            Attachment: <span className="font-medium text-foreground">{pdfName || 'Quotation PDF'}</span>
          </div>

          <Tabs defaultValue="compose">
            <TabsList>
              <TabsTrigger value="compose">Compose</TabsTrigger>
              <TabsTrigger value="preview">Preview</TabsTrigger>
            </TabsList>
            <TabsContent value="compose" className="mt-3">
              <QuotationReactQuill value={bodyHtml} onChange={setBodyHtml} minHeightPx={220} />
            </TabsContent>
            <TabsContent value="preview" className="mt-3">
              <div
                className="prose prose-sm min-h-[220px] max-w-none rounded-[14px] border border-[#d1d5dc] bg-white p-4 text-sm"
                dangerouslySetInnerHTML={{ __html: bodyHtml || '<p class="text-muted-foreground">(empty)</p>' }}
              />
            </TabsContent>
          </Tabs>
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={sending}>
            Cancel
          </Button>
          <Button type="button" onClick={() => void onSend()} disabled={loading || sending}>
            {sending ? 'Sending…' : 'Send'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
