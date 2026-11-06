'use client';

import {
  AlignCenter,
  AlignLeft,
  AlignRight,
  Baseline,
  Bold,
  Code2,
  Heading1,
  Heading2,
  Heading3,
  Highlighter,
  Italic,
  Link as LinkIcon,
  Link2Off,
  List,
  ListOrdered,
  Quote,
  Redo,
  Strikethrough,
  Underline as UnderlineIcon,
  Undo,
} from 'lucide-react';
import {
  EditorContent,
  ReactRenderer,
  useEditor,
  type Editor,
} from '@tiptap/react';
import Link from '@tiptap/extension-link';
import Mention from '@tiptap/extension-mention';
import Placeholder from '@tiptap/extension-placeholder';
import TextAlign from '@tiptap/extension-text-align';
import { BackgroundColor, Color, TextStyle } from '@tiptap/extension-text-style';
import StarterKit from '@tiptap/starter-kit';
import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from 'react';
import { ColorPicker } from '@/components/common/ColorPicker';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Separator } from '@/components/ui/separator';
import { Toggle } from '@/components/ui/toggle';
import { cn } from '@/lib/utils';
import {
  MergeFieldNode,
  unwrapMergeFieldTokens,
  wrapMergeFieldTokens,
} from '@/components/ui/rich-text-merge-fields';

/** Item the mention popup expects. Loosely shaped so callers can map their
 * own user list (e.g. `getUsersSelect()` returning `{ id, name, email }`). */
export interface MentionItem {
  id: string;
  name?: string | null;
  email?: string | null;
  avatar_url?: string | null;
}

export type RichTextEditorProps = {
  value: string;
  onChange: (html: string) => void;
  placeholder?: string;
  minHeight?: number;
  className?: string;
  editable?: boolean;
  /**
   * When set, typing `@` opens a popup populated by this fetcher.
   * Picking inserts a styled mention (blue, data-id={user.id}) into the
   * document; the user's id is recoverable from the HTML via
   * ``extractMentionedUserIds(html)``.
   */
  mentionUsersFetcher?: () => Promise<MentionItem[]>;
  /**
   * Receives the underlying TipTap editor once it's ready. Useful when the
   * caller needs to programmatically insert content (e.g. Jinja2 placeholders)
   * at the current cursor position.
   */
  onEditorReady?: (editor: Editor) => void;
  /** Put on the editable element, so a visible label can name it. */
  id?: string;
  'aria-labelledby'?: string;
  /**
   * `inline`: bold, italic, underline, strike and text colour only (the tag designer's Content
   * box, whose block layout is the layer's own). Default: the full toolbar.
   */
  toolbar?: 'full' | 'inline';
  /**
   * `{{path}}` tokens become one atomic node each: a mark covers a token whole and a selection
   * never splits it. Value in and out still carries them as plain `{{path}}` text.
   */
  mergeFields?: boolean;
};

/** Editors whose caret somebody has placed (a focus or a selection change). */
const everFocused = new WeakSet<Editor>();

/** Insert text holding `{{tokens}}` at the caret of a `mergeFields` editor; each complete token
 * becomes its atom. */
export function insertMergeFieldText(editor: Editor, text: string) {
  if (!text) return;
  // An editor nobody has clicked into yet has its caret at the very start; the field goes after
  // the text there, not in front of it.
  const at = everFocused.has(editor) ? undefined : 'end';
  editor.chain().focus(at).insertContent({ type: 'text', text }).run();
}

/** One serialisation for comparing a stored value with the editor's (entities, quotes). */
function canonicalHtml(html: string): string {
  if (!html || typeof DOMParser === 'undefined') return html;
  return new DOMParser().parseFromString(html, 'text/html').body.innerHTML;
}

const RGB = /rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)/gi;

/**
 * The HTML the editor emits, with each inline `style` written the same way in every DOM:
 * `prop: value` joined by `; `, no trailing `;`, colours as lower-case hex. The browser (and
 * jsdom) re-serialise a style attribute as `color: rgb(107, 114, 128);`, which would make the
 * stored value depend on where it was typed.
 */
