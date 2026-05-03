'use client';

import { useQuery } from '@tanstack/react-query';
import {
  getQueryDetail,
  getRecentQueries,
  getTopContacts,
  getTopUsers,
  getUsageByDay,
  getUsageSummary,
  getWishlist,
} from '../services/aiUsageService';

const isoOrUndef = (d: Date | undefined) => (d ? d.toISOString() : undefined);

export function useUsageSummary(from?: Date, to?: Date, feature?: string) {
  return useQuery({
    queryKey: ['ai-usage-summary', isoOrUndef(from), isoOrUndef(to), feature ?? null],
    queryFn: () => getUsageSummary(from, to, feature),
    staleTime: 30 * 1000,
  });
}

export function useUsageByDay(from?: Date, to?: Date, feature?: string) {
  return useQuery({
    queryKey: ['ai-usage-by-day', isoOrUndef(from), isoOrUndef(to), feature ?? null],
    queryFn: () => getUsageByDay(from, to, feature),
    staleTime: 30 * 1000,
  });
}

export function useTopUsers(from?: Date, to?: Date, limit = 10, feature?: string) {
  return useQuery({
    queryKey: ['ai-usage-top-users', isoOrUndef(from), isoOrUndef(to), limit, feature ?? null],
    queryFn: () => getTopUsers(from, to, limit, feature),
    staleTime: 30 * 1000,
  });
}

export function useTopContacts(
  from?: Date,
  to?: Date,
  limit = 10,
  feature: string = 'ai_extract',
) {
  return useQuery({
    queryKey: ['ai-usage-top-contacts', isoOrUndef(from), isoOrUndef(to), limit, feature],
    queryFn: () => getTopContacts(from, to, limit, feature),
    staleTime: 30 * 1000,
  });
}

export function useRecentQueries(from?: Date, to?: Date, limit = 50, feature?: string) {
  return useQuery({
    queryKey: ['ai-usage-recent', isoOrUndef(from), isoOrUndef(to), limit, feature ?? null],
    queryFn: () => getRecentQueries(from, to, limit, feature),
    staleTime: 30 * 1000,
  });
}

export function useQueryDetail(messageId: string | null | undefined) {
  return useQuery({
    queryKey: ['ai-usage-query-detail', messageId],
    queryFn: () => getQueryDetail(messageId as string),
    enabled: !!messageId,
    staleTime: 5 * 60 * 1000,
  });
}

export function useWishlist(limit = 20) {
  return useQuery({
    queryKey: ['ai-wishlist', limit],
    queryFn: () => getWishlist(limit),
    staleTime: 60 * 1000,
  });
}
