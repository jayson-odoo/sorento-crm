'use client';

import { useLayoutEffect, useMemo, useRef, type MutableRefObject } from 'react';
import ReactQuill from 'react-quill-new';
import { cn } from '@/lib/utils';
import type Quill from 'quill';
import 'react-quill-new/dist/quill.snow.css';

export const QUOTATION_QUILL_MODULES = {
  toolbar: [
    [{ header: [2, 3, false] }],
    ['bold', 'italic', 'underline', 'strike'],
    [{ list: 'ordered' }, { list: 'bullet' }],
    ['link'],
    ['clean'],
  ],
};

const DEFAULT_MODULES = QUOTATION_QUILL_MODULES;

export interface QuotationReactQuillProps {
  value: string;
  onChange: (html: string) => void;
  placeholder?: string;
  className?: string;
  /** Min height for editor content area */
  minHeightPx?: number;
  /**
   * When true, `modules` replaces the default toolbar config entirely.
   * When false/omitted, `modules` is shallow-merged over the default modules.
   */
  replaceModules?: boolean;
  /** Optional Quill modules (keyboard, clipboard, etc.). See `replaceModules`. */
  modules?: Record<string, unknown>;
  /** Filled with the Quill instance once the editor mounts (client-only). */
  quillInstanceRef?: MutableRefObject<Quill | null>;
  readOnly?: boolean;
}

export function QuotationReactQuill({
  value,
  onChange,
  placeholder = 'Type…',
  className,
  minHeightPx = 160,
  replaceModules,
  modules: modulesProp,
  quillInstanceRef,
  readOnly,
}: QuotationReactQuillProps) {
  const innerRef = useRef<InstanceType<typeof ReactQuill> | null>(null);
  const modules = useMemo(() => {
    if (replaceModules && modulesProp) return modulesProp;
    if (modulesProp) return { ...DEFAULT_MODULES, ...modulesProp };
    return DEFAULT_MODULES;
  }, [replaceModules, modulesProp]);

  useLayoutEffect(() => {
    if (!quillInstanceRef) return;
    try {
      const instance = innerRef.current;
      if (instance && typeof instance.getEditor === 'function') {
        quillInstanceRef.current = instance.getEditor();
      }
    } catch {
      /* editor not mounted yet */
    }
    return () => {
      quillInstanceRef.current = null;
    };
  }, [quillInstanceRef, modules]);

  return (
    <div
      className={cn(
        'quotation-quill rounded-[14px] border border-[#d1d5dc] bg-white [&_.ql-container]:rounded-b-[14px] [&_.ql-toolbar]:rounded-t-[14px] [&_.ql-toolbar]:border-[#d1d5dc] [&_.ql-editor]:min-h-[length:var(--qe-min)] [&_.ql-editor.ql-blank:before]:text-[rgba(10,10,10,0.45)] [&_.ql-editor.ql-blank:before]:not-italic',
        className,
      )}
      style={{ ['--qe-min' as string]: `${minHeightPx}px` } as React.CSSProperties}
    >
      <ReactQuill
        ref={innerRef}
        theme="snow"
        value={value || ''}
        onChange={onChange}
        modules={modules}
        placeholder={placeholder}
        readOnly={readOnly}
      />
    </div>
  );
}
