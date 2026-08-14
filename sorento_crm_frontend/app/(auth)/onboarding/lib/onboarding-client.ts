/**
 * The public onboarding intake API contract (UAC AC-3.6).
 *
 * Every call is gated by the per-request token, sent as `X-Onboarding-Token`.
 * There is no account, no NextAuth session and no cookie: this module is the
 * whole auth story for the intake page.
 *
 *   GET  /api/v1/public/onboarding/me
 *        200 OnboardingIntakeContext - company, requester, expiry, status,
 *            template LABELS (never roles), and the rows saved so far.
 *        401 unknown / expired / revoked token.
 *
 *   POST /api/v1/public/onboarding/parse        multipart { file }
 *        200 OnboardingParseResult - rows plus per-row problems. Writes nothing.
 *        429 per-IP rate limit (the endpoint is unauthenticated compute).
 *
 *   PUT  /api/v1/public/onboarding/rows          { rows: OnboardingDraftRow[] }
 *        200 { people } - whole-list replace, keyed on row_number.
 *        409 once the request has left `sent`.
 *
 *   POST /api/v1/public/onboarding/submit        { requester_note }
 *        200 OnboardingIntakeContext with `editable: false`. The same token now
 *            serves the read-only status page (AC-3.4).
 *
 * PHASE 1: the bodies below answer from `__mocks__/onboarding.ts` so the screen
 * can be built and reviewed before any endpoint exists. Phase 2 replaces the
 * bodies only - the signatures above are the contract the backend is built to.
 */

import type {
  OnboardingIntakeContext,
  OnboardingParseResult,
  OnboardingPerson,
  OnboardingPersonPatch,
} from '@/components/common/onboarding/types';
import {
  MOCK_INTAKE_CONTEXT,
  MOCK_PARSE_RESULT,
  MOCK_PEOPLE,
} from '../__mocks__/onboarding';

/** A row on its way to the server: no ids, no lane state, no verdict. */
export interface OnboardingDraftRow {
  row_number: number;
  full_name: string;
  nick_name: string | null;
  phone_raw: string | null;
  email_raw: string | null;
  section_label: string | null;
  template_id: string | null;
  requester_note: string | null;
  needs_system_account: boolean;
  needs_respond_contact: boolean;
  needs_agent_seat: boolean;
}

export function toDraftRow(person: OnboardingPerson): OnboardingDraftRow {
  return {
    row_number: person.row_number,
    full_name: person.full_name,
    nick_name: person.nick_name,
    phone_raw: person.phone_raw,
    email_raw: person.email_raw,
    section_label: person.section_label,
    template_id: person.template_id,
    requester_note: person.requester_note,
    needs_system_account: person.needs_system_account,
    needs_respond_contact: person.needs_respond_contact,
    needs_agent_seat: person.needs_agent_seat,
  };
}

/** Apply a patch to a person row. Shared by both screens so an edit means one thing. */
export function applyPersonPatch(
  person: OnboardingPerson,
  patch: OnboardingPersonPatch,
): OnboardingPerson {
  return { ...person, ...patch };
}

const MOCK_DELAY_MS = 250;

function later<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), MOCK_DELAY_MS));
}

export async function fetchIntakeContext(token: string): Promise<OnboardingIntakeContext> {
  // PHASE 1 mock. `token` is threaded through so the swap is body-only.
  if (!token) throw new Error('This link is missing its token.');
  if (token === 'expired') throw new Error('This link has expired.');
  if (token === 'empty') return later({ ...MOCK_INTAKE_CONTEXT, people: [] });
  if (token === 'submitted') {
    return later({
      ...MOCK_INTAKE_CONTEXT,
      status: 'submitted' as const,
      editable: false,
      people: MOCK_PEOPLE,
    });
  }
  return later({ ...MOCK_INTAKE_CONTEXT, people: [] });
}

export async function parseSheet(token: string, file: File): Promise<OnboardingParseResult> {
  if (!token) throw new Error('This link is missing its token.');
  // PHASE 1 mock: any workbook answers with the PHONE LIST shape.
  if (!/\.(xlsx|xlsm|xls)$/i.test(file.name)) {
    throw new Error('Upload an Excel workbook (.xlsx, .xlsm or .xls).');
  }
  return later(MOCK_PARSE_RESULT);
}

export async function saveRows(
  token: string,
  rows: OnboardingDraftRow[],
): Promise<{ people: OnboardingPerson[] }> {
  if (!token) throw new Error('This link is missing its token.');
  return later({
    people: rows.map((row, index) => ({
      ...MOCK_PEOPLE[0],
      ...row,
      id: `person-${index + 1}`,
      reviewer_note: null,
      review_status: 'proposed' as const,
      rejection_reason: null,
      problems: [],
      collisions: [],
    })),
  });
}

export async function submitIntake(
  token: string,
  requesterNote: string | null,
): Promise<OnboardingIntakeContext> {
  if (!token) throw new Error('This link is missing its token.');
  return later({
    ...MOCK_INTAKE_CONTEXT,
    status: 'submitted' as const,
    editable: false,
    requester_note: requesterNote,
    people: MOCK_PEOPLE,
  });
}
