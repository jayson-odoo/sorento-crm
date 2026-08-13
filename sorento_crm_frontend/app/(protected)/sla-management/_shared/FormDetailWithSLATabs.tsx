'use client';

import { ReactNode } from 'react';
import { FileText, Timer } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import FormSLATrackingTab from './FormSLATrackingTab';
import type { FormSLASourceType } from './formSLAService';

export interface FormDetailExtraTab {
  value: string;
  label: string;
  content: ReactNode;
  /**
   * Bare lucide icon for the trigger (no size class - the `line` variant sizes
   * it). Optional so a caller that has nothing meaningful to draw renders a
   * label-only trigger rather than a filler icon.
   */
  icon?: ReactNode;
}

interface FormDetailWithSLATabsProps {
  sourceEntityType: FormSLASourceType;
  sourceEntityId: string;
  children: ReactNode;
  /** Entity-specific tabs inserted between "Details" and "SLA Tracking". */
  extraTabs?: FormDetailExtraTab[];
}

export default function FormDetailWithSLATabs({
  sourceEntityType,
  sourceEntityId,
  children,
  extraTabs = [],
}: FormDetailWithSLATabsProps) {
  return (
    <Tabs defaultValue="details">
      {/* The house underlined strip (same as the product/user detail pages), so
          every record in the system wears one tab style. The list carries its
          own bottom margin, so the root drops space-y. */}
      <TabsList variant="line" className="mb-5 w-full justify-start overflow-x-auto">
        <TabsTrigger value="details">
          <FileText />
          <span>Details</span>
        </TabsTrigger>
        {extraTabs.map((tab) => (
          <TabsTrigger key={tab.value} value={tab.value}>
            {tab.icon}
            <span>{tab.label}</span>
          </TabsTrigger>
        ))}
        <TabsTrigger value="sla">
          <Timer />
          <span>SLA Tracking</span>
        </TabsTrigger>
      </TabsList>
      <TabsContent value="details" className="m-0">
        {children}
      </TabsContent>
      {extraTabs.map((tab) => (
        <TabsContent key={tab.value} value={tab.value} className="m-0">
          {tab.content}
        </TabsContent>
      ))}
      <TabsContent value="sla" className="m-0">
        <FormSLATrackingTab
          sourceEntityType={sourceEntityType}
          sourceEntityId={sourceEntityId}
        />
      </TabsContent>
    </Tabs>
  );
}
