'use client';

/**
 * The requester's whole journey on one screen (UAC AC-5).
 *
 * Steps 2 to 4 of the journey in order: give us the people (sheet or typed),
 * say what each needs, submit. After submit the SAME component renders the
 * read-only status view, because the grid the requester filled in is the grid
 * she should recognise when she comes back to check on it.
 */

import { useCallback, useMemo, useState } from 'react';
import { Loader2, Plus, Upload } from 'lucide-react';
import { toast } from 'sonner';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardHeading, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { FileDropzone } from '@/components/common/FileDropzone';
import { PeopleGrid } from '@/components/common/onboarding/PeopleGrid';
import type {
  OnboardingPerson,
  OnboardingPersonPatch,
} from '@/components/common/onboarding/types';
import { IntakeHeader } from './IntakeHeader';
import { applyPersonPatch, toDraftRow } from '../lib/onboarding-client';
import { useIntakeContext, useParseSheet, useSubmitIntake } from '../hooks/useIntake';

const ACCEPTED = '.xlsx,.xlsm,.xls';

/** "1 person", "2 people". A sheet with one row on it is not "1 people". */
function people_(count: number): string {
  return count === 1 ? 'person' : 'people';
}

/** A blank row, so somebody with three people to add never needs a spreadsheet. */
function blankPerson(rowNumber: number, sectionLabel: string | null): OnboardingPerson {
  return {
    id: `new-${rowNumber}-${Math.random().toString(36).slice(2, 8)}`,
    row_number: rowNumber,
    full_name: '',
    nick_name: null,
    phone_raw: null,
    email_raw: null,
    section_label: sectionLabel,
    template_id: null,
    requester_note: null,
    reviewer_note: null,
    needs_system_account: true,
    needs_respond_contact: false,
    needs_agent_seat: false,
    review_status: 'proposed',
    rejection_reason: null,
    problems: [],
    collisions: [],
    user_step: 'pending',
    user_error: null,
    user_label: null,
    contact_step: 'pending',
    contact_error: null,
    agent_step: 'pending',
    agent_error: null,
  };
}

