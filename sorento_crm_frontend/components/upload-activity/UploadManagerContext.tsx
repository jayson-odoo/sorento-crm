'use client';

/**
 * UploadManagerContext — FE-only optimistic state for upload sessions.
 *
 * Owns sessions that the user just submitted, before the backend has
 * acknowledged all POSTs. Each session is merged with the BE
 * `/upload-activity` feed by `useUploadActivity` — the BE entry, once
 * present, wins, and the optimistic copy is cleared via `reconcile`.
 *
 * Phase 2: callers MUST pass an `uploader` closure to `startSession`. The
 * simulated uploader has been removed.
 *
 * No Zustand in repo — uses React Context + useReducer.
 */

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useReducer,
  useRef,
  type ReactNode,
} from 'react';
import { useQueryClient } from '@tanstack/react-query';

import type {
  SessionStatus,
  SessionType,
  UploadActivityFile,
  UploadActivitySession,
} from './types';
import { UPLOAD_ACTIVITY_QUERY_KEY } from './queryKeys';

// ---- state ----------------------------------------------------------------

interface OptimisticState {
  sessions: Record<string, UploadActivitySession>;
  isDrawerOpen: boolean;
}

type Action =
  | {
      type: 'pushSession';
      session: UploadActivitySession;
      blobs: Record<string, File>;
    }
  | {
      type: 'markFilePosted';
      sessionId: string;
      clientId: string;
      attachmentId: string;
    }
  | {
      type: 'markFileFailed';
      sessionId: string;
      clientId: string;
      errorCode: string;
      errorMessage: string;
    }
  | {
      type: 'reconcileSession';
      sessionId: string;
    }
  | { type: 'setDrawerOpen'; open: boolean };

function recomputeAggregate(
  files: UploadActivityFile[],
): UploadActivitySession['aggregate'] {
  return {
    total: files.length,
    uploading: files.filter((f) => f.status === 'uploading').length,
    processing: files.filter((f) => f.status === 'processing').length,
    linked: files.filter((f) => f.status === 'linked').length,
    unlinked: files.filter((f) => f.status === 'unlinked').length,
    failed: files.filter(
      (f) => f.status === 'failed' || f.status === 'post_failed',
    ).length,
  };
}

function recomputeSessionStatus(
  aggregate: UploadActivitySession['aggregate'],
): SessionStatus {
  if (aggregate.uploading > 0) return 'uploading';
  if (aggregate.processing > 0) return 'processing';
  if (aggregate.failed === aggregate.total) return 'failed';
  if (aggregate.unlinked > 0 || aggregate.failed > 0) return 'partial';
  return 'linked';
}

function reducer(state: OptimisticState, action: Action): OptimisticState {
  switch (action.type) {
    case 'pushSession':
      return {
        ...state,
        sessions: {
          ...state.sessions,
          [action.session.session_id]: action.session,
        },
      };

    case 'markFilePosted': {
      const session = state.sessions[action.sessionId];
      if (!session) return state;
      const files = session.files.map((f) =>
        f.client_id === action.clientId
          ? {
              ...f,
              attachment_id: action.attachmentId,
              status: 'processing' as const,
              last_updated_at: new Date().toISOString(),
              _post_blob: undefined,
            }
          : f,
      );
      const aggregate = recomputeAggregate(files);
      return {
        ...state,
        sessions: {
          ...state.sessions,
          [action.sessionId]: {
            ...session,
            files,
            aggregate,
            status: recomputeSessionStatus(aggregate),
          },
        },
      };
    }

    case 'markFileFailed': {
      const session = state.sessions[action.sessionId];
      if (!session) return state;
      const files = session.files.map((f) =>
        f.client_id === action.clientId
          ? {
              ...f,
              status: 'post_failed' as const,
              error_code: action.errorCode,
              error_message: action.errorMessage,
              last_updated_at: new Date().toISOString(),
            }
          : f,
      );
      const aggregate = recomputeAggregate(files);
      return {
        ...state,
        sessions: {
          ...state.sessions,
          [action.sessionId]: {
            ...session,
            files,
            aggregate,
            status: recomputeSessionStatus(aggregate),
            needs_action: true,
          },
        },
      };
    }

    case 'reconcileSession': {
      // BE has the session — drop the optimistic copy. The drawer
      // merge layer will keep showing the BE version.
      const { [action.sessionId]: _drop, ...rest } = state.sessions;
      return { ...state, sessions: rest };
    }

    case 'setDrawerOpen':
      return { ...state, isDrawerOpen: action.open };

    default:
      return state;
  }
}

// ---- context --------------------------------------------------------------

interface UploadManagerApi {
  state: OptimisticState;
  /** Submit a new upload session. Triggers background POSTs. Returns sessionId. */
  startSession: (input: StartSessionInput) => string;
  /** Retry a single file (POST_FAILED state) using the cached blob. */
  retryFile: (sessionId: string, clientId: string) => Promise<void>;
  /** Open or close the drawer (also called on icon click). */
  setDrawerOpen: (open: boolean) => void;
}

export interface StartSessionInput {
  /** File blobs the user picked. */
  files: File[];
  /** "single" if 1 file, else "multi". `bulk_zip` is BE-side only. */
  sessionType: SessionType;
  /** Optional pre-generated upload_batch_id; auto-generated if absent. */
  uploadBatchId?: string;
  /** Per-file uploader. Required — must wrap the api-client POST and
   *  resolve to the attachment id (or throw on failure). */
  uploader: (file: File, batchId: string) => Promise<{ attachment_id: string }>;

