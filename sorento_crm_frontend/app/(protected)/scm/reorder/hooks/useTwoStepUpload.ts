'use client';

import { useEffect, useRef, useState } from 'react';
import { getOutstandingUploadConfig } from '../services/outstandingImportService';

/**
 * SCM - the preview-then-confirm upload flow, shared by every SCM upload dialog.
 *
 * Two steps, never one click: choosing a file PREVIEWS it (writes nothing) and the user
 * confirms before anything is saved. The whole reorder plan is computed from these files,
 * so a wrong one quietly imported is a week of unpicking.
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
  preview: (file: File) => Promise<TPreview>;
  apply: (file: File) => Promise<TResult>;
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
  choose: (next: File | null) => Promise<void>;
  reject: (rejected: File, reason: 'type' | 'size' | 'extra') => void;
  confirm: () => Promise<void>;
  /** True when a file is picked, readable, and neither request is in flight. */
  canConfirm: boolean;
}

function messageOf(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

export function useTwoStepUpload<TPreview extends TwoStepPreview, TResult>({
  open,
  preview: previewFn,
  apply: applyFn,
  onApplied,
}: UseTwoStepUploadOptions<TPreview, TResult>): TwoStepUpload<TPreview, TResult> {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<TPreview | null>(null);
  const [result, setResult] = useState<TResult | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
    setError(null);
  }, [open]);

  const choose = async (next: File | null) => {
    const token = ++seq.current;
    setFile(next);
    setPreview(null);
    setResult(null);
    setError(null);
    if (!next) return;

    setPreviewing(true);
    try {
      const previewed = await previewFn(next);
      if (seq.current !== token) return;
      setPreview(previewed);
    } catch (e) {
      if (seq.current !== token) return;
      setError(messageOf(e, 'Failed to read the file.'));
    } finally {
      if (seq.current === token) setPreviewing(false);
    }
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
    canConfirm: !!file && !!preview && preview.ok && !previewing && !applying,
  };
}
