'use client';

import { createContext, useContext } from 'react';
import type { ReportParamValues } from '@/services/reportService';

/** The params the report is running with, for the strip a screen passes as `belowHeader` (a link that carries the filters). */
export const ReportParamsContext = createContext<ReportParamValues>({});

export const useReportRunParams = () => useContext(ReportParamsContext);
