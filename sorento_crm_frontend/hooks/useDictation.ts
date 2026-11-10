'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from '@/lib/toast';

type Lang = 'en-US' | 'ms-MY';

interface RecognitionResult {
  isFinal: boolean;
  0: { transcript: string };
}
interface RecognitionEvent {
  resultIndex: number;
  results: ArrayLike<RecognitionResult>;
}
interface Recognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((e: RecognitionEvent) => void) | null;
  onerror: ((e: { error?: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
}
type RecognitionCtor = new () => Recognition;

const IDLE_STOP_MS = 60_000;

function recognitionCtor(): RecognitionCtor | null {
  if (typeof window === 'undefined') return null;
  const w = window as unknown as {
    SpeechRecognition?: RecognitionCtor;
    webkitSpeechRecognition?: RecognitionCtor;
  };
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

export function useDictation({ lang, onFinal }: { lang: Lang; onFinal: (text: string) => void }) {
  // Lazy, not an effect: a same-value setState on mount costs the host an extra render pass.
  const [supported] = useState(() => recognitionCtor() !== null);
  const [listening, setListening] = useState(false);
  const recRef = useRef<Recognition | null>(null);
  const idleRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onFinalRef = useRef(onFinal);
  onFinalRef.current = onFinal;

  const clearIdle = () => {
    if (idleRef.current) clearTimeout(idleRef.current);
    idleRef.current = null;
  };

  const stop = useCallback(() => {
    clearIdle();
    recRef.current?.stop();
  }, []);

  const armIdle = useCallback(() => {
    clearIdle();
    idleRef.current = setTimeout(() => recRef.current?.stop(), IDLE_STOP_MS);
  }, []);

  const toggle = useCallback(() => {
    if (recRef.current) {
      stop();
      return;
    }
    const Ctor = recognitionCtor();
    if (!Ctor) return;
    const rec = new Ctor();
    rec.lang = lang;
    rec.continuous = true;
    rec.interimResults = true;
    rec.onresult = (e) => {
      armIdle();
      for (let i = e.resultIndex; i < e.results.length; i += 1) {
        const res = e.results[i];
        if (res.isFinal) {
          const text = res[0].transcript.trim();
          if (text) onFinalRef.current(text);
        }
      }
    };
    rec.onerror = (e) => {
      if (e.error === 'not-allowed') toast.error('Allow the microphone for this site');
    };
    rec.onend = () => {
      clearIdle();
      recRef.current = null;
      setListening(false);
    };
    recRef.current = rec;
    try {
      rec.start();
      setListening(true);
      armIdle();
    } catch {
      recRef.current = null;
    }
  }, [armIdle, lang, stop]);

  useEffect(
    () => () => {
      clearIdle();
      const rec = recRef.current;
      if (rec) {
        rec.onend = null;
        rec.stop();
        recRef.current = null;
      }
    },
    [],
  );

  return { supported, listening, toggle, stop };
}
