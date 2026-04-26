'use client';

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type Quill from 'quill';
import { Paperclip, Smile } from 'lucide-react';
import EmojiPicker, { Theme, type EmojiClickData } from 'emoji-picker-react';
import { toast } from 'sonner';
import { QuotationReactQuill, QUOTATION_QUILL_MODULES } from '@/components/commercial/QuotationReactQuill';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { cn } from '@/lib/utils';
import { useUploadAttachment, useAttachmentTypesList } from '@/app/(protected)/resource-management/attachments/hooks/useAttachments';
import { MentionList, type MentionItem } from './mention/MentionList';

export type ActivityUserOption = { id: string; name: string | null; email: string };

export interface ActivityMessageComposerProps {
  users: ActivityUserOption[];
  disabled?: boolean;
  placeholder?: string;
  onSend: (bodyHtml: string) => void | Promise<void>;
  className?: string;
  /** When set, uploads attach to this entity and inserts a download link into the message. */
  attachmentContext?: { entityType: string; entityId: string };
}

function isHtmlEffectivelyEmpty(html: string): boolean {
  if (typeof document === 'undefined') return !html?.trim();
  const d = document.createElement('div');
  d.innerHTML = html || '';
  const t = d.textContent?.replace(/\u00a0/g, ' ').trim() ?? '';
  return t.length === 0;
}

/** Active @mention: `@` must start the segment or follow a non-word character (avoids email `a@b`). */
function findAtMention(textBeforeCursor: string): { atIndex: number; query: string } | null {
  let at = -1;
  for (let i = textBeforeCursor.length - 1; i >= 0; i--) {
    const ch = textBeforeCursor[i];
    if (ch === '\n') break;
    if (ch === '@') {
      const prev = i > 0 ? textBeforeCursor[i - 1] : ' ';
      if (/\w/.test(prev)) continue;
      at = i;
      break;
    }
  }
  if (at === -1) return null;
  const query = textBeforeCursor.slice(at + 1);
  if (query.includes('\n')) return null;
  return { atIndex: at, query };
}

