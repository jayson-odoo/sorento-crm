'use client';

import { useEffect, useRef, useState } from 'react';
import { getOutstandingUploadConfig } from '../services/outstandingImportService';
import type { UploadTestResult } from '../components/UploadTestVerdict';

/**
 * SCM - the test-then-upload flow, shared by every SCM upload dialog.
 *
 * Three steps, and the first one is deliberately inert: **choosing a file does nothing at
 * all**. Test is an explicit press that reads the file and writes nothing, and Confirm is
 * what commits. Previewing on drop was the old behaviour and it is what the captain asked us
 * to stop: it made every SCM dialog behave unlike the GRN, SPO and customer importers next
 * door, it spent a long read on a file the operator may only have mis-clicked, and it left
 * "Test" meaning something different here from everywhere else.
 *
 * Nothing is ever saved from a single click either: the whole reorder plan is computed from
 * these files, so a wrong one quietly imported is a week of unpicking.
 *
 * Extracted the moment there was a SECOND upload channel, because the parts that are easy
 * to get subtly wrong are exactly the parts that would have been copied: the sequence guard
 * that stops a stale preview landing on top of a newer one, the reset on reopen, and the
 * accept list coming from the server rather than a second copy in the browser.
 *
 * What it deliberately does NOT own is the rendering. A diff of changed order lines and a
 * summary of an imported order book have nothing in common on screen, and pushing both
 * through one component would produce a component that is a switch statement.
 */

/** The minimum a preview must carry: whether the file is usable at all. */
export interface TwoStepPreview {
  ok: boolean;
}

/**
 * What to offer before the server has said what it accepts.
 *
 * The list is the SERVER's (`SCM_UPLOAD_EXTENSIONS`, served by `/outstanding/config`) - a
 * second authoritative copy in the browser is exactly how the first dialog came to refuse a
 * legacy `.xls` that the reader parses perfectly well. This constant is only the value used
 * for the fraction of a second before the real one arrives.
 */
export const FALLBACK_ACCEPT = '.xlsx,.xlsm,.xls';

export const MAX_SIZE_MB = 25;

export interface UseTwoStepUploadOptions<TPreview extends TwoStepPreview, TResult> {
  /** Dialog visibility. Every open resets the flow, so a second visit never shows the first
      visit's result. */
  open: boolean;
  /** What Test runs. Reads the file, writes nothing. */
  preview: (file: File) => Promise<TPreview>;
  apply: (file: File) => Promise<TResult>;
  /**
   * Optional second read for the channels whose backend also offers `?validate_only=true`:
   * the standard `{valid, errors, warnings}` verdict. Run by Test ALONGSIDE the preview, not
   * instead of it, so one press gives one answer however many endpoints are behind it.
   */
  test?: (file: File) => Promise<UploadTestResult>;
  onApplied?: (result: TResult) => void;
}

export interface TwoStepUpload<TPreview extends TwoStepPreview, TResult> {
  file: File | null;
  preview: TPreview | null;
  result: TResult | null;
  previewing: boolean;
  applying: boolean;
  error: string | null;
  /** Comma-separated, for the dropzone. */
  accept: string;
  /** ".xlsx or .xlsm or .xls", for a message a person reads. */
  acceptedFormats: string;
  /** Take the file. Runs NOTHING - see the note at the top of this file. */
  choose: (next: File | null) => void;
  reject: (rejected: File, reason: 'type' | 'size' | 'extra') => void;
  confirm: () => Promise<void>;
  /**
   * True when a file is picked, no request is in flight, and nothing already read says the
   * file is unusable. Testing is never REQUIRED: the operator may confirm a file they have
   * not tested, exactly as they can in the GRN and customer importers.
   */
  canConfirm: boolean;
  /** The Test verdict, once run. Null until then; cleared on a new file. */
  testResult: UploadTestResult | null;
  testing: boolean;
  /** Read the file and report. Always present: every channel can be tested. */
  runTest: () => Promise<void>;
}

