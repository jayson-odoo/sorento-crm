'use client';

/**
 * The requester's whole journey on one screen (UAC AC-5).
 *
 * Steps 2 to 4 of the journey in order: type the people in, say what each
 * needs, submit. After submit the SAME component renders the read-only status
 * view, because the grid the requester filled in is the grid she should
 * recognise when she comes back to check on it.
 *
 * There is no file upload: rows are typed into the system (captain decision,
 * 2026-08-15). The reader that used to accept a workbook, and the section
 * headings it inferred, went with it.
 */

import { useCallback, useMemo, useState } from 'react';
import { Loader2, Plus, Send } from 'lucide-react';
import { toast } from 'sonner';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardHeading, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { PeopleGrid } from '@/components/common/onboarding/PeopleGrid';
import type {
  OnboardingPerson,
  OnboardingPersonPatch,
} from '@/components/common/onboarding/types';
import { IntakeHeader } from './IntakeHeader';
import { applyPersonPatch, toDraftRow } from '../lib/onboarding-client';
import { useIntakeContext, useSubmitIntake } from '../hooks/useIntake';

/** "1 person", "2 people". A batch with one row on it is not "1 people". */
function people_(count: number): string {
  return count === 1 ? 'person' : 'people';
}

/** A blank row: adding a person is the only way a list is built now. */
function blankPerson(rowNumber: number): OnboardingPerson {
  return {
    id: `new-${rowNumber}-${Math.random().toString(36).slice(2, 8)}`,
    row_number: rowNumber,
    full_name: '',
    nick_name: null,
    role_label: null,
    phone_raw: null,
    email_raw: null,
    template_id: null,
    requester_note: null,
    reviewer_note: null,
    needs_system_account: true,
    needs_respond_contact: false,
    needs_agent_seat: false,
    review_status: 'proposed',
    rejection_reason: null,
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
  const [note, setNote] = useState('');
  const [submitted, setSubmitted] = useState(false);

  const contextQuery = useIntakeContext(token);

  const context = contextQuery.data;
  // The server's rows are the starting point; local edits take over once the
  // requester touches anything, so a background refetch cannot wipe her typing.
  const rows = people ?? context?.people ?? [];
  const editable = Boolean(context?.editable) && !submitted;

  const submitMutation = useSubmitIntake(token, {
    onSuccess: (result) => {
      setPeople(result.people);
      setSubmitted(true);
      toast.success(
        `${result.people.length} ${people_(result.people.length)} submitted for review.`,
      );
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
      return [...base, blankPerson(base.length + 1)];
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
          <AlertTitle>
            {rows.length} {people_(rows.length)} submitted for review.
          </AlertTitle>
        </Alert>
      ) : null}

      <PeopleGrid
        mode={editable ? 'intake' : 'readonly'}
        people={rows}
        templates={context.templates}
        title="People"
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
        emptyMessage={editable ? 'No people yet. Add a person.' : 'Nothing was submitted.'}
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
                  <Send className="size-4" />
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
