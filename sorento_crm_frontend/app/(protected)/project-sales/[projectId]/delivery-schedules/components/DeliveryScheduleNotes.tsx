'use client';

import type { ScheduleNote } from '../../../_shared/types/deliverySchedule.types';

/**
 * Free-text remarks the extractor found on the page but did not interpret (section 9.7a).
 *
 * Some revisions arrive as prose in the margin rather than as a phase-column change - "ONLY
 * FOR FLOOR TRAP TO BE DELIVER IN 2026, START FROM 23/7/2026" is not a cell edit, it is a
 * sentence a person reads. Verbatim, never turned into a date here. The header always shows,
 * empty or not: a note the reader missed because the section was hidden is worse than one that
 * had nothing to say.
 */
export function DeliveryScheduleNotes({ notes }: { notes: ScheduleNote[] }) {
  return (
    <div className="rounded-lg border border-border bg-muted/30 px-3 py-2.5 text-sm">
      <p className="font-medium">Notes on the document</p>
      {notes.length === 0 ? (
        <p className="mt-1 text-muted-foreground">No notes on the document</p>
      ) : (
        <ul className="mt-1 space-y-1">
          {notes.map((note, index) => (
            <li key={index} className="break-words text-muted-foreground">
              {note.page_no !== null ? `Page ${note.page_no}: ${note.text}` : note.text}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
