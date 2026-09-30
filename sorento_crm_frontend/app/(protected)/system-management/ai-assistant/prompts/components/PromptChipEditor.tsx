'use client';

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Braces, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { FindBar, isFindChord } from '@/components/common/find-in-text/FindBar';
import { useFindController } from '@/components/common/find-in-text/useFindController';
import { splitTemplate } from '../../lib/promptSegments';
import type { RegistryVariableRow } from '../../services/aiPromptsService';

/** Variables that render several lines: drawn as a full-width block, not an inline pill. */
const BLOCK_VARIABLES = new Set(['statuses', 'domains_detail', 'entity_kinds_detail', 'specs']);

const CHIP_CLASS =
  'mx-0.5 inline-flex max-w-full flex-wrap items-center gap-1 rounded-md border border-primary/30 bg-primary/10 px-1.5 py-px align-baseline font-sans text-2xs leading-5 text-primary';
const BLOCK_CHIP_CLASS = 'my-0.5 flex w-full';
const RENDERED_CLASS =
  'basis-full whitespace-pre-wrap break-words rounded border border-primary/20 bg-background px-2 py-1 font-mono text-2xs text-foreground';

/**
 * The prompt editor for a key with registry variables (PLAN-prompt-dynamic-30sep R5a; owner,
 * 30 Sep 2026: "it needs to stay visualized during edit time, all the time; it should be a
 * variable wired into the prompt; if I want to overwrite I can remove the variable").
 *
 * The text is edited in place; every registry variable is a chip that names its source and
 * row count, expands to the text the model receives, links to the page that edits it, and
 * is removed with its x (the owner's own words then take its place). The value is always
 * the plain template: a chip serialises back to exactly the token it came from.
 *
 * The DOM is built imperatively and rebuilt only when `value` changes from outside (a
 * version switch, an Undo): React re-rendering a contenteditable on every keystroke is what
 * throws the caret around. Find reuses the textarea editor's controller (R5c): matches are
 * highlighted, the caret moves only on an explicit next/previous, and closing find leaves the
 * match selected for editing in place.
 */
