'use client';

/**
 * Google-Slides-style inline text edit (S2, D5): a plain `<textarea>` laid
 * directly over the Konva text node it is editing, matching its position,
 * size, font and rotation so there is no visible seam between "selected" and
 * "editing".
 *
 * Positioned with the SAME maths `KonvaTagLayer` uses for the node itself
 * (`layer.x_mm * scale`, offset by the ruler thickness and the current pan) -
 * every layer, grouped or not, carries its OWN absolute canvas-mm position
 * (there is no nested-Group coordinate space in this doc format), so this
 * needs nothing from Konva's own transform tree.
 *
 * Commit path mirrors the Inspector's Content box exactly (`onCommit` is
 * `writeSelectedContent` in the parent): a slot-bound layer writes through
 * `text_override`, an unbound one through `props.text`. Enter inserts a
 * newline (the browser's own default - nothing to handle); Esc, Cmd/Ctrl+Enter
 * or losing focus commits and closes.
 *
 * B/I/U/Shift+X are NOT handled here - `TagCanvasEditor`'s own keydown
 * handler answers them ahead of its `isInput`/`editingLayerId` guards, so
 * they work whether this editor is open or not (AC-S2-4).
 */

import { useEffect, useRef, useState, type CSSProperties } from 'react';
import type { TagLayer, TagLayerProps } from '@/lib/dealer-kit/tag-template-types';

interface InlineTextEditorProps {
  layer: TagLayer;
  /** Seed value - the same rule the Inspector's Content box resolves with. */
  value: string;
  /** mm -> px, already carrying the current zoom. */
  scale: number;
  /** Screen offset of canvas mm-(0,0), in px, relative to the positioned ancestor. */
  originX: number;
  originY: number;
  onCommit: (value: string) => void;
}

export function InlineTextEditor({
  layer,
  value,
  scale,
  originX,
  originY,
  onCommit,
}: InlineTextEditorProps) {
  const props = layer.props as Extract<TagLayerProps, { kind: 'text' }>;
  const [text, setText] = useState(value);
  const ref = useRef<HTMLTextAreaElement>(null);
  const committedRef = useRef(false);

  // Focused, caret at the end (AC-S2-1).
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.focus();
    el.setSelectionRange(el.value.length, el.value.length);
    // Only on mount - re-focusing on every keystroke would fight the caret.
  }, []);

  const commit = () => {
    if (committedRef.current) return;
    committedRef.current = true;
    onCommit(text);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    const modifier = e.ctrlKey || e.metaKey;
    if (e.key === 'Escape') {
      e.preventDefault();
      commit();
      return;
    }
    if (modifier && e.key === 'Enter') {
      e.preventDefault();
      commit();
    }
    // Plain Enter falls through to the textarea's own default: a newline.
  };

  const style: CSSProperties = {
    position: 'absolute',
    left: originX + layer.x_mm * scale,
    top: originY + layer.y_mm * scale,
    width: layer.width_mm * scale,
    height: layer.height_mm * scale,
    transform: layer.rotation_deg ? `rotate(${layer.rotation_deg}deg)` : undefined,
    transformOrigin: 'top left',
    fontFamily: props.fontFamily,
    fontSize: props.fontSize * scale * 0.35,
    fontWeight: props.fontWeight,
    fontStyle: props.italic ? 'italic' : 'normal',
    textDecoration:
      [props.underline && 'underline', props.strikethrough && 'line-through']
        .filter(Boolean)
        .join(' ') || 'none',
    color: props.color,
    textAlign: props.align,
    lineHeight: props.lineHeight,
    letterSpacing: props.letterSpacing ? props.letterSpacing * scale * 0.1 : undefined,
    padding: 0,
    margin: 0,
    border: '1px solid #3b82f6',
    outline: 'none',
    resize: 'none',
    background: '#ffffff',
    overflow: 'hidden',
    zIndex: 30,
  };

  return (
    <textarea
      ref={ref}
      data-testid="inline-text-editor"
      aria-label="Edit text"
      value={text}
      onChange={(e) => setText(e.target.value)}
      onKeyDown={handleKeyDown}
      onBlur={commit}
      style={style}
    />
  );
}