  // ---- `import_job` sessions (Excel/data imports) --------------------------
  // Without these, an Excel import could only ever open the drawer and show
  // nothing: `notifyImportQueued()` just invalidates the BE feed, and the feed
  // has no row until the worker has created the job. These let the page that
  // queued the import show its own row immediately; the BE entry replaces it
  // through the normal reconcile path as soon as it exists.
  /** The queued job's id, so the row navigates to its import-job page. */
  importJobId?: string;
  /** Override the derived title (filename for `single`, "N files" otherwise). */
  title?: string;
  /** Which import this is, for the row summary. */
  jobType?: string;
  /** Rows the dry run counted, so the row shows scale before the worker
   *  reports any progress of its own. */
  totalRows?: number;
}

const Ctx = createContext<UploadManagerApi | null>(null);

// ---- provider -------------------------------------------------------------

function genId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function')
    return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export function UploadManagerProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [state, dispatch] = useReducer(reducer, {
    sessions: {},
    isDrawerOpen: false,
  });

  // Track in-flight uploads to support retry without leaking timers.
  const inFlightRef = useRef<Map<string, AbortController>>(new Map());
  // Cache the uploader closure per session so retryFile can re-fire the
  // same upload after a transient failure without the caller re-passing it.
  const uploaderRef = useRef<
    Map<string, (file: File, batchId: string) => Promise<{ attachment_id: string }>>
  >(new Map());

  const setDrawerOpen = useCallback((open: boolean) => {
    dispatch({ type: 'setDrawerOpen', open });
  }, []);

  const runUploadsForSession = useCallback(
    (
      sessionId: string,
      files: { client_id: string; blob: File }[],
      uploader: StartSessionInput['uploader'],
    ) => {
      files.forEach(({ client_id, blob }) => {
        const key = `${sessionId}:${client_id}`;
        const controller = new AbortController();
        inFlightRef.current.set(key, controller);

        uploader(blob, sessionId)
          .then((res) => {
            if (controller.signal.aborted) return;
            dispatch({
              type: 'markFilePosted',
              sessionId,
              clientId: client_id,
              attachmentId: res.attachment_id,
            });
            // Tell the BE feed to refetch so the real session replaces the
            // optimistic copy as soon as the row + integration_log exist.
            void queryClient.invalidateQueries({ queryKey: UPLOAD_ACTIVITY_QUERY_KEY });
          })
          .catch((err: Error) => {
            if (controller.signal.aborted) return;
            dispatch({
              type: 'markFileFailed',
              sessionId,
              clientId: client_id,
              errorCode: 'POST_FAILED',
              errorMessage: err.message ?? 'Upload failed',
            });
          })
          .finally(() => {
            inFlightRef.current.delete(key);
          });
      });
    },
    [queryClient],
  );

  const startSession = useCallback(
    (input: StartSessionInput): string => {
      // Key an import_job session on the JOB id, because that is what the
      // backend keys its own row on (`session_id = str(job.job_id)`). The merge
      // in useUploadActivity dedupes on session_id, so a random id here means
      // the optimistic row and the real one are two different sessions: the
      // drawer shows the same import twice until a refresh drops the optimistic
      // half. uploadBatchId still wins for attachment batches, which is what
      // the backend groups those on.
      const sessionId = input.uploadBatchId ?? input.importJobId ?? genId();
      const nowIso = new Date().toISOString();

      const files: UploadActivityFile[] = input.files.map((f) => ({
        client_id: genId(),
        attachment_id: null,
        filename: f.name,
        status: 'uploading',
        summary: '',
        linked: [],
        unlinked_reasons: [],
        error_code: null,
        error_message: null,
        integration_log_id: null,
        last_updated_at: nowIso,
        _post_blob: f,
      }));

      const session: UploadActivitySession = {
        session_id: sessionId,
        session_type: input.sessionType,
        title:
          input.title ??
          (input.sessionType === 'single' && input.files[0]
            ? input.files[0].name
            : `${input.files.length} files`),
        started_at: nowIso,
        finished_at: null,
        status: 'uploading',
        aggregate: recomputeAggregate(files),
        files,
        import_job_id: input.importJobId ?? null,
        needs_action: false,
        job_type: input.jobType ?? null,
        total_rows: input.totalRows ?? null,
      };

      const blobs: Record<string, File> = {};
      session.files.forEach((f, i) => {
        const blob = input.files[i];
        if (blob) blobs[f.client_id] = blob;
      });

      dispatch({ type: 'pushSession', session, blobs });
      dispatch({ type: 'setDrawerOpen', open: true });

      runUploadsForSession(
        sessionId,
        session.files.map((f) => ({
          client_id: f.client_id,
          blob: f._post_blob as File,
        })),
        input.uploader,
      );
      // Remember the uploader for retryFile.
      uploaderRef.current.set(sessionId, input.uploader);

      return sessionId;
    },
    [runUploadsForSession],
  );

  const retryFile = useCallback(
    async (sessionId: string, clientId: string): Promise<void> => {
      const session = state.sessions[sessionId];
      if (!session) return;
      const file = session.files.find((f) => f.client_id === clientId);
      if (!file?._post_blob) return;
      const uploader = uploaderRef.current.get(sessionId);
      if (!uploader) return;
      runUploadsForSession(
        sessionId,
        [{ client_id: clientId, blob: file._post_blob }],
        uploader,
      );
    },
    [state.sessions, runUploadsForSession],
  );

  const value = useMemo<UploadManagerApi>(
    () => ({ state, startSession, retryFile, setDrawerOpen }),
    [state, startSession, retryFile, setDrawerOpen],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useUploadManager(): UploadManagerApi {
  const ctx = useContext(Ctx);
  if (!ctx)
    throw new Error('useUploadManager must be used inside <UploadManagerProvider>');
  return ctx;
}

// Convenience selector hooks for components that only need read access.
export function useOptimisticSessions(): UploadActivitySession[] {
  const { state } = useUploadManager();
  return Object.values(state.sessions);
}