function messageOf(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

export function useTwoStepUpload<TPreview extends TwoStepPreview, TResult>({
  open,
  preview: previewFn,
  apply: applyFn,
  test: testFn,
  onApplied,
}: UseTwoStepUploadOptions<TPreview, TResult>): TwoStepUpload<TPreview, TResult> {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<TPreview | null>(null);
  const [result, setResult] = useState<TResult | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<UploadTestResult | null>(null);
  const [testing, setTesting] = useState(false);
  const [accept, setAccept] = useState<string>(FALLBACK_ACCEPT);
  const acceptedFormats = accept.split(',').join(' or ');

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    void getOutstandingUploadConfig()
      .then((cfg) => {
        if (!cancelled && cfg.allowed_extensions?.length) {
          setAccept(cfg.allowed_extensions.join(','));
        }
      })
      // A failure here is not worth a banner: the dropzone keeps the fallback list and the
      // server still refuses anything it does not accept, with its own message.
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [open]);

  // A second pick while the first preview is still in flight must not have the older
  // response land on top of the newer one.
  const seq = useRef(0);

  useEffect(() => {
    if (!open) return;
    seq.current += 1;
    setFile(null);
    setPreview(null);
    setResult(null);
    setPreviewing(false);
    setApplying(false);
    setTesting(false);
    setTestResult(null);
    setError(null);
  }, [open]);

  const choose = (next: File | null) => {
    // No fetch. Picking a file is not a decision to do anything with it, and a dialog that
    // starts reading on drop cannot be cancelled by putting the mouse down somewhere else.
    seq.current += 1;
    setFile(next);
    setPreview(null);
    setResult(null);
    // A verdict belongs to the file it was run against. Carrying it onto the next pick is
    // how somebody uploads a bad file on the strength of a green tick for a different one.
    setTestResult(null);
    setError(null);
  };

  const reject = (rejected: File, reason: 'type' | 'size' | 'extra') => {
    // Single-file zone: the first file is already previewing, the rest are noise.
    if (reason === 'extra') return;
    if (reason === 'size') {
      setError(`${rejected.name} is larger than ${MAX_SIZE_MB} MB.`);
      return;
    }
    // 'type': the accept list is authoritative, so refuse it now. Uploading it to be told
    // what the extension already said would cost the user a round trip, and forwarding a
    // file the dropzone rejected would make its filter mean nothing.
    setError(`${rejected.name} is not a ${acceptedFormats} file.`);
  };

  const runTest = async () => {
    if (!file) return;
    const token = ++seq.current;
    setTesting(true);
    setPreviewing(true);
    setError(null);
    try {
      // Both reads on one press. A channel with a `validate_only` endpoint has two things to
      // say about the same file - what it would change, and whether anything blocks - and
      // making the operator press twice to hear both is how one of them stops being read.
      const [previewed, verdict] = await Promise.all([
        previewFn(file),
        testFn ? testFn(file) : Promise.resolve(null),
      ]);
      if (seq.current !== token) return;
      setPreview(previewed);
      if (verdict) setTestResult(verdict);
    } catch (e) {
      if (seq.current !== token) return;
      setError(messageOf(e, 'Failed to read the file.'));
    } finally {
      if (seq.current === token) {
        setTesting(false);
        setPreviewing(false);
      }
    }
  };

  const confirm = async () => {
    if (!file) return;
    setApplying(true);
    setError(null);
    try {
      const applied = await applyFn(file);
      setResult(applied);
      onApplied?.(applied);
    } catch (e) {
      setError(messageOf(e, 'Failed to apply the upload.'));
    } finally {
      setApplying(false);
    }
  };

  return {
    file,
    preview,
    result,
    previewing,
    applying,
    error,
    accept,
    acceptedFormats,
    choose,
    reject,
    confirm,
    // Testing is never mandatory - forcing it before every upload makes it ceremony rather
    // than a tool - but a file already KNOWN to be unusable is never confirmable.
    canConfirm: !!file && !applying && !testing && !previewing && (!preview || preview.ok),
    testResult,
    testing,
    runTest,
  };
}