export function normaliseEditorHtml(html: string): string {
  // Text is never touched: with no style attribute there is nothing to normalise, and with one the
  // work is on the parsed elements' attributes, not on the string.
  if (!html.includes('style=') || typeof DOMParser === 'undefined') return html;
  const doc = new DOMParser().parseFromString(html, 'text/html');
  doc.body.querySelectorAll('[style]').forEach((el) => {
    const declarations = (el.getAttribute('style') ?? '')
      .split(';')
      .map((part) => part.trim())
      .filter(Boolean)
      .map((part) =>
        part.replace(RGB, (_m, r, g, b) =>
          `#${[r, g, b]
            .map((n) => Math.min(255, Number(n)).toString(16).padStart(2, '0'))
            .join('')}`,
        ),
      );
    if (declarations.length) el.setAttribute('style', declarations.join('; '));
    else el.removeAttribute('style');
  });
  return doc.body.innerHTML;
}

/** Declarations a paste may not carry: colour, highlight and alignment come only from the toolbar. */
const PASTE_DROPPED = /^(color|background-color|background|text-align)$/i;

/** Pasted HTML loses those declarations; the rest (font-weight, font-style, text-decoration) stay
 * so a word-processor paste keeps its real bold / italic / underline. */
export function stripPastedStyles(html: string): string {
  if (typeof DOMParser === 'undefined') return html;
  const doc = new DOMParser().parseFromString(html, 'text/html');
  doc.body.querySelectorAll<HTMLElement>('[style]').forEach((el) => {
    const kept = (el.getAttribute('style') ?? '')
      .split(';')
      .map((part) => part.trim())
      .filter((part) => part && !PASTE_DROPPED.test(part.split(':')[0].trim()));
    if (kept.length) el.setAttribute('style', kept.join('; '));
    else el.removeAttribute('style');
  });
  return doc.body.innerHTML;
}

const ToolbarButton = ({
  active,
  onClick,
  disabled,
  title,
  children,
}: {
  active?: boolean;
  onClick: () => void;
  disabled?: boolean;
  title: string;
  children: React.ReactNode;
}) => (
  <Toggle
    size="sm"
    pressed={!!active}
    onPressedChange={onClick}
    disabled={disabled}
    title={title}
    aria-label={title}
  >
    {children}
  </Toggle>
);

function LinkPopoverButton({ editor }: { editor: Editor }) {
  const [open, setOpen] = useState(false);
  const [href, setHref] = useState('');
  const isActive = editor.isActive('link');

  function openPopover() {
    const current = (editor.getAttributes('link').href as string | undefined) ?? '';
    setHref(current);
    setOpen(true);
  }

  function apply() {
    const value = href.trim();
    if (!value) {
      editor.chain().focus().extendMarkRange('link').unsetLink().run();
    } else {
      editor
        .chain()
        .focus()
        .extendMarkRange('link')
        .setLink({ href: value })
        .run();
    }
    setOpen(false);
  }

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        if (next) openPopover();
        else setOpen(false);
      }}
    >
      <PopoverTrigger asChild>
        <Toggle
          size="sm"
          pressed={isActive}
          title={isActive ? 'Edit link' : 'Add link'}
          aria-label={isActive ? 'Edit link' : 'Add link'}
        >
          <LinkIcon className="size-4" />
        </Toggle>
      </PopoverTrigger>
      <PopoverContent className="w-[320px] p-3" align="start">
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">
            Paste a URL or a Jinja2 placeholder like{' '}
            <code className="rounded bg-muted px-1">{`{{ promotion.link }}`}</code>.
          </p>
          <Input
            autoFocus
            value={href}
            onChange={(e) => setHref(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                apply();
              }
            }}
            placeholder="https://example.com or {{ promotion.link }}"
          />
          <div className="flex justify-end gap-2">
            {isActive && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  editor.chain().focus().extendMarkRange('link').unsetLink().run();
                  setOpen(false);
                }}
              >
                Remove
              </Button>
            )}
            <Button type="button" size="sm" onClick={apply}>
              Apply
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}


