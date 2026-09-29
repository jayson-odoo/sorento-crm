'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { getEmailTheme, previewEmailTheme, saveEmailTheme } from '../services/emailThemeService';
import type { EmailTheme, EmailThemeResponse, EmailThemeSampleCode } from '../types/emailTheme.types';

const EMAIL_THEME_KEY = ['email-theme'];

export function useEmailThemeQuery() {
  return useQuery({
    queryKey: EMAIL_THEME_KEY,
    queryFn: getEmailTheme,
  });
}

export function useSaveEmailThemeMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (theme: EmailTheme) => saveEmailTheme(theme),
    onSuccess: (data: EmailThemeResponse) => {
      qc.setQueryData(EMAIL_THEME_KEY, data);
      toast.success('Email theme saved');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to save email theme');
    },
  });
}

/** Live preview (AC-EM030): renders one credential sample mail under the UNSAVED form values. */
export function useEmailThemePreview() {
  return useMutation({
    mutationFn: ({ theme, code }: { theme: EmailTheme; code: EmailThemeSampleCode }) =>
      previewEmailTheme(theme, code),
  });
}
