'use client';

import {
  forwardRef,
  useCallback,
  useImperativeHandle,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';
import { ArrowUp, FileSpreadsheet, FileText, Loader2, Mic, Paperclip, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { extensionOf, formatSize } from '@/components/common/FileDropzone';
import {
  deleteAssistantFile,
  uploadAssistantFile,
  type AssistantFile,
} from '@/lib/aiAssistantChatApi';
import { useDictation } from '@/hooks/useDictation';
import { localStore } from '@/lib/storage';
import { cn } from '@/lib/utils';

const ACCEPT_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.webp', '.xlsx', '.xls', '.csv', '.pdf'];
const ACCEPT = ACCEPT_EXTENSIONS.join(',');
const MAX_BYTES = 10 * 1024 * 1024;
const MAX_FILES = 5;
const LINE_HEIGHT = 20;
const MAX_LINES = 8;
const LANG_KEY = 'ai-assistant-dictation-lang';

type Lang = 'en-US' | 'ms-MY';

interface Chip {
  key: string;
  name: string;
  size: number;
  status: 'uploading' | 'ready' | 'error';
  error?: string;
  file?: AssistantFile;
  sheet?: string;
}

export interface AssistantComposerHandle {
  addFiles: (files: File[]) => void;
}

export interface AssistantComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSend: (payload: {
    text: string;
    attachments: { id: string; sheet: string | null }[];
  }) => Promise<void> | void;
  isSending: boolean;
  canAttach: boolean;
}

function clientRefusal(file: File): string | null {
  const ext = extensionOf(file.name);
  if (ext === '.xlsm') return 'Macro workbooks are not read; save as .xlsx';
  if (!ACCEPT_EXTENSIONS.includes(ext)) return 'Unsupported file type';
  if (file.size > MAX_BYTES) return 'Over 10 MB';
  return null;
}

function ChipIcon({ chip }: { chip: Chip }) {
  const kind = chip.file?.kind;
  const ext = extensionOf(chip.name);
  if (kind === 'image' && chip.file?.thumb_url) {
    return <img src={chip.file.thumb_url} alt="" className="size-9 shrink-0 rounded-md object-cover" />;
  }
  const sheet = kind === 'sheet' || ['.xlsx', '.xls', '.csv', '.xlsm'].includes(ext);
  const Icon = sheet ? FileSpreadsheet : FileText;
  return (
    <span
      className={cn(
        'flex size-9 shrink-0 items-center justify-center rounded-md text-white',
        chip.status === 'error' ? 'bg-destructive' : sheet ? 'bg-emerald-700' : 'bg-red-600',
      )}
    >
      <Icon className="size-4" aria-hidden />
    </span>
  );
}

const AssistantComposer = forwardRef<AssistantComposerHandle, AssistantComposerProps>(
  function AssistantComposer({ value, onChange, onSend, isSending, canAttach }, ref) {
    const [chips, setChips] = useState<Chip[]>([]);
    const chipsRef = useRef<Chip[]>([]);
    chipsRef.current = chips;
    const textRef = useRef<HTMLTextAreaElement | null>(null);
    const inputRef = useRef<HTMLInputElement | null>(null);
    const valueRef = useRef(value);
    valueRef.current = value;
    const keySeq = useRef(0);
    const [lang, setLang] = useState<Lang>(() =>
      localStore.getItem(LANG_KEY) === 'ms-MY' ? 'ms-MY' : 'en-US',
    );

    const toggleLang = () => {
      const next: Lang = lang === 'en-US' ? 'ms-MY' : 'en-US';
      setLang(next);
      localStore.setItem(LANG_KEY, next);
    };

    const dictation = useDictation({
      lang,
      onFinal: (text) => {
        const cur = valueRef.current;
        onChange(cur && !/\s$/.test(cur) ? `${cur} ${text}` : `${cur}${text}`);
      },
    });

    // Grow 1 to 8 lines, then scroll.
    useLayoutEffect(() => {
      const el = textRef.current;
      if (!el) return;
      el.style.height = 'auto';
      const max = LINE_HEIGHT * MAX_LINES;
      el.style.height = `${Math.min(el.scrollHeight, max)}px`;
      el.style.overflowY = el.scrollHeight > max ? 'auto' : 'hidden';
    }, [value]);

    const patch = useCallback((key: string, next: Partial<Chip>) => {
      setChips((prev) => prev.map((c) => (c.key === key ? { ...c, ...next } : c)));
    }, []);

    const addFiles = useCallback(
      (files: File[]) => {
        if (!canAttach) return;
        let count = chipsRef.current.filter((c) => c.status !== 'error').length;
        const added: Chip[] = [];
        const toUpload: { key: string; file: File }[] = [];
        for (const file of files) {
          if (file.name.trim().startsWith('._')) continue;
          keySeq.current += 1;
          const key = `chip-${keySeq.current}`;
          const base = { key, name: file.name, size: file.size };
          if (count >= MAX_FILES) {
            added.push({ ...base, status: 'error', error: 'At most 5 files per message' });
            continue;
          }
          const refusal = clientRefusal(file);
          if (refusal) {
            added.push({ ...base, status: 'error', error: refusal });
            continue;
          }
          count += 1;
          added.push({ ...base, status: 'uploading' });
          toUpload.push({ key, file });
        }
        if (!added.length) return;
        setChips((prev) => [...prev, ...added]);
        for (const { key, file } of toUpload) {
          uploadAssistantFile(file).then(
            (uploaded) =>
              patch(key, {
                status: 'ready',
                file: uploaded,
                sheet: uploaded.sheets[0]?.name,
              }),
            (err: unknown) =>
              patch(key, {
                status: 'error',
                error: (err as Error)?.message || 'Upload failed',
              }),
          );
        }
      },
      [canAttach, patch],
    );

    useImperativeHandle(ref, () => ({ addFiles }), [addFiles]);

    const removeChip = (chip: Chip) => {
      setChips((prev) => prev.filter((c) => c.key !== chip.key));
      if (chip.file) deleteAssistantFile(chip.file.id).catch(() => undefined);
    };

    const ready = chips.filter((c) => c.status === 'ready' && c.file);
    const blocked = chips.some((c) => c.status !== 'ready');
    const hasText = value.trim().length > 0;
    const canSend = !isSending && !blocked && (hasText || ready.length > 0);

    const send = async () => {
      if (!canSend) return;
      if (dictation.listening) dictation.stop();
      const attachments = ready.map((c) => ({ id: c.file!.id, sheet: c.sheet ?? null }));
      try {
        await onSend({ text: value, attachments });
        setChips([]);
      } catch {
        // keep the chips so the user can retry
      }
    };

    const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key !== 'Enter' || e.shiftKey) return;
      if (e.nativeEvent.isComposing || e.keyCode === 229) return;
      if (typeof window !== 'undefined' && window.matchMedia?.('(pointer: coarse)').matches) return;
      e.preventDefault();
      void send();
    };

    const onPaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
      if (!canAttach) return;
      if (e.clipboardData.getData('text/plain')) return;
      const images = Array.from(e.clipboardData.files ?? []).filter((f) =>
        f.type.startsWith('image/'),
      );
      if (!images.length) return;
      e.preventDefault();
      addFiles(images);
    };

    return (
      <div className="border-t border-border/70 bg-background/85 p-3">
        <div className="rounded-2xl border border-input bg-background p-1.5 focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/25">
          {chips.length > 0 ? (
            <div className="flex flex-wrap gap-1.5 px-0.5 pb-1.5">
              {chips.map((chip) => {
                const sheets = chip.file?.sheets ?? [];
                const picked = sheets.find((s) => s.name === chip.sheet) ?? sheets[0];
                return (
                  <div
                    key={chip.key}
                    className={cn(
                      'relative flex max-w-full items-center gap-2 rounded-xl border p-1 pe-1.5 text-xs',
                      chip.status === 'error'
                        ? 'border-destructive bg-destructive/10'
                        : 'border-border bg-muted/40',
                    )}
                  >
                    <ChipIcon chip={chip} />
                    <div className="flex min-w-0 flex-col">
                      <span className="max-w-[150px] truncate font-medium" title={chip.name}>
                        {chip.name}
                      </span>
                      {chip.status === 'ready' && sheets.length > 1 ? (
                        <SearchableSelect
                          value={chip.sheet ?? sheets[0].name}
                          onChange={(v) => patch(chip.key, { sheet: v })}
                          options={sheets.map((s) => ({ value: s.name, label: s.name }))}
                          aria-label={`Sheet of ${chip.name}`}
                          size="sm"
                          className="w-max"
                        />
                      ) : null}
                      <span
                        className={cn(
                          'whitespace-nowrap text-2xs',
                          chip.status === 'error' ? 'text-destructive' : 'text-muted-foreground',
                        )}
                      >
                        {chip.status === 'error'
                          ? chip.error
                          : chip.status === 'uploading'
                            ? `${formatSize(chip.size)}, uploading`
                            : picked
                              ? `${picked.rows} rows`
                              : chip.file?.kind === 'pdf' && chip.file.pages != null
                                ? `${chip.file.pages} pages`
                                : formatSize(chip.size)}
                      </span>
                    </div>
                    <button
                      type="button"
                      aria-label={`Remove ${chip.name}`}
                      onClick={() => removeChip(chip)}
                      className="flex size-5 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-muted"
                    >
                      <X className="size-3.5" />
                    </button>
                    {chip.status === 'uploading' ? (
                      <div
                        role="progressbar"
                        aria-label={`Uploading ${chip.name}`}
                        className="absolute inset-x-1 bottom-0.5 h-[3px] overflow-hidden rounded-full bg-muted"
                      >
                        <div className="h-full w-2/3 animate-pulse rounded-full bg-primary" />
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          ) : null}
          <textarea
            ref={textRef}
            rows={1}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={onKeyDown}
            onPaste={onPaste}
            aria-label="Message the assistant"
            placeholder="Ask the assistant..."
            className="block w-full resize-none border-0 bg-transparent px-1.5 py-1 text-sm leading-5 outline-none placeholder:text-muted-foreground/80"
          />
          <div className="flex items-center gap-0.5 pt-0.5">
            {canAttach ? (
              <>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="size-8 rounded-lg"
                  aria-label="Attach files"
                  onClick={() => inputRef.current?.click()}
                >
                  <Paperclip className="size-4" />
                </Button>
                <input
                  ref={inputRef}
                  type="file"
                  multiple
                  accept={ACCEPT}
                  data-testid="assistant-file-input"
                  aria-label="Choose files"
                  className="hidden"
                  tabIndex={-1}
                  onChange={(e) => {
                    addFiles(Array.from(e.target.files ?? []));
                    e.target.value = '';
                  }}
                />
              </>
            ) : null}
            {dictation.supported ? (
              <>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className={cn(
                    'size-8 rounded-lg',
                    dictation.listening &&
                      'bg-destructive text-white hover:bg-destructive/90 hover:text-white motion-safe:animate-pulse',
                  )}
                  aria-label={dictation.listening ? 'Stop dictation' : 'Dictate'}
                  aria-pressed={dictation.listening}
                  onClick={dictation.toggle}
                >
                  <Mic className="size-4" />
                </Button>
                <button
                  type="button"
                  aria-label="Dictation language"
                  onClick={toggleLang}
                  className="rounded-md border border-border px-1.5 py-0.5 text-2xs text-muted-foreground hover:bg-muted"
                >
                  {lang === 'ms-MY' ? 'BM' : 'EN'}
                </button>
              </>
            ) : null}
            <span className="flex-1" />
            <Button
              type="button"
              size="icon"
              className="size-8 rounded-full"
              disabled={!canSend}
              onClick={() => void send()}
              aria-label={isSending ? 'Sending' : 'Send message'}
            >
              {isSending ? <Loader2 className="size-4 animate-spin" /> : <ArrowUp className="size-4" />}
            </Button>
          </div>
        </div>
      </div>
    );
  },
);

export default AssistantComposer;