function ColorPopoverButton({
  editor,
  kind,
  label: labelOverride,
}: {
  editor: Editor;
  kind: 'color' | 'highlight';
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  const label = labelOverride ?? (kind === 'color' ? 'Text colour' : 'Highlight');
  const attribute = kind === 'color' ? 'color' : 'backgroundColor';
  const current = (editor.getAttributes('textStyle')[attribute] as string | undefined) ?? '';
  const Icon = kind === 'color' ? Baseline : Highlighter;

  function apply(hex: string) {
    const chain = editor.chain().focus();
    if (kind === 'color') chain.setColor(hex).run();
    else chain.setBackgroundColor(hex).run();
  }

  function remove() {
    const chain = editor.chain().focus();
    if (kind === 'color') chain.unsetColor().run();
    else chain.unsetBackgroundColor().run();
    setOpen(false);
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Toggle size="sm" pressed={!!current} title={label} aria-label={label}>
          <Icon className="size-4" />
        </Toggle>
      </PopoverTrigger>
      <PopoverContent className="w-auto space-y-2 p-3" align="start">
        <ColorPicker value={current || '#000000'} onChange={apply} />
        <Button type="button" variant="outline" size="sm" onClick={remove}>
          Remove colour
        </Button>
      </PopoverContent>
    </Popover>
  );
}

/** The tag designer's Content box: its buttons act on the selection, beside the layer's own
 * whole-text Bold / Italic toggles, so they are named for the selection. */
function InlineToolbar({ editor }: { editor: Editor }) {
  return (
    <div className="flex flex-wrap items-center gap-1 border-b bg-muted/30 px-2 py-1">
      <ToolbarButton
        title="Bold selection"
        active={editor.isActive('bold')}
        onClick={() => editor.chain().focus().toggleBold().run()}
      >
        <Bold className="size-4" />
      </ToolbarButton>
      <ToolbarButton
        title="Italic selection"
        active={editor.isActive('italic')}
        onClick={() => editor.chain().focus().toggleItalic().run()}
      >
        <Italic className="size-4" />
      </ToolbarButton>
      <ToolbarButton
        title="Underline selection"
        active={editor.isActive('underline')}
        onClick={() => editor.chain().focus().toggleUnderline().run()}
      >
        <UnderlineIcon className="size-4" />
      </ToolbarButton>
      <ToolbarButton
        title="Strikethrough selection"
        active={editor.isActive('strike')}
        onClick={() => editor.chain().focus().toggleStrike().run()}
      >
        <Strikethrough className="size-4" />
      </ToolbarButton>
      <ColorPopoverButton editor={editor} kind="color" label="Selection colour" />
    </div>
  );
}

function Toolbar({ editor }: { editor: Editor }) {
  return (
    <div className="flex flex-wrap items-center gap-1 border-b bg-muted/30 px-2 py-1">
      <ToolbarButton
        title="Bold"
        active={editor.isActive('bold')}
        onClick={() => editor.chain().focus().toggleBold().run()}
      >
        <Bold className="size-4" />
      </ToolbarButton>
      <ToolbarButton
        title="Italic"
        active={editor.isActive('italic')}
        onClick={() => editor.chain().focus().toggleItalic().run()}
      >
        <Italic className="size-4" />
      </ToolbarButton>
      <ToolbarButton
        title="Strikethrough"
        active={editor.isActive('strike')}
        onClick={() => editor.chain().focus().toggleStrike().run()}
      >
        <Strikethrough className="size-4" />
      </ToolbarButton>
      <ToolbarButton
        title="Underline"
        active={editor.isActive('underline')}
        onClick={() => editor.chain().focus().toggleUnderline().run()}
      >
        <UnderlineIcon className="size-4" />
      </ToolbarButton>
      <ColorPopoverButton editor={editor} kind="color" />
      <ColorPopoverButton editor={editor} kind="highlight" />
      <ToolbarButton
        title="Inline code"
        active={editor.isActive('code')}
        onClick={() => editor.chain().focus().toggleCode().run()}
      >
        <Code2 className="size-4" />
      </ToolbarButton>

      <Separator orientation="vertical" className="mx-1 h-5" />

      <ToolbarButton
        title="Heading 1"
        active={editor.isActive('heading', { level: 1 })}
        onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
      >
        <Heading1 className="size-4" />
      </ToolbarButton>
      <ToolbarButton
        title="Heading 2"
        active={editor.isActive('heading', { level: 2 })}
        onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
      >
        <Heading2 className="size-4" />
      </ToolbarButton>
      <ToolbarButton
        title="Heading 3"
        active={editor.isActive('heading', { level: 3 })}
        onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
      >
        <Heading3 className="size-4" />
      </ToolbarButton>

      <Separator orientation="vertical" className="mx-1 h-5" />

      <ToolbarButton
        title="Align left"
        active={editor.isActive({ textAlign: 'left' })}
        onClick={() => editor.chain().focus().setTextAlign('left').run()}
      >
        <AlignLeft className="size-4" />
      </ToolbarButton>
      <ToolbarButton
        title="Align centre"
        active={editor.isActive({ textAlign: 'center' })}
        onClick={() => editor.chain().focus().setTextAlign('center').run()}
      >
        <AlignCenter className="size-4" />
      </ToolbarButton>
      <ToolbarButton
        title="Align right"
        active={editor.isActive({ textAlign: 'right' })}
        onClick={() => editor.chain().focus().setTextAlign('right').run()}
      >
        <AlignRight className="size-4" />
      </ToolbarButton>

      <Separator orientation="vertical" className="mx-1 h-5" />

      <ToolbarButton
        title="Bullet list"
        active={editor.isActive('bulletList')}
        onClick={() => editor.chain().focus().toggleBulletList().run()}
      >
        <List className="size-4" />
      </ToolbarButton>
      <ToolbarButton
        title="Ordered list"
        active={editor.isActive('orderedList')}
        onClick={() => editor.chain().focus().toggleOrderedList().run()}
      >
        <ListOrdered className="size-4" />
      </ToolbarButton>
      <ToolbarButton
        title="Blockquote"
        active={editor.isActive('blockquote')}
        onClick={() => editor.chain().focus().toggleBlockquote().run()}
      >
        <Quote className="size-4" />
      </ToolbarButton>

      <Separator orientation="vertical" className="mx-1 h-5" />

      <LinkPopoverButton editor={editor} />
      <ToolbarButton
        title="Remove link"
        disabled={!editor.isActive('link')}
        onClick={() => {
          editor.chain().focus().extendMarkRange('link').unsetLink().run();
        }}
      >
        <Link2Off className="size-4" />
      </ToolbarButton>

      <Separator orientation="vertical" className="mx-1 h-5" />

      <ToolbarButton
        title="Undo"
        disabled={!editor.can().undo()}
        onClick={() => editor.chain().focus().undo().run()}
      >
        <Undo className="size-4" />
      </ToolbarButton>
      <ToolbarButton
        title="Redo"
        disabled={!editor.can().redo()}
        onClick={() => editor.chain().focus().redo().run()}
      >
        <Redo className="size-4" />
      </ToolbarButton>
    </div>
  );
}

// --- Mention popup ----------------------------------------------------

interface MentionListProps {
  items: MentionItem[];
  command: (item: { id: string; label: string }) => void;
}

interface MentionListHandle {
  onKeyDown: (props: { event: KeyboardEvent }) => boolean;
}

const MentionList = forwardRef<MentionListHandle, MentionListProps>(function MentionList(
  { items, command },
  ref,
) {
  const [selected, setSelected] = useState(0);

  useEffect(() => {
    setSelected(0);
  }, [items]);

  function pick(i: number) {
    const item = items[i];
    if (!item) return;
    command({
      id: item.id,
      label: item.name || item.email || item.id,
    });
  }

  useImperativeHandle(ref, () => ({
    onKeyDown: ({ event }) => {
      if (event.key === 'ArrowUp') {
        setSelected((s) => (items.length === 0 ? 0 : (s + items.length - 1) % items.length));
        return true;
      }
      if (event.key === 'ArrowDown') {
        setSelected((s) => (items.length === 0 ? 0 : (s + 1) % items.length));
        return true;
      }
      if (event.key === 'Enter') {
        pick(selected);
        return true;
      }
      return false;
    },
  }));

  if (items.length === 0) {
    return (
      <div className="rounded-md border bg-popover shadow-md p-2 text-sm text-muted-foreground min-w-[200px]">
        No matching users.
      </div>
    );
  }

  return (
    <div
      role="listbox"
      className="rounded-md border bg-popover shadow-md p-1 min-w-[220px] max-w-[320px] max-h-[260px] overflow-y-auto"
    >
      {items.map((item, i) => (
        <button
          type="button"
          role="option"
          aria-selected={i === selected}
          key={item.id}
          className={cn(
            'w-full text-left px-2 py-1.5 rounded text-sm flex flex-col gap-0.5',
            i === selected ? 'bg-accent' : 'hover:bg-accent/60',
          )}
          onMouseEnter={() => setSelected(i)}
          onMouseDown={(e) => {
            // mousedown so the click registers before the editor blurs.
            e.preventDefault();
            pick(i);
          }}
        >
          <span className="font-medium">{item.name || item.email || item.id}</span>
          {item.name && item.email ? (
            <span className="text-xs text-muted-foreground">{item.email}</span>
          ) : null}
        </button>
      ))}
    </div>
  );
});

function positionPopup(popup: HTMLElement, rect: DOMRect) {
  popup.style.left = `${rect.left}px`;
  popup.style.top = `${rect.bottom + 4}px`;
}

/** Extract the unique set of user ids referenced by mention nodes in
 * an editor's HTML output. Safe to call on the server (returns []). */
export function extractMentionedUserIds(html: string): string[] {
  if (typeof window === 'undefined') return [];
  if (!html) return [];
  const doc = new DOMParser().parseFromString(html, 'text/html');
  const ids = new Set<string>();
  doc
    .querySelectorAll('[data-type="mention"], span.mention')
    .forEach((el) => {
      const id = el.getAttribute('data-id');
      if (id) ids.add(id);
    });
  return Array.from(ids);
}

// --- Editor ----------------------------------------------------------

export function RichTextEditor({
  value,
  onChange,
  placeholder,
  minHeight = 240,
  className,
  editable = true,
  mentionUsersFetcher,
  onEditorReady,
  id,
  'aria-labelledby': labelledBy,
  toolbar = 'full',
  mergeFields = false,
}: RichTextEditorProps) {
  const inline = toolbar === 'inline';
  // A `mergeFields` editor holds its tokens as atoms; the value in and out keeps them as text.
  const toEditor = (html: string) => (mergeFields ? wrapMergeFieldTokens(html) : html);
  const fromEditor = (html: string) => (mergeFields ? unwrapMergeFieldTokens(html) : html);
  // Stash the fetcher in a ref so the Mention extension's closure can read
  // the latest version without re-creating the editor when the prop changes.
  const fetcherRef = useRef(mentionUsersFetcher);
  fetcherRef.current = mentionUsersFetcher;
  const usersCache = useRef<MentionItem[] | null>(null);

  const extensions = useMemo(() => {
    const list: ReturnType<typeof StarterKit.configure>[] | unknown[] = [
      StarterKit.configure({
        heading: inline ? false : { levels: [1, 2, 3] },
        // The inline toolbar's editor holds inline formatting only: with these off, no keyboard
        // shortcut, input rule or paste can make a block its stored format cannot draw.
        ...(inline
          ? {
              bulletList: false,
              orderedList: false,
              listItem: false,
              listKeymap: false,
              blockquote: false,
              codeBlock: false,
              horizontalRule: false,
              code: false,
              link: false,
            }
          : {}),
        // A merge-field value is stored as plain lines when unformatted; a hard break inside a
        // paragraph has no plain form, so Shift+Enter is a new paragraph's job only.
        ...(mergeFields ? { hardBreak: false } : {}),
      }),
      Link.configure({
        openOnClick: false,
        autolink: true,
        // Allow Jinja2 placeholders (and any other non-URL string) as href so
        // template authors can do `<a href="{{ promotion.link }}">`. The
        // default `validate` rejects anything that doesn't parse as a URL.
        validate: () => true,
        HTMLAttributes: {
          rel: 'noopener noreferrer nofollow',
          target: '_blank',
          class: 'text-primary underline underline-offset-2',
        },
      }),
      Placeholder.configure({ placeholder: placeholder || 'Type here...' }),
      // Colour, highlight and alignment. They emit inline `style` only when a button is used,
      // so content saved before they existed round-trips unchanged.
      // Only a span that carries a colour or highlight is a text style; a bare styled span
      // (what a word processor wraps text in) is just its text, and its bold / italic /
      // underline come from their own marks.
      TextStyle.extend({
        parseHTML() {
          return [
            {
              tag: 'span',
              getAttrs: (element) => {
                const el = element as HTMLElement;
                return el.style.color || el.style.backgroundColor ? {} : false;
              },
            },
          ];
        },
      }),
      Color,
      BackgroundColor,
      TextAlign.configure({ types: ['heading', 'paragraph'] }),
    ];
    if (mergeFields) list.push(MergeFieldNode);
    if (inline) {
      // No link, highlight or alignment either: the inline toolbar has no button for them.
      const dropped = new Set(['link', 'backgroundColor', 'textAlign']);
      return (list as Array<{ name?: string }>).filter((ext) => !dropped.has(ext.name ?? ''));
    }

    if (mentionUsersFetcher) {
      list.push(
        Mention.configure({
          HTMLAttributes: {
            class:
              'mention rounded px-1 py-0.5 bg-blue-50 text-blue-600 font-medium dark:bg-blue-950/40 dark:text-blue-400',
          },
          renderText({ node }) {
            return `@${node.attrs.label ?? node.attrs.id}`;
          },
          suggestion: {
            char: '@',
            allowSpaces: false,
            items: async ({ query }) => {
              if (!fetcherRef.current) return [];
              if (!usersCache.current) {
                try {
                  usersCache.current = (await fetcherRef.current()) as MentionItem[];
                } catch {
                  usersCache.current = [];
                }
              }
              const q = (query || '').trim().toLowerCase();
              const all = usersCache.current ?? [];
              const filtered = q
                ? all.filter((u) => {
                    const hay = `${u.name ?? ''} ${u.email ?? ''}`.toLowerCase();
                    return hay.includes(q);
                  })
                : all;
              return filtered.slice(0, 8);
            },
            render: () => {
              let component: ReactRenderer<MentionListHandle, MentionListProps> | null = null;
              let popup: HTMLDivElement | null = null;
              return {
                onStart: (props) => {
                  component = new ReactRenderer(MentionList, {
                    props: { items: props.items, command: props.command },
                    editor: props.editor,
                  });
                  popup = document.createElement('div');
                  popup.style.position = 'fixed';
                  popup.style.zIndex = '50';
                  popup.appendChild(component.element);
                  document.body.appendChild(popup);
                  const rect = props.clientRect?.();
                  if (rect) positionPopup(popup, rect);
                },
                onUpdate: (props) => {
                  component?.updateProps({ items: props.items, command: props.command });
                  const rect = props.clientRect?.();
                  if (rect && popup) positionPopup(popup, rect);
                },
                onKeyDown: (props) => {
                  if (props.event.key === 'Escape') {
                    popup?.remove();
                    return true;
                  }
                  return component?.ref?.onKeyDown({ event: props.event }) ?? false;
                },
                onExit: () => {
                  popup?.remove();
                  popup = null;
                  component?.destroy();
                  component = null;
                },
              };
            },
          },
        }),
      );
    }
    return list;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [Boolean(mentionUsersFetcher), placeholder, mergeFields, inline]);

  const editor = useEditor({
    immediatelyRender: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    extensions: extensions as any[],
    content: toEditor(value || ''),
    editable,
    editorProps: {
      transformPastedHTML: stripPastedStyles,
      attributes: {
        ...(id ? { id } : {}),
        ...(labelledBy ? { 'aria-labelledby': labelledBy } : {}),
        class: cn(
          'prose prose-sm dark:prose-invert max-w-none px-3 py-2 focus:outline-none',
          '[&_p]:my-2 [&_ul]:my-2 [&_ol]:my-2 [&_h1]:mt-3 [&_h2]:mt-3 [&_h3]:mt-3',
          // Force list markers - Tailwind preflight removes them on ul/ol
          '[&_ul]:list-disc [&_ul]:pl-6 [&_ol]:list-decimal [&_ol]:pl-6',
          '[&_li]:my-0.5 [&_li]:pl-1 [&_li>p]:my-0',
          '[&_ul_ul]:list-[circle] [&_ul_ul_ul]:list-[square]',
          '[&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5',
          '[&_.is-editor-empty:first-child::before]:pointer-events-none',
          '[&_.is-editor-empty:first-child::before]:float-left',
          '[&_.is-editor-empty:first-child::before]:h-0',
          '[&_.is-editor-empty:first-child::before]:text-muted-foreground',
          '[&_.is-editor-empty:first-child::before]:content-[attr(data-placeholder)]',
        ),
        style: `min-height: ${minHeight}px;`,
      },
    },
    onFocus: ({ editor: e }) => {
      everFocused.add(e);
    },
    onSelectionUpdate: ({ editor: e }) => {
      everFocused.add(e);
    },
    onUpdate: ({ editor: e }) => {
      const html = fromEditor(normaliseEditorHtml(e.getHTML()));
      onChange(html === '<p></p>' ? '' : html);
    },
  });

  // Keep editor in sync if parent resets the value (e.g. after load from API).
  useEffect(() => {
    if (!editor) return;
    const current = fromEditor(normaliseEditorHtml(editor.getHTML()));
    const incoming = value || '';
    // A `mergeFields` editor compares one serialisation of each side, so a value that only differs
    // in how a quote or an entity is written does not reset the caret mid-typing.
    const same = mergeFields
      ? canonicalHtml(incoming) === canonicalHtml(current)
      : incoming === current;
    if (!same && !(incoming === '' && current === '<p></p>')) {
      editor.commands.setContent(toEditor(incoming), { emitUpdate: false });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, editor]);

  useEffect(() => {
    if (!editor) return;
    // `false`: toggling editability is not an edit; emitting here would hand every mount an
    // onChange the user never made (DESIGNER-RICH-TEXT review B1).
    editor.setEditable(editable, false);
  }, [editable, editor]);

  useEffect(() => {
    if (editor && onEditorReady) onEditorReady(editor);
  }, [editor, onEditorReady]);

  if (!editor) return null;

  return (
    <div
      className={cn(
        'rounded-md border bg-background focus-within:ring-2 focus-within:ring-ring',
        className,
      )}
    >
      {toolbar === 'inline' ? <InlineToolbar editor={editor} /> : <Toolbar editor={editor} />}
      <EditorContent editor={editor} />
    </div>
  );
}

export default RichTextEditor;
