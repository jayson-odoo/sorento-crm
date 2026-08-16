'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Recording a voice message in the chat composer (UAC AC-L9).
 *
 * The clip is handed back as a `File` so the composer stages it through the
 * SAME path the Attach button and paste use - one send, one outbox row, one
 * thread bubble, no new plumbing.
 */

/** Hard cap. A voice note is a reply, not a podcast, and an open mic is the
 *  failure that matters: it stops itself at 2 minutes. */
export const VOICE_MAX_DURATION_MS = 120_000;

/**
 * Container preference, best first.
 *
 * Verified live against Respond.io 2026-08-16 (the same upload + send path the
 * composer uses, to the one outbound-enabled contact): all three were accepted
 * by the API, but Respond's own file inspection came back
 * `isFileTypeSupported: false` for the webm clip and typed it `video/webm`,
 * while the mp4 clip read `audio/x-m4a` and the ogg clip
 * `audio/ogg; codecs=opus` with no such flag. That matches Meta's documented
 * audio formats (aac, mp4, mpeg, amr, ogg-opus - no webm), so webm is the last
 * resort, never the default.
 */
export const VOICE_MIME_PREFERENCE = [
  'audio/mp4',
  'audio/ogg;codecs=opus',
  'audio/webm;codecs=opus',
] as const;

const EXTENSION_BY_MIME: { prefix: string; ext: string }[] = [
  { prefix: 'audio/mp4', ext: 'm4a' },
  { prefix: 'audio/ogg', ext: 'ogg' },
  { prefix: 'audio/webm', ext: 'webm' },
];

const NOT_SUPPORTED = 'Voice recording is not supported in this browser.';
const BLOCKED = 'Microphone access is blocked.';

/** The first container this browser can record that Respond.io will take, or null. */
export function pickVoiceMimeType(): string | null {
  if (typeof MediaRecorder === 'undefined') return null;
  const isSupported = MediaRecorder.isTypeSupported;
  if (typeof isSupported !== 'function') return null;
  return VOICE_MIME_PREFERENCE.find((mime) => isSupported.call(MediaRecorder, mime)) ?? null;
}

export function isVoiceRecordingSupported(): boolean {
  if (typeof navigator === 'undefined') return false;
  if (typeof navigator.mediaDevices?.getUserMedia !== 'function') return false;
  return pickVoiceMimeType() !== null;
}

/** `voice-message-20260816-2231.m4a` - readable in the staged chip, in the
 *  outbox, and as the filename WhatsApp shows the contact. */
export function voiceFileName(mime: string, at: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  const stamp =
    `${at.getFullYear()}${pad(at.getMonth() + 1)}${pad(at.getDate())}` +
    `-${pad(at.getHours())}${pad(at.getMinutes())}${pad(at.getSeconds())}`;
  const ext = EXTENSION_BY_MIME.find((e) => mime.startsWith(e.prefix))?.ext ?? 'bin';
  return `voice-message-${stamp}.${ext}`;
}

