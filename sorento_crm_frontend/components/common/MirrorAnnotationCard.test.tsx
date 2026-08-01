/**
 * MirrorAnnotationCard — the ONE editable surface on every AutoCount mirror.
 * Shared across all 12 mirror detail pages, so its behaviour is pinned here:
 *   - Save is disabled until the user actually changes something (no accidental
 *     no-op writes);
 *   - Save reports both fields;
 *   - the card reconciles when the underlying record changes (refetch);
 *   - the saving state disables Save.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { MirrorAnnotationCard } from './MirrorAnnotationCard';

beforeEach(() => cleanup());

describe('MirrorAnnotationCard', () => {
  it('renders the existing note and follow-up value', () => {
    render(
      <MirrorAnnotationCard
        value={{ internal_note: 'existing note', follow_up: true }}
        onSave={vi.fn()}
      />,
    );
    expect((screen.getByLabelText('Note') as HTMLTextAreaElement).value).toBe('existing note');
    expect(screen.getByRole('switch')).toHaveAttribute('data-state', 'checked');
  });

  it('keeps Save disabled until something changes', () => {
    render(
      <MirrorAnnotationCard value={{ internal_note: 'a', follow_up: false }} onSave={vi.fn()} />,
    );
    const save = screen.getByRole('button', { name: /save note/i });
    expect(save).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Note'), { target: { value: 'a changed' } });
    expect(save).toBeEnabled();
  });

  it('reports both fields on save', () => {
    const onSave = vi.fn();
    render(
      <MirrorAnnotationCard value={{ internal_note: '', follow_up: false }} onSave={onSave} />,
    );
    fireEvent.change(screen.getByLabelText('Note'), { target: { value: 'new note' } });
    fireEvent.click(screen.getByRole('button', { name: /save note/i }));
    expect(onSave).toHaveBeenCalledWith({ internal_note: 'new note', follow_up: false });
  });

  it('disables Save while saving', () => {
    render(
      <MirrorAnnotationCard
        value={{ internal_note: 'x', follow_up: false }}
        onSave={vi.fn()}
        isSaving
      />,
    );
    // dirty the field so the only reason it could still be disabled is isSaving
    fireEvent.change(screen.getByLabelText('Note'), { target: { value: 'y' } });
    expect(screen.getByRole('button', { name: /saving/i })).toBeDisabled();
  });

  it('reconciles local state when the record changes', () => {
    const { rerender } = render(
      <MirrorAnnotationCard value={{ internal_note: 'first', follow_up: false }} onSave={vi.fn()} />,
    );
    expect((screen.getByLabelText('Note') as HTMLTextAreaElement).value).toBe('first');
    rerender(
      <MirrorAnnotationCard value={{ internal_note: 'second', follow_up: true }} onSave={vi.fn()} />,
    );
    expect((screen.getByLabelText('Note') as HTMLTextAreaElement).value).toBe('second');
  });
});
