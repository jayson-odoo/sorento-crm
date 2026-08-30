import { ReactNode } from 'react';
import { cn } from '@/lib/utils';

export interface ToolbarActionsProps {
  children?: ReactNode;
}

export interface ToolbarProps {
  children?: ReactNode;
}

export interface ToolbarHeadingProps {
  className?: string;
  children: ReactNode;
}

export const Toolbar = ({ children }: ToolbarProps) => {
  return (
    <div
      data-slot="toolbar"
      className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between grow pb-5"
    >
      {children}
    </div>
  );
};

export const ToolbarHeading = ({
  children,
  className,
}: ToolbarHeadingProps) => {
  return (
    <div
      data-slot="toolbar-heading"
      className={cn('flex flex-col flex-wrap gap-px', className)}
    >
      {children}
    </div>
  );
};

export const ToolbarActions = ({ children }: ToolbarActionsProps) => {
  return (
    <div
      data-slot="toolbar-actions"
      className="flex items-center flex-wrap gap-1.5 lg:gap-3.5"
    >
      {children}
    </div>
  );
};