/** mm:ss for the elapsed counter shown while recording. */
export function formatElapsed(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${String(secs).padStart(2, '0')}`;
}

interface UseVoiceRecorderOptions {
  /** Called with the finished clip. Not called on cancel, nor on an empty clip. */
  onClip: (file: File) => void;
  maxDurationMs?: number;
}

export interface VoiceRecorderState {
  /** False when the browser cannot record, or the user blocked the microphone. */
  available: boolean;
  /** Short reason for `available === false`; null when it is available. */
  reason: string | null;
  recording: boolean;
  seconds: number;
  /** Resolves with a short reason when it could not start, otherwise null. */
  start: () => Promise<string | null>;
  stop: () => void;
  cancel: () => void;
}

export function useVoiceRecorder({
  onClip,
  maxDurationMs = VOICE_MAX_DURATION_MS,
}: UseVoiceRecorderOptions): VoiceRecorderState {
  const [supported, setSupported] = useState(false);
  const [blocked, setBlocked] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const cancelledRef = useRef(false);
  // getUserMedia can resolve AFTER unmount - the permission prompt is open when
  // the drawer closes. The cleanup has already run by then, so without this the
  // stream assigned below is one nothing ever stops: a live microphone for the
  // life of the tab.
  const unmountedRef = useRef(false);
  const tickRef = useRef<number | null>(null);
  const capRef = useRef<number | null>(null);
  // Kept in a ref so the recorder's onstop always calls the CURRENT handler
  // without re-creating the recorder on every composer render.
  const onClipRef = useRef(onClip);
  useEffect(() => {
    onClipRef.current = onClip;
  }, [onClip]);

  // Feature detection runs after mount: the server renders no MediaRecorder, so
  // deciding this during render would be a hydration mismatch.
  useEffect(() => {
    setSupported(isVoiceRecordingSupported());
  }, []);

  const clearTimers = useCallback(() => {
    if (tickRef.current !== null) window.clearInterval(tickRef.current);
    if (capRef.current !== null) window.clearTimeout(capRef.current);
    tickRef.current = null;
    capRef.current = null;
  }, []);

  /** THE thing that must never be skipped: a live microphone left open. */
  const releaseMic = useCallback(() => {
    streamRef.current?.getTracks?.().forEach((track) => track.stop?.());
    streamRef.current = null;
  }, []);

  const teardown = useCallback(() => {
    recorderRef.current = null;
    chunksRef.current = [];
    clearTimers();
    releaseMic();
    setRecording(false);
    setSeconds(0);
  }, [clearTimers, releaseMic]);

  const start = useCallback(async (): Promise<string | null> => {
    if (recorderRef.current) return null;
    const mime = pickVoiceMimeType();
    if (!mime || typeof navigator?.mediaDevices?.getUserMedia !== 'function') {
      setSupported(false);
      return NOT_SUPPORTED;
    }
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setBlocked(BLOCKED);
      return BLOCKED;
    }
    if (unmountedRef.current) {
      stream.getTracks?.().forEach((track) => track.stop?.());
      return null;
    }
    streamRef.current = stream;
    cancelledRef.current = false;
    chunksRef.current = [];
    let recorder: MediaRecorder;
    try {
      recorder = new MediaRecorder(stream, { mimeType: mime });
    } catch {
      releaseMic();
      setSupported(false);
      return NOT_SUPPORTED;
    }
    recorderRef.current = recorder;
    recorder.ondataavailable = (event: BlobEvent) => {
      if (event.data?.size) chunksRef.current.push(event.data);
    };
    recorder.onstop = () => {
      const chunks = chunksRef.current;
      const cancelled = cancelledRef.current;
      teardown();
      if (cancelled || chunks.length === 0) return;
      const blob = new Blob(chunks, { type: mime });
      onClipRef.current(new File([blob], voiceFileName(mime), { type: mime }));
    };
    recorder.start();
    setBlocked(null);
    setRecording(true);
    setSeconds(0);
    tickRef.current = window.setInterval(() => setSeconds((value) => value + 1), 1000);
    capRef.current = window.setTimeout(() => {
      // Cap reached: stop and KEEP the clip - the two minutes recorded are the
      // message, throwing them away would be the surprise.
      try {
        recorderRef.current?.stop?.();
      } catch {
        teardown();
      }
    }, maxDurationMs);
    return null;
  }, [maxDurationMs, releaseMic, teardown]);

  const finish = useCallback(
    (cancelled: boolean) => {
      if (!recorderRef.current) return;
      cancelledRef.current = cancelled;
      try {
        recorderRef.current.stop?.();
      } catch {
        // A recorder that refuses to stop must still not hold the microphone.
        teardown();
      }
    },
    [teardown],
  );

  const stop = useCallback(() => finish(false), [finish]);
  const cancel = useCallback(() => finish(true), [finish]);

  // Unmount mid-recording (the drawer closes, the ticket changes): drop the clip
  // and release the microphone.
  useEffect(
    () => () => {
      unmountedRef.current = true;
      cancelledRef.current = true;
      try {
        recorderRef.current?.stop?.();
      } catch {
        // ignored - the release below is what matters
      }
      recorderRef.current = null;
      chunksRef.current = [];
      clearTimers();
      releaseMic();
    },
    [clearTimers, releaseMic],
  );

  return {
    available: supported && !blocked,
    reason: !supported ? NOT_SUPPORTED : blocked,
    recording,
    seconds,
    start,
    stop,
    cancel,
  };
}