/** Same rich-text stack as Terms & conditions (`QuotationReactQuill`). */
export function ActivityMessageComposer({
  users,
  disabled,
  placeholder = 'Write a message…',
  onSend,
  className,
  attachmentContext,
}: ActivityMessageComposerProps) {
  const [html, setHtml] = useState('');
  const [mentionUi, setMentionUi] = useState<{
    start: number;
    cursor: number;
    items: MentionItem[];
    left: number;
    top: number;
  } | null>(null);
  const [emojiOpen, setEmojiOpen] = useState(false);
  const [posting, setPosting] = useState(false);
  const postingRef = useRef(false);

  const htmlRef = useRef('');
  htmlRef.current = html;

  const usersRef = useRef(users);
  usersRef.current = users;

  const mentionUiRef = useRef<typeof mentionUi>(null);
  mentionUiRef.current = mentionUi;

  const quillRef = useRef<Quill | null>(null);
  const mentionListRef = useRef<{ onKeyDown: (props: { event: KeyboardEvent }) => boolean } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const uploadMutation = useUploadAttachment();
  const { data: attachmentTypes = [] } = useAttachmentTypesList();
  const defaultAttachmentTypeId = attachmentTypes[0]?.id ?? '';

  const modules = useMemo(
    () => ({
      ...QUOTATION_QUILL_MODULES,
    }),
    [],
  );

  const syncMentionFromQuill = useCallback((q: Quill) => {
    const range = q.getSelection();
    if (!range) {
      setMentionUi(null);
      return;
    }
    const text = q.getText(0, range.index);
    const ctx = findAtMention(text);
    if (!ctx) {
      setMentionUi(null);
      return;
    }
    const qLower = ctx.query.toLowerCase().trim();
    const items: MentionItem[] = usersRef.current
      .map((u) => ({
        id: u.id,
        label: (u.name || '').trim() || u.email || u.id,
      }))
      .filter((it) => !qLower || it.label.toLowerCase().includes(qLower) || it.id.toLowerCase().includes(qLower))
      .slice(0, 20);

    let bounds: ReturnType<typeof q.getBounds> | null = null;
    try {
      bounds = q.getBounds(ctx.atIndex);
    } catch {
      setMentionUi(null);
      return;
    }
    if (!bounds) {
      setMentionUi(null);
      return;
    }
    const editorRect = q.root.getBoundingClientRect();
    setMentionUi({
      start: ctx.atIndex,
      cursor: range.index,
      items,
      left: editorRect.left + bounds.left,
      top: editorRect.top + bounds.bottom + 6,
    });
  }, []);

  const applyMention = useCallback(
    (item: MentionItem) => {
      const q = quillRef.current;
      const m = mentionUiRef.current;
      if (!q || !m) return;
      q.focus();
      const deleteLen = m.cursor - m.start;
      q.deleteText(m.start, deleteLen);
      const label = item.label.trim();
      const insert = `@${label} `;
      q.insertText(m.start, insert, { link: `mention:${item.id}` });
      setMentionUi(null);
      const nextCaret = m.start + insert.length;
      q.setSelection(nextCaret, 0);
    },
    [],
  );

  const submit = useCallback(async () => {
    const body = htmlRef.current;
    if (disabled || postingRef.current) return;
    if (isHtmlEffectivelyEmpty(body)) return;
    postingRef.current = true;
    setPosting(true);
    try {
      await onSend(body);
      setHtml('');
      htmlRef.current = '';
      setMentionUi(null);
    } finally {
      postingRef.current = false;
      setPosting(false);
    }
  }, [disabled, onSend]);

  useLayoutEffect(() => {
    let detached: (() => void) | undefined;
    let innerRaf = 0;
    const outerRaf = requestAnimationFrame(() => {
      innerRaf = requestAnimationFrame(() => {
        const q = quillRef.current;
        if (!q) return;

        const onDoc = () => syncMentionFromQuill(q);
        q.on('text-change', onDoc);
        q.on('selection-change', onDoc);

        const root = q.root;
        const onKeyDown = (e: KeyboardEvent) => {
          if (e.key === 'Escape' && mentionUiRef.current) {
            e.preventDefault();
            setMentionUi(null);
            return;
          }

          const dropdownOpen = !!document.querySelector('[data-mention-composer-dropdown]');
          if (dropdownOpen && mentionListRef.current?.onKeyDown({ event: e })) {
            e.preventDefault();
            e.stopPropagation();
            return;
          }

          if (e.key !== 'Enter' || e.shiftKey || e.ctrlKey || e.metaKey) return;
          if (dropdownOpen) return;

          if (isHtmlEffectivelyEmpty(htmlRef.current)) return;
          e.preventDefault();
          e.stopPropagation();
          void submit();
        };
        root.addEventListener('keydown', onKeyDown, true);

        syncMentionFromQuill(q);

        detached = () => {
          q.off('text-change', onDoc);
          q.off('selection-change', onDoc);
          root.removeEventListener('keydown', onKeyDown, true);
        };
      });
    });
    return () => {
      cancelAnimationFrame(outerRaf);
      cancelAnimationFrame(innerRaf);
      detached?.();
    };
  }, [submit, syncMentionFromQuill]);

  useEffect(() => {
    if (!mentionUi) return;
    const onMouseDown = (e: MouseEvent) => {
      const el = e.target;
      if (!(el instanceof Element)) return;
      if (el.closest('[data-mention-composer-dropdown]')) return;
      if (el.closest('.emoji-picker-react')) return;
      setMentionUi(null);
    };
    document.addEventListener('mousedown', onMouseDown);
    return () => document.removeEventListener('mousedown', onMouseDown);
  }, [mentionUi]);

  const insertAtCaret = useCallback((text: string) => {
    const q = quillRef.current;
    if (!q) return;
    const range = q.getSelection(true);
    const idx = range?.index ?? q.getLength() - 1;
    q.insertText(idx, text);
    q.setSelection(idx + text.length, 0);
  }, []);

  const onEmojiPick = useCallback(
    (data: EmojiClickData) => {
      insertAtCaret(data.emoji);
      setEmojiOpen(false);
    },
    [insertAtCaret],
  );

  const onAttachFiles = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      e.target.value = '';
      if (!file) return;
      if (!attachmentContext) {
        toast.error('Attachments are not available here.');
        return;
      }
      if (!defaultAttachmentTypeId) {
        toast.error('No attachment type is configured.');
        return;
      }
      try {
        const att = await uploadMutation.mutateAsync({
          file,
          attachmentTypeId: defaultAttachmentTypeId,
          entityType: attachmentContext.entityType,
          entityId: attachmentContext.entityId,
          accessLevels: ['dealer', 'end_user'],
        });
        const q = quillRef.current;
        if (!q) return;
        const href = `/api/v1/resource-management/attachments/${att.id}/download`;
        const range = q.getSelection(true);
        const idx = range?.index ?? Math.max(0, q.getLength() - 1);
        q.insertText(idx, '\n');
        q.insertText(idx + 1, file.name || 'attachment', { link: href });
        q.insertText(idx + 1 + (file.name || 'attachment').length, '\n');
        const end = idx + 2 + (file.name || 'attachment').length + 1;
        q.setSelection(end, 0);
      } catch {
        /* mutation toast */
      }
    },
    [attachmentContext, defaultAttachmentTypeId, uploadMutation],
  );

  const empty = isHtmlEffectivelyEmpty(html);

  return (
    <div className={cn('overflow-hidden rounded-[14px] border border-[#d1d5dc] bg-white shadow-xs', className)}>
      <QuotationReactQuill
        quillInstanceRef={quillRef}
        replaceModules
        modules={modules}
        value={html}
        onChange={setHtml}
        placeholder={placeholder}
        minHeightPx={120}
        readOnly={disabled}
        className="rounded-none border-0 shadow-none [&_.ql-toolbar]:rounded-t-[14px] [&_.ql-container]:border-t-0 [&_.ql-container]:rounded-none"
      />

      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        aria-hidden
        onChange={onAttachFiles}
      />

      <div className="flex items-center justify-between gap-3 border-t border-[#d1d5dc] bg-white px-3 py-2">
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="text-[#364153] hover:bg-[#f3f4f6]"
            aria-label="Attach file"
            disabled={disabled || !attachmentContext || !defaultAttachmentTypeId || uploadMutation.isPending}
            onClick={() => fileInputRef.current?.click()}
          >
            <Paperclip className="size-5" />
          </Button>

          <Popover open={emojiOpen} onOpenChange={setEmojiOpen}>
            <PopoverTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="text-[#364153] hover:bg-[#f3f4f6]"
                aria-label="Emoji"
                disabled={disabled}
              >
                <Smile className="size-5" />
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-auto border-none p-0 shadow-lg" align="start" side="top">
              <EmojiPicker theme={Theme.LIGHT} onEmojiClick={onEmojiPick} width={320} height={400} />
            </PopoverContent>
          </Popover>
        </div>

        <Button
          type="button"
          className="min-w-[88px] rounded-lg bg-[#e7000b] px-5 font-medium text-white hover:bg-[#c4000a]"
          disabled={disabled || posting || empty}
          onClick={() => void submit()}
        >
          Post
        </Button>
      </div>

      {mentionUi &&
        typeof document !== 'undefined' &&
        createPortal(
          <div
            className="pointer-events-auto"
            style={{
              position: 'fixed',
              left: mentionUi.left,
              top: mentionUi.top,
              zIndex: 10001,
            }}
          >
            <MentionList ref={mentionListRef} items={mentionUi.items} command={applyMention} />
          </div>,
          document.body,
        )}
    </div>
  );
}