export function IntakeScreen({ token }: { token: string }) {
  const [people, setPeople] = useState<OnboardingPerson[] | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [note, setNote] = useState('');
  const [submitted, setSubmitted] = useState(false);

  const contextQuery = useIntakeContext(token);

  const context = contextQuery.data;
  // The server's rows are the starting point; local edits take over once the
  // requester touches anything, so a background refetch cannot wipe her typing.
  const rows = people ?? context?.people ?? [];
  const editable = Boolean(context?.editable) && !submitted;

  const parseMutation = useParseSheet(token, {
    onSuccess: (result) => {
      const parsed = result.rows.map((row, index) => ({
        ...blankPerson(index + 1, row.section_label),
        row_number: row.row_number,
        full_name: row.full_name,
        nick_name: row.nick_name,
        phone_raw: row.phone_raw,
        email_raw: row.email_raw,
        section_label: row.section_label,
        problems: row.problems,
      }));
      setPeople(parsed);
      setFiles([]);
      const problemCount = parsed.filter((p) => p.problems.length).length;
      const read = `Read ${parsed.length} ${people_(parsed.length)}`;
      toast.success(
        problemCount ? `${read}, ${problemCount} with issues.` : `${read}.`,
      );
    },
    onError: (e) => toast.error(e.message),
  });

  const submitMutation = useSubmitIntake(token, {
    onSuccess: (result) => {
      setPeople(result.people);
      setSubmitted(true);
      toast.success(`${result.people.length} people submitted for review.`);
    },
    onError: (e) => toast.error(e.message),
  });

  const patchPerson = useCallback((personId: string, patch: OnboardingPersonPatch) => {
    setPeople((current) => {
      const base = current ?? rows;
      return base.map((p) => (p.id === personId ? applyPersonPatch(p, patch) : p));
    });
    // `rows` is read through the setter's closure on purpose: the state may be
    // null on the first edit, in which case the server's rows are the base.
  }, [rows]);

  const removePerson = useCallback(
    (personId: string) => {
      setPeople((current) => (current ?? rows).filter((p) => p.id !== personId));
    },
    [rows],
  );

  const addRow = useCallback(() => {
    setPeople((current) => {
      const base = current ?? rows;
      const last = base[base.length - 1];
      return [...base, blankPerson(base.length + 1, last?.section_label ?? null)];
    });
  }, [rows]);

  const readyToSubmit = useMemo(
    () => rows.length > 0 && rows.every((p) => p.full_name.trim().length > 0),
    [rows],
  );

  if (contextQuery.isLoading) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-6 w-96 max-w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (contextQuery.isError || !context) {
    return (
      <Alert variant="destructive">
        <AlertIcon />
        <AlertTitle>
          {(contextQuery.error as Error)?.message ??
            'This link is no longer valid. Ask whoever sent it for a new one.'}
        </AlertTitle>
      </Alert>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <IntakeHeader context={submitted ? { ...context, status: 'submitted', editable: false } : context} />

      {!editable ? (
        <Alert>
          <AlertIcon />
          <AlertTitle>{rows.length} people submitted for review.</AlertTitle>
        </Alert>
      ) : (
        <Card>
          <CardHeader>
            <CardHeading>
              <CardTitle>People</CardTitle>
            </CardHeading>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <FileDropzone
              accept={ACCEPTED}
              files={files}
              maxSizeMb={10}
              disabled={parseMutation.isPending}
              onFilesChange={(next) => {
                setFiles(next);
                if (next[0]) parseMutation.mutate(next[0]);
              }}
              onReject={(file, reason) =>
                toast.error(
                  reason === 'size'
                    ? `${file.name} is too large.`
                    : reason === 'type'
                      ? `${file.name} is not an Excel workbook.`
                      : `${file.name} was ignored - one workbook at a time.`,
                )
              }
            />
            {parseMutation.isPending ? (
              <p className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" />
                Reading the workbook...
              </p>
            ) : null}
            {parseMutation.isError ? (
              <Alert variant="destructive">
                <AlertIcon />
                <AlertTitle>{(parseMutation.error as Error).message}</AlertTitle>
              </Alert>
            ) : null}
          </CardContent>
        </Card>
      )}

      <PeopleGrid
        mode={editable ? 'intake' : 'readonly'}
        people={rows}
        templates={context.templates}
        title={editable ? 'Access' : 'People'}
        actions={
          editable ? (
            <Button variant="outline" onClick={addRow}>
              <Plus className="size-4" />
              Add a person
            </Button>
          ) : null
        }
        onPatchPerson={patchPerson}
        onRemovePerson={editable ? removePerson : undefined}
        emptyMessage={
          editable ? 'No people yet. Upload a sheet or add a person.' : 'Nothing was submitted.'
        }
      />

      {editable ? (
        <Card>
          <CardHeader>
            <CardHeading>
              <CardTitle>Notes</CardTitle>
            </CardHeading>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <div className="flex flex-col gap-2">
              <Label htmlFor="requester-note">Notes</Label>
              <Textarea
                id="requester-note"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Optional"
                rows={3}
              />
            </div>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-sm text-muted-foreground">
                {rows.length} {people_(rows.length)} ready to submit.
              </p>
              <Button
                onClick={() => submitMutation.mutate({ rows: rows.map(toDraftRow), note: note.trim() || null })}
                disabled={!readyToSubmit || submitMutation.isPending}
              >
                {submitMutation.isPending ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Upload className="size-4" />
                )}
                Submit for review
              </Button>
            </div>
            {!readyToSubmit && rows.length > 0 ? (
              <p className="text-sm text-amber-700">Every person needs a name.</p>
            ) : null}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