export function PromptChipEditor({
  value,
  onChange,
  variables,
  registryNames,
  disabled = false,
  className,
}: {
  value: string;
  onChange: (next: string) => void;
  variables: RegistryVariableRow[];
  registryNames: string[];
  disabled?: boolean;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const emitted = useRef<string | null>(null);
  const savedRange = useRef<Range | null>(null);
  const [undoValue, setUndoValue] = useState<string | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerQuery, setPickerQuery] = useState('');

  const byName = useMemo(() => new Map(variables.map((v) => [v.name, v])), [variables]);
  const namesKey = registryNames.join(',');

  // ---- DOM <-> value ------------------------------------------------------------------

  const makeChip = useCallback(
    (name: string, raw: string): HTMLElement => {
      const meta = byName.get(name);
      const chip = document.createElement('span');
      chip.dataset.chip = name;
      chip.dataset.raw = raw;
      chip.setAttribute('contenteditable', 'false');
      chip.className = cn(CHIP_CLASS, BLOCK_VARIABLES.has(name) && BLOCK_CHIP_CLASS);

      const toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.dataset.action = 'toggle';
      toggle.dataset.testid = `chip-toggle-${name}`;
      toggle.setAttribute('data-testid', `chip-toggle-${name}`);
      toggle.setAttribute('aria-label', `Show what ${meta?.label ?? name} renders`);
      toggle.setAttribute('aria-expanded', 'false');
      toggle.className = 'rounded px-0.5 text-primary/70 hover:bg-primary/10';
      toggle.textContent = '▸';
      chip.appendChild(toggle);

      const label = document.createElement('span');
      label.className = 'font-semibold';
      label.textContent = meta?.label ?? name;
      chip.appendChild(label);

      if (meta) {
        const detail = document.createElement('span');
        detail.className = 'text-primary/70';
        detail.textContent = `${meta.count} rows, from ${meta.source}`;
        chip.appendChild(detail);
        const link = document.createElement('a');
        link.href = meta.href;
        link.target = '_blank';
        link.rel = 'noopener';
        link.setAttribute('aria-label', `Open ${meta.source}`);
        link.className = 'px-0.5 text-primary/70 hover:text-primary';
        link.textContent = '↗';
        chip.appendChild(link);
      }

      if (!disabled) {
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.dataset.action = 'remove';
        remove.setAttribute('data-testid', `chip-remove-${name}`);
        remove.setAttribute('aria-label', `Remove ${meta?.label ?? name}`);
        remove.className = 'rounded px-0.5 text-primary/70 hover:bg-destructive/10 hover:text-destructive';
        remove.textContent = '×';
        chip.appendChild(remove);
      }

      const rendered = document.createElement('span');
      rendered.setAttribute('data-testid', `chip-rendered-${name}`);
      rendered.className = RENDERED_CLASS;
      rendered.hidden = true;
      rendered.textContent = meta?.rendered ?? '';
      chip.appendChild(rendered);
      return chip;
    },
    [byName, disabled],
  );

  const build = useCallback(
    (template: string) => {
      const root = ref.current;
      if (!root) return;
      root.replaceChildren();
      for (const seg of splitTemplate(template, registryNames)) {
        root.appendChild(seg.kind === 'text' ? document.createTextNode(seg.text) : makeChip(seg.name, seg.raw));
      }
    },
    // namesKey stands in for registryNames' contents.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [makeChip, namesKey],
  );

  const serialise = useCallback((node: Node): string => {
    let out = '';
    node.childNodes.forEach((child) => {
      if (child.nodeType === Node.TEXT_NODE) {
        out += child.textContent ?? '';
      } else if (child instanceof HTMLElement) {
        if (child.dataset.chip) out += child.dataset.raw ?? `{{${child.dataset.chip}}}`;
        else if (child.tagName === 'BR') out += '\n';
        else {
          // A browser-inserted block (Enter in some engines): its content on a new line.
          const inner = serialise(child);
          out += (out && !out.endsWith('\n') ? '\n' : '') + inner;
        }
      }
    });
    return out;
  }, []);

  const emit = useCallback(() => {
    const root = ref.current;
    if (!root) return;
    const next = serialise(root);
    emitted.current = next;
    onChange(next);
  }, [onChange, serialise]);

  // Rebuild only for an outside change; a change this editor emitted is already on screen.
  useLayoutEffect(() => {
    if (value === emitted.current) return;
    build(value);
    emitted.current = value;
    setUndoValue(null);
  }, [value, build]);

  // Registry data arriving (or changing) redraws the chips' labels in place.
  useLayoutEffect(() => {
    if (emitted.current != null) build(emitted.current);
  }, [build]);

  // ---- caret, chip actions, insert ----------------------------------------------------

  const rememberCaret = () => {
    const sel = typeof window !== 'undefined' ? window.getSelection() : null;
    if (sel && sel.rangeCount > 0 && ref.current?.contains(sel.getRangeAt(0).startContainer)) {
      savedRange.current = sel.getRangeAt(0).cloneRange();
    }
  };

  const onRootClick = (e: React.MouseEvent) => {
    const target = e.target as HTMLElement;
    const button = target.closest<HTMLElement>('[data-action]');
    const chip = target.closest<HTMLElement>('[data-chip]');
    if (!button || !chip) {
      rememberCaret();
      return;
    }
    e.preventDefault();
    if (button.dataset.action === 'toggle') {
      const rendered = chip.querySelector<HTMLElement>('[data-testid^="chip-rendered-"]');
      if (rendered) rendered.hidden = !rendered.hidden;
      button.textContent = rendered && !rendered.hidden ? '▾' : '▸';
      button.setAttribute('aria-expanded', rendered && !rendered.hidden ? 'true' : 'false');
    } else if (button.dataset.action === 'remove' && !disabled) {
      setUndoValue(emitted.current ?? value);
      chip.remove();
      emit();
    }
  };

  const insertVariable = (name: string) => {
    const root = ref.current;
    if (!root || disabled) return;
    const chip = makeChip(name, `{{${name}}}`);
    const range = savedRange.current;
    if (range && root.contains(range.startContainer)) {
      range.deleteContents();
      range.insertNode(chip);
      range.setStartAfter(chip);
      range.collapse(true);
      savedRange.current = range;
    } else {
      root.appendChild(chip);
    }
    setPickerOpen(false);
    setPickerQuery('');
    emit();
  };

  const insertPlainText = (text: string) => {
    if (typeof document.execCommand === 'function' && document.execCommand('insertText', false, text)) return;
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return;
    const range = sel.getRangeAt(0);
    range.deleteContents();
    const node = document.createTextNode(text);
    range.insertNode(node);
    range.setStartAfter(node);
    range.collapse(true);
    sel.removeAllRanges();
    sel.addRange(range);
    emit();
  };

  // ---- find ----------------------------------------------------------------------------

  // The text find searches: the value with every chip masked, so a match never lands in or
  // across a variable, and every offset is an offset into `value` itself.
  const findText = useMemo(() => {
    let out = '';
    for (const seg of splitTemplate(emitted.current ?? value, registryNames)) {
      out += seg.kind === 'text' ? seg.text : '\u0000'.repeat(seg.raw.length);
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, namesKey]);
  const find = useFindController(findText);
  const { open, matches, activeIndex, jumpSeq, openFind, close } = find;
  const activeOffsets = useRef<{ start: number; end: number } | null>(null);

  /** A DOM Range for value offsets [start, end), or null when it would touch a chip. */
  const rangeFor = useCallback((start: number, end: number): Range | null => {
    const root = ref.current;
    if (!root) return null;
    let pos = 0;
    let startNode: Text | null = null;
    let startOff = 0;
    let endNode: Text | null = null;
    let endOff = 0;
    for (const child of Array.from(root.childNodes)) {
      const len =
        child.nodeType === Node.TEXT_NODE
          ? (child.textContent ?? '').length
          : child instanceof HTMLElement && child.dataset.chip
            ? (child.dataset.raw ?? '').length
            : (child.textContent ?? '').length;
      if (child.nodeType === Node.TEXT_NODE) {
        if (!startNode && start >= pos && start <= pos + len) {
          startNode = child as Text;
          startOff = start - pos;
        }
        if (startNode && end >= pos && end <= pos + len) {
          endNode = child as Text;
          endOff = end - pos;
          break;
        }
      }
      pos += len;
    }
    if (!startNode || !endNode) return null;
    const range = document.createRange();
    range.setStart(startNode, startOff);
    range.setEnd(endNode, endOff);
    return range;
  }, []);

  // Highlight every match; the active one differently. Recomputed on every text change,
  // which never touches the caret (CSS Custom Highlight API; a no-op where unsupported).
  useEffect(() => {
    const registry = (globalThis as { CSS?: { highlights?: Map<string, unknown> } }).CSS?.highlights;
    const HighlightCtor = (globalThis as { Highlight?: new (...r: Range[]) => unknown }).Highlight;
    if (!registry || !HighlightCtor) return;
    if (!open || matches.length === 0) {
      registry.delete('prompt-find');
      registry.delete('prompt-find-active');
      return;
    }
    const all = matches.map((m) => rangeFor(m.start, m.end)).filter((r): r is Range => r != null);
    registry.set('prompt-find', new HighlightCtor(...all));
    const active = activeIndex >= 0 ? rangeFor(matches[activeIndex].start, matches[activeIndex].end) : null;
    if (active) registry.set('prompt-find-active', new HighlightCtor(active));
    else registry.delete('prompt-find-active');
    return () => {
      registry.delete('prompt-find');
      registry.delete('prompt-find-active');
    };
  }, [open, matches, activeIndex, rangeFor]);

  // Jump to the active match on an explicit find navigation only (jumpSeq), never because
  // the text changed: that is the R5c caret bug, not repeated here.
  const latest = useRef({ matches, activeIndex, open });
  latest.current = { matches, activeIndex, open };
  useEffect(() => {
    const { matches: ms, activeIndex: idx, open: isOpen } = latest.current;
    const root = ref.current;
    if (!root || !isOpen || idx < 0 || !ms[idx]) return;
    const { start, end } = ms[idx];
    activeOffsets.current = { start, end };
    root.setAttribute('data-find-active', `${start}-${end}`);
    const range = rangeFor(start, end);
    if (range && typeof range.getBoundingClientRect === 'function') {
      const rect = range.getBoundingClientRect();
      const box = root.getBoundingClientRect();
      root.scrollTop += rect.top - box.top - root.clientHeight / 2;
    }
  }, [jumpSeq, rangeFor]);

  const dismissFind = () => {
    const root = ref.current;
    const offsets = activeOffsets.current;
    root?.removeAttribute('data-find-active');
    if (!root || !offsets) return;
    const range = rangeFor(offsets.start, offsets.end);
    root.focus();
    if (range) {
      const sel = window.getSelection();
      sel?.removeAllRanges();
      sel?.addRange(range);
      savedRange.current = range.cloneRange();
    }
  };

  // ---- render --------------------------------------------------------------------------

  const pickerOptions = variables.filter(
    (v) =>
      !pickerQuery ||
      v.label.toLowerCase().includes(pickerQuery.toLowerCase()) ||
      v.source.toLowerCase().includes(pickerQuery.toLowerCase()),
  );

  return (
    <div className={cn('space-y-2', className)}>
      {!disabled ? (
        <div className="relative flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setPickerOpen((o) => !o)}
            data-testid="insert-variable"
            aria-expanded={pickerOpen}
          >
            <Plus className="size-4" /> Insert variable
          </Button>
          {pickerOpen ? (
            <div
              className="absolute left-0 top-full z-30 mt-1 w-72 max-w-[calc(100vw-2rem)] rounded-md border bg-background p-2 shadow-md"
              data-testid="insert-variable-menu"
            >
              <Input
                value={pickerQuery}
                onChange={(e) => setPickerQuery(e.target.value)}
                placeholder="Search variables"
                className="mb-2 h-8 text-xs"
                autoFocus
              />
              <div className="max-h-64 overflow-auto">
                {pickerOptions.length === 0 ? (
                  <p className="px-2 py-1 text-xs text-muted-foreground">No variable matches.</p>
                ) : (
                  pickerOptions.map((v) => (
                    <button
                      key={v.name}
                      type="button"
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => insertVariable(v.name)}
                      data-testid={`insert-variable-${v.name}`}
                      className="flex w-full items-center justify-between gap-2 rounded px-2 py-1 text-left text-xs hover:bg-muted"
                    >
                      <span className="flex min-w-0 items-center gap-1.5">
                        <Braces className="size-3.5 shrink-0 text-primary" />
                        <span className="truncate font-medium">{v.label}</span>
                      </span>
                      <span className="shrink-0 text-muted-foreground">{v.count} rows</span>
                    </button>
                  ))
                )}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="relative">
        <FindBar controller={find} onDismiss={dismissFind} />
        <div
          ref={ref}
          role="textbox"
          aria-multiline="true"
          aria-label="Prompt"
          aria-readonly={disabled}
          contentEditable={!disabled}
          suppressContentEditableWarning
          spellCheck={false}
          data-testid="prompt-chip-editor"
          className="max-h-[70vh] min-h-[320px] overflow-auto whitespace-pre-wrap break-words rounded-md border bg-background p-3 font-mono text-xs leading-relaxed outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onInput={() => {
            // Typing after a removal makes the removal final: Undo would roll the typing back.
            setUndoValue(null);
            emit();
          }}
          onKeyUp={rememberCaret}
          onMouseUp={rememberCaret}
          onClick={onRootClick}
          onBlur={rememberCaret}
          onPaste={(e) => {
            e.preventDefault();
            insertPlainText(e.clipboardData.getData('text/plain'));
          }}
          onKeyDown={(e) => {
            if (isFindChord(e)) {
              e.preventDefault();
              openFind();
            } else if (e.key === 'Escape' && open) {
              e.preventDefault();
              close();
              dismissFind();
            } else if (e.key === 'Enter' && !e.shiftKey && !e.metaKey && !e.ctrlKey && !e.altKey) {
              // A newline, never a browser-inserted <div>, so the value stays plain text.
              e.preventDefault();
              insertPlainText('\n');
            }
          }}
        />
      </div>

      {undoValue != null ? (
        <div
          className="flex items-center justify-between gap-2 rounded-md border bg-muted/40 px-3 py-1.5 text-xs"
          role="status"
        >
          <span>Variable removed. Your text takes over here.</span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-xs"
            data-testid="chip-undo"
            onClick={() => {
              const previous = undoValue;
              setUndoValue(null);
              onChange(previous);
            }}
          >
            Undo
          </Button>
        </div>
      ) : null}

      <style>{`::highlight(prompt-find){background-color:color-mix(in oklab, var(--color-warning, #f59e0b) 40%, transparent)}::highlight(prompt-find-active){background-color:color-mix(in oklab, var(--color-primary, #2563eb) 40%, transparent)}`}</style>
    </div>
  );
}
