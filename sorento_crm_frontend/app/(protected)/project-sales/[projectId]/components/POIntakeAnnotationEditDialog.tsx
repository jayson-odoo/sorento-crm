'use client';

import * as React from 'react';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import type {
  POAnnotation,
  POAnnotationEditBody,
  POAnnotationInterpretation,
} from '../../_shared/types/poIntake.types';
import { PO_INTERPRETATION_LABELS } from '../../_shared/types/poIntake.types';

const INTERPRETATION_OPTIONS = (
  Object.keys(PO_INTERPRETATION_LABELS) as POAnnotationInterpretation[]
).map((value) => ({ value, label: PO_INTERPRETATION_LABELS[value] }));

/**
 * The human's reading of a pencil note, which then applies exactly as an accept does.
 *
 * Unknown keys already in `interpretation_json` are carried through untouched: the contract
 * says the shape depends on the interpretation, so anything the extractor put there that
 * this dialog has no field for must survive an edit rather than be dropped.
 */
export function POIntakeAnnotationEditDialog({
  annotation,
  saving,
  onClose,
  onSubmit,
}: {
  annotation: POAnnotation;
  saving: boolean;
  onClose: () => void;
  onSubmit: (body: POAnnotationEditBody) => Promise<void>;
}) {
  const existing = (annotation.interpretation_json ?? {}) as Record<string, unknown>;

  const [interpretation, setInterpretation] = React.useState<POAnnotationInterpretation>(
    annotation.interpretation,
  );
  const [lineNos, setLineNos] = React.useState(
    (asNumberArray(existing.line_nos) ?? annotation.refers_to_lines).join(', '),
  );
  const [code, setCode] = React.useState(asText(existing.code));
  const [description, setDescription] = React.useState(asText(existing.description));
  const [poNumber, setPoNumber] = React.useState(asText(existing.po_number));
  const [text, setText] = React.useState(
    asText(existing.text) || (annotation.raw_text ?? ''),
  );
  const [note, setNote] = React.useState('');

  const parsedLines = parseLineNos(lineNos);
  const touchesLines =
    interpretation === 'cancel_line' ||
    interpretation === 'amend_code' ||
    interpretation === 'amend_description';
  const blocked =
    (touchesLines && parsedLines.length === 0) ||
    (interpretation === 'amend_code' && !code.trim()) ||
    (interpretation === 'amend_description' && !description.trim()) ||
    (interpretation === 'successor_po' && !poNumber.trim());

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-h-[92vh] w-full max-w-lg overflow-hidden">
        <DialogHeader>
          <DialogTitle>Edit this reading</DialogTitle>
        </DialogHeader>

        <form
          onSubmit={async (event) => {
            event.preventDefault();
            const json: Record<string, unknown> = { ...existing };
            if (touchesLines) json.line_nos = parsedLines;
            if (interpretation === 'amend_code') json.code = code.trim();
            if (interpretation === 'amend_description')
              json.description = description.trim();
            if (interpretation === 'successor_po') json.po_number = poNumber.trim();
            if (interpretation === 'signature' || interpretation === 'other') {
              json.text = text.trim();
            }
            await onSubmit({
              interpretation,
              interpretation_json: json,
              note: note.trim() || null,
            });
          }}
        >
          <DialogBody className="max-h-[65vh] space-y-4 overflow-y-auto">
            {annotation.raw_text && (
              <div className="rounded-md border border-border bg-muted/40 px-3 py-2">
                <p className="text-xs text-muted-foreground">On the paper</p>
                <p className="mt-0.5 text-sm break-words">{annotation.raw_text}</p>
              </div>
            )}

            <div className="space-y-1.5">
              <Label htmlFor="po-annot-interpretation">What it means</Label>
              <SearchableSelect
                id="po-annot-interpretation"
                value={interpretation}
                onChange={(value) =>
                  setInterpretation(value as POAnnotationInterpretation)
                }
                options={INTERPRETATION_OPTIONS}
                placeholder="Pick one"
              />
            </div>

            {touchesLines && (
              <div className="space-y-1.5">
                <Label htmlFor="po-annot-lines">
                  Lines it points at<span className="text-destructive"> *</span>
                </Label>
                <Input
                  id="po-annot-lines"
                  value={lineNos}
                  onChange={(event) => setLineNos(event.target.value)}
                  placeholder="7, 20, 23"
                  inputMode="numeric"
                />
              </div>
            )}

            {interpretation === 'amend_code' && (
              <div className="space-y-1.5">
                <Label htmlFor="po-annot-code">
                  New code<span className="text-destructive"> *</span>
                </Label>
                <Input
                  id="po-annot-code"
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                  placeholder="As written"
                />
              </div>
            )}

            {interpretation === 'amend_description' && (
              <div className="space-y-1.5">
                <Label htmlFor="po-annot-description">
                  New description<span className="text-destructive"> *</span>
                </Label>
                <Input
                  id="po-annot-description"
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  placeholder="As written"
                />
              </div>
            )}

            {interpretation === 'successor_po' && (
              <div className="space-y-1.5">
                <Label htmlFor="po-annot-po">
                  Replacement PO number
                  <span className="text-destructive"> *</span>
                </Label>
                <Input
                  id="po-annot-po"
                  value={poNumber}
                  onChange={(event) => setPoNumber(event.target.value)}
                  placeholder="HQ/26/05/087"
                />
              </div>
            )}

            {(interpretation === 'signature' || interpretation === 'other') && (
              <div className="space-y-1.5">
                <Label htmlFor="po-annot-text">What it says</Label>
                <Input
                  id="po-annot-text"
                  value={text}
                  onChange={(event) => setText(event.target.value)}
                />
              </div>
            )}

            <div className="space-y-1.5">
              <Label htmlFor="po-annot-note">Note</Label>
              <Textarea
                id="po-annot-note"
                rows={2}
                value={note}
                onChange={(event) => setNote(event.target.value)}
                placeholder="Why your reading differs"
              />
            </div>
          </DialogBody>

          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={blocked || saving}>
              {saving ? 'Applying…' : 'Apply my reading'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function asText(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function asNumberArray(value: unknown): number[] | null {
  if (!Array.isArray(value)) return null;
  const numbers = value
    .map((item) => Number(item))
    .filter((item) => Number.isFinite(item));
  return numbers.length ? numbers : null;
}

export function parseLineNos(input: string): number[] {
  return Array.from(
    new Set(
      input
        .split(/[,\s]+/)
        .map((part) => Number(part.replace(/[()]/g, '')))
        .filter((value) => Number.isInteger(value) && value > 0),
    ),
  ).sort((a, b) => a - b);
}
