'use client';

import { useCallback, useEffect, useMemo, useState, type MouseEvent as ReactMouseEvent } from 'react';
import { useSession } from 'next-auth/react';
import { useQuery } from '@tanstack/react-query';
import {
  Check,
  ChevronDown,
  GripVertical,
  Info,
  LayoutGrid,
  LayoutList,
  Pencil,
  Plus,
  Trash2,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command';
import { apiFetch } from '@/lib/api';
import { cn } from '@/lib/utils';
import { getWorkflowStages } from '@/app/(protected)/commercial-core/process-configuration/services/workflowStageService';
import type {
  CommercialProjectTaskBoard,
  CommercialProjectTaskBoardTask,
} from '@/app/(protected)/commercial-management/projects/types/commercialProject.types';
import { TaskActivitiesButton } from './TaskActivitiesButton';

type UserSelectRow = { id: string; name: string | null; email: string };
type ActivityTaskStatusRow = { id: string; code: string; label: string; color_hex: string | null };
type TaskCategoryRow = { code: string; label: string; sort_order: number; is_active: boolean };

const COL_DEFAULTS: Record<string, number> = {
  status: 148,
  title: 220,
  assignee: 152,
  timeline: 280,
  actions: 96,
};

function colStorageKey(storageKey: string) {
  return `commercial-entity-task-cols:${storageKey}`;
}

function loadColWidths(storageKey: string): Record<string, number> {
  if (typeof window === 'undefined') return { ...COL_DEFAULTS };
  try {
    const raw = localStorage.getItem(colStorageKey(storageKey));
    if (!raw) return { ...COL_DEFAULTS };
    return { ...COL_DEFAULTS, ...JSON.parse(raw) };
  } catch {
    return { ...COL_DEFAULTS };
  }
}

function saveColWidths(storageKey: string, w: Record<string, number>) {
  try {
    localStorage.setItem(colStorageKey(storageKey), JSON.stringify(w));
  } catch {
    /* ignore */
  }
}

function isTaskDoneCode(statusCode: string | null | undefined): boolean {
  const c = (statusCode || '').toLowerCase();
  return c.includes('done') || c.includes('complete') || c === 'closed';
}

function hexToRgba(hex: string, alpha: number): string {
  const normalized = hex.replace('#', '');
  if (!/^[0-9a-fA-F]{6}$/.test(normalized)) return `rgba(231, 0, 11, ${alpha})`;
  const intVal = Number.parseInt(normalized, 16);
  const r = (intVal >> 16) & 255;
  const g = (intVal >> 8) & 255;
  const b = intVal & 255;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

type TaskBoardSection = {
  key: string;
  label: string;
  categoryCode: string | null;
  rows: CommercialProjectTaskBoardTask[];
};

type TaskRowView = {
  task: CommercialProjectTaskBoardTask;
  depth: 0 | 1;
  parentId: string | null;
};

export type CommercialEntityTaskBoardProps = {
  storageKey: string;
  taskBoard: CommercialProjectTaskBoard;
  onPersist: (next: CommercialProjectTaskBoard) => void;
  canEdit: boolean;
  tasksGroupLabel: string;
  boardTitle?: string;
  className?: string;
  /** When set, each task row shows task-scoped activities (separate from document-level feeds). */
  activitiesParent?:
    | { variant: 'project'; parentId: string }
    | { variant: 'master_quotation'; parentId: string };
  scheduleBaselineStartDate?: string | null;
  onPreviewSchedule?: (body: {
    task_board: Record<string, unknown>;
    baseline_start_date?: string | null;
    changed_task_id?: string | null;
  }) => Promise<{ task_board: Record<string, unknown>; impacts: Array<Record<string, unknown>> }>;
  onApplySchedule?: (body: {
    task_board: Record<string, unknown>;
    baseline_start_date?: string | null;
    changed_task_id?: string | null;
  }) => Promise<{ task_board: Record<string, unknown>; impacts: Array<Record<string, unknown>> }>;
};

function TaskTitleInline({
  title,
  disabled,
  onCommit,
}: {
  title: string;
  disabled: boolean;
  onCommit: (next: string) => void;
}) {
  const [value, setValue] = useState(title);
  useEffect(() => {
    setValue(title);
  }, [title]);
  if (disabled) {
    return <span className="line-clamp-2 text-sm font-medium text-[#101828]">{title.trim() ? title : '—'}</span>;
  }
  return (
    <Input
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onBlur={() => {
        const t = value.trim();
        if (t && t !== title.trim()) onCommit(t);
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          (e.target as HTMLInputElement).blur();
        }
      }}
      className="focus-visible:border-input h-auto min-h-8 border-transparent bg-transparent px-1 py-1 text-sm font-medium text-[#101828] shadow-none focus-visible:ring-0"
      aria-label="Task name"
    />
  );
}

function TaskDescriptionPopover({
  taskId,
  description,
  canEdit,
  onSaveDescription,
}: {
  taskId: string;
  description: string | null | undefined;
  canEdit: boolean;
  onSaveDescription: (next: string | null) => void;
}) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="size-8 shrink-0 text-[#6a7282]"
          aria-label="Task description"
          onClick={(e) => e.stopPropagation()}
        >
          <Info className="size-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80" align="start" onClick={(e) => e.stopPropagation()}>
        <Label className="text-xs">Description</Label>
        <Textarea
          key={taskId}
          className="mt-1"
          rows={4}
          defaultValue={(description as string) || ''}
          readOnly={!canEdit}
          onBlur={(e) => {
            if (!canEdit) return;
            const v = e.target.value.trim();
            onSaveDescription(v || null);
          }}
        />
      </PopoverContent>
    </Popover>
  );
}

export function CommercialEntityTaskBoard({
  storageKey,
  taskBoard: boardProp,
  onPersist,
  canEdit,
  tasksGroupLabel,
  boardTitle = 'Task Board',
  className,
  activitiesParent,
  scheduleBaselineStartDate,
  onPreviewSchedule,
  onApplySchedule,
}: CommercialEntityTaskBoardProps) {
  const { data: session } = useSession();
  const sessionUserId = session?.user?.id;
  const board = useMemo(
    () => (boardProp && typeof boardProp === 'object' ? boardProp : { tasks: [] }),
    [boardProp],
  );
  const normalizedTasks = useMemo<CommercialProjectTaskBoardTask[]>(
    () =>
      (board.tasks ?? []).map((t) => ({
        ...t,
        parent_task_id: t.parent_task_id ?? null,
        lead_time_days: Math.max(1, Number(t.lead_time_days || 1)),
        dependency_task_ids: Array.isArray(t.dependency_task_ids) ? t.dependency_task_ids.map(String) : [],
      })),
    [board.tasks],
  );

  const [taskSectionExpanded, setTaskSectionExpanded] = useState<Record<string, boolean>>({});
  const [tasksScope, setTasksScope] = useState<'my' | 'all'>('all');
  const [tasksLayout, setTasksLayout] = useState<'list' | 'kanban'>('list');
  const [taskSearchQuery, setTaskSearchQuery] = useState('');
  const [filterStartDate, setFilterStartDate] = useState('');
  const [filterEndDate, setFilterEndDate] = useState('');
  const [colWidths, setColWidths] = useState<Record<string, number>>(() => loadColWidths(storageKey));
  const [taskDialogOpen, setTaskDialogOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<CommercialProjectTaskBoardTask | null>(null);
  const [draggingTaskId, setDraggingTaskId] = useState<string | null>(null);
  const [dragOverSectionKey, setDragOverSectionKey] = useState<string | null>(null);
  const [taskForm, setTaskForm] = useState({
    title: '',
    description: '',
    category: '',
    category_code: '',
    parent_task_id: '' as string | '',
    assignee_user_id: '',
    sort_order: 0,
    status_code: '',
    lead_time_days: 1,
    dependency_task_ids: [] as string[],
  });
  const [schedulePreviewOpen, setSchedulePreviewOpen] = useState(false);
  const [schedulePreviewPending, setSchedulePreviewPending] = useState(false);
  const [scheduleApplyPending, setScheduleApplyPending] = useState(false);
  const [schedulePreviewImpacts, setSchedulePreviewImpacts] = useState<
    Array<{
      task_id: string;
      title: string;
      old_start_date?: string | null;
      old_end_date?: string | null;
      new_start_date?: string | null;
      new_end_date?: string | null;
    }>
  >([]);
  const [schedulePreviewBoard, setSchedulePreviewBoard] = useState<Record<string, unknown> | null>(null);
  const [dependencyPickerOpen, setDependencyPickerOpen] = useState(false);
  const [lastChangedTaskId, setLastChangedTaskId] = useState<string | null>(null);
  const taskById = useMemo(() => {
    const map = new Map<string, CommercialProjectTaskBoardTask>();
    for (const t of normalizedTasks) map.set(t.id, t);
    return map;
  }, [normalizedTasks]);

  const { data: usersSelect = [] } = useQuery({
    queryKey: ['user-select-entity-task-board'],
    queryFn: async () => {
      const r = await apiFetch('/api/user-management/users/select');
      if (!r.ok) return [];
      return (await r.json()) as UserSelectRow[];
    },
    staleTime: 60_000,
  });

  const { data: taskStatuses = [] } = useQuery({
    queryKey: ['workflow-stages', 'task'],
    queryFn: async () => {
      const rows = await getWorkflowStages({ domain: 'task' });
      return rows
        .filter((row) => row.is_active)
        .sort((a, b) => a.sort_order - b.sort_order || a.code.localeCompare(b.code))
        .map((row) => ({
          id: row.id,
          code: row.code,
          label: row.label,
          color_hex: row.color_hex,
        })) as ActivityTaskStatusRow[];
    },
    staleTime: 60_000,
  });

  const { data: taskCategories = [] } = useQuery({
    queryKey: ['commercial-task-categories'],
    queryFn: async () => {
      const r = await apiFetch('/api/v1/commercial-activity/task-categories');
      if (!r.ok) return [];
      return (await r.json()) as TaskCategoryRow[];
    },
    staleTime: 60_000,
  });

  useEffect(() => {
    setColWidths(loadColWidths(storageKey));
  }, [storageKey]);

  useEffect(() => {
    saveColWidths(storageKey, colWidths);
  }, [storageKey, colWidths]);

  const myTaskSection = useMemo((): TaskBoardSection | null => {
    const tasks = [...normalizedTasks].sort(
      (a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || (a.title || '').localeCompare(b.title || ''),
    );
    const uid = sessionUserId;
    const mine = uid ? tasks.filter((t) => t.assignee_user_id === uid) : [];
    if (!uid) return null;
    return {
      key: '__my_tasks',
      label: 'My tasks',
      categoryCode: null,
      rows: mine,
    };
  }, [normalizedTasks, sessionUserId]);

  const categorySections = useMemo((): TaskBoardSection[] => {
    const tasks = [...normalizedTasks].sort(
      (a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || (a.title || '').localeCompare(b.title || ''),
    );

    const byKey = new Map<string, CommercialProjectTaskBoardTask[]>();
    const keyMeta = new Map<string, { label: string; code: string | null }>();

    for (const t of tasks) {
      const code = (t.category_code || '').trim() || null;
      const labelFromMaster = code ? taskCategories.find((c) => c.code === code)?.label : null;
      const label = (labelFromMaster || (t.category || '').trim() || 'General') as string;
      const key = code || `__lbl:${label}`;
      if (!byKey.has(key)) {
        byKey.set(key, []);
        keyMeta.set(key, { label, code });
      }
      byKey.get(key)!.push(t);
    }

    const catSections: TaskBoardSection[] = Array.from(byKey.entries())
      .map(([key, rows]) => {
        const m = keyMeta.get(key)!;
        return { key, label: m.label, categoryCode: m.code, rows };
      })
      .sort((a, b) => a.label.localeCompare(b.label));
    return catSections;
  }, [normalizedTasks, taskCategories]);
  const displayTaskSections = useMemo(() => {
    if (tasksScope === 'my') {
      return myTaskSection ? [myTaskSection] : [];
    }
    return myTaskSection ? [myTaskSection, ...categorySections] : categorySections;
  }, [categorySections, myTaskSection, tasksScope]);

  const userNameMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const u of usersSelect) {
      m.set(u.id, (u.name || '').trim() || u.email || '');
    }
    return m;
  }, [usersSelect]);

  const statusLabelMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const s of taskStatuses) {
      m.set(s.code, s.label);
    }
    return m;
  }, [taskStatuses]);
  const statusColorMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const s of taskStatuses) {
      if (s.color_hex) m.set(s.code, s.color_hex);
    }
    return m;
  }, [taskStatuses]);

  const filteredTaskSections = useMemo(() => {
    const q = taskSearchQuery.trim().toLowerCase();
    const hasStart = !!filterStartDate;
    const hasEnd = !!filterEndDate;

    const passes = (t: CommercialProjectTaskBoardTask) => {
      const textBlob = [
        (t.title || '').toLowerCase(),
        (userNameMap.get(t.assignee_user_id || '') || '').toLowerCase(),
        (statusLabelMap.get(t.status_code || '') || '').toLowerCase(),
        (t.status_code || '').toLowerCase(),
      ].join(' ');
      if (q && !textBlob.includes(q)) return false;

      const taskStart = t.start_date ? String(t.start_date).slice(0, 10) : '';
      const taskEnd = t.end_date ? String(t.end_date).slice(0, 10) : '';
      if (hasStart && (!taskStart || taskStart < filterStartDate)) return false;
      if (hasEnd && (!taskEnd || taskEnd > filterEndDate)) return false;
      return true;
    };

    return displayTaskSections
      .map((section) => ({ ...section, rows: section.rows.filter(passes) }))
      .filter((section) => section.rows.length > 0);
  }, [displayTaskSections, filterEndDate, filterStartDate, statusLabelMap, taskSearchQuery, userNameMap]);
  const sectionRowViews = useMemo(() => {
    const toRows = (section: TaskBoardSection): TaskRowView[] => {
      const rows = [...section.rows].sort(
        (a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || (a.title || '').localeCompare(b.title || ''),
      );
      const top = rows.filter((r) => !r.parent_task_id);
      const byParent = new Map<string, CommercialProjectTaskBoardTask[]>();
      for (const r of rows) {
        if (!r.parent_task_id) continue;
        const parentList = byParent.get(r.parent_task_id) ?? [];
        parentList.push(r);
        byParent.set(r.parent_task_id, parentList);
      }
      const out: TaskRowView[] = [];
      for (const t of top) {
        out.push({ task: t, depth: 0, parentId: null });
        const children = (byParent.get(t.id) ?? []).sort(
          (a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || (a.title || '').localeCompare(b.title || ''),
        );
        for (const c of children) out.push({ task: c, depth: 1, parentId: t.id });
      }
      return out;
    };
    const map = new Map<string, TaskRowView[]>();
    for (const section of filteredTaskSections) {
      map.set(section.key, toRows(section));
    }
    return map;
  }, [filteredTaskSections]);
  const openNewTask = (
    categoryLabel?: string,
    categoryCode?: string | null,
    assigneeUserId?: string,
    parentTaskId?: string | null,
  ) => {
    if (!canEdit) return;
    setEditingTask(null);
    const defaultStatus = taskStatuses.find((s) => s.code === 'not_started')?.code || taskStatuses[0]?.code || '';
    const firstActive = taskCategories.find((c) => c.is_active) ?? taskCategories[0];
    const initCode =
      categoryCode ?? (firstActive?.code ?? '');
    const initLabel =
      categoryLabel ??
      (initCode ? taskCategories.find((c) => c.code === initCode)?.label ?? '' : '');
    setTaskForm({
      title: '',
      description: '',
      category: initLabel || firstActive?.label || '',
      category_code: initCode,
      parent_task_id: parentTaskId || '',
      assignee_user_id: assigneeUserId ?? '',
      sort_order: normalizedTasks.length,
      status_code: defaultStatus,
      lead_time_days: 1,
      dependency_task_ids: [],
    });
    setTaskDialogOpen(true);
  };
  const openEditTask = (t: CommercialProjectTaskBoardTask) => {
    if (!canEdit) return;
    setEditingTask(t);
    setTaskForm({
      title: t.title,
      description: (t.description as string) ?? '',
      category: t.category ?? '',
      category_code: (t.category_code as string) ?? '',
      parent_task_id: t.parent_task_id ?? '',
      assignee_user_id: t.assignee_user_id ?? '',
      sort_order: t.sort_order ?? 0,
      status_code: t.status_code ?? '',
      lead_time_days: Math.max(1, Number(t.lead_time_days || 1)),
      dependency_task_ids: Array.isArray(t.dependency_task_ids) ? t.dependency_task_ids.map(String) : [],
    });
    setTaskDialogOpen(true);
  };
  const submitTaskDialog = () => {
    if (!canEdit || !taskForm.title.trim()) return;
    const tasks = [...normalizedTasks];
    const selectedCode = (taskForm.category_code || '').trim() || null;
    const parentTask = taskForm.parent_task_id ? taskById.get(taskForm.parent_task_id) ?? null : null;
    const code = parentTask ? (parentTask.category_code ?? null) : selectedCode;
    const catLabel = code
      ? taskCategories.find((c) => c.code === code)?.label || parentTask?.category?.trim() || taskForm.category.trim() || code
      : parentTask?.category?.trim() || taskForm.category.trim() || 'General';
    const assignee = (taskForm.assignee_user_id || '').trim() || null;
    if (editingTask) {
      const idx = tasks.findIndex((x) => x.id === editingTask.id);
      if (idx >= 0) {
        tasks[idx] = {
          ...tasks[idx],
          title: taskForm.title.trim(),
          description: taskForm.description.trim() || null,
          category: catLabel,
          category_code: code,
          parent_task_id: taskForm.parent_task_id || null,
          assignee_user_id: assignee,
          sort_order: taskForm.sort_order,
          status_code: taskForm.status_code || tasks[idx].status_code,
          lead_time_days: Math.max(1, Number(taskForm.lead_time_days || 1)),
      dependency_task_ids: taskForm.dependency_task_ids.filter((depId) => depId !== editingTask.id),
          is_service_task: false,
        };
        setLastChangedTaskId(editingTask.id);
      }
    } else {
      const id =
        typeof crypto !== 'undefined' && crypto.randomUUID
          ? crypto.randomUUID()
          : `task-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      tasks.push({
        id,
        title: taskForm.title.trim(),
        description: taskForm.description.trim() || null,
        category: catLabel,
        category_code: code,
        parent_task_id: taskForm.parent_task_id || null,
        assignee_user_id: assignee ?? undefined,
        sort_order: taskForm.sort_order,
        status_code: taskForm.status_code || undefined,
        lead_time_days: Math.max(1, Number(taskForm.lead_time_days || 1)),
        dependency_task_ids: taskForm.dependency_task_ids,
        is_service_task: false,
      });
      setLastChangedTaskId(id);
    }
    onPersist({ ...board, tasks });
    setTaskDialogOpen(false);
  };
  const deleteTask = (id: string) => {
    if (!canEdit) return;
    const tasks = normalizedTasks.filter((t) => t.id !== id);
    onPersist({ ...board, tasks });
  };
  const patchTask = useCallback(
    (taskId: string, patch: Partial<CommercialProjectTaskBoardTask>) => {
      if (!canEdit) return;
      const tasks = [...normalizedTasks];
      const idx = tasks.findIndex((x) => x.id === taskId);
      if (idx < 0) return;
      tasks[idx] = { ...tasks[idx]!, ...patch };
      setLastChangedTaskId(taskId);
      onPersist({ ...board, tasks });
    },
    [normalizedTasks, board, onPersist, canEdit],
  );
  const taskSectionOpen = (key: string) => taskSectionExpanded[key] !== false;

  const expandAllTaskSections = () => {
    const next: Record<string, boolean> = {};
    for (const s of displayTaskSections) next[s.key] = true;
    setTaskSectionExpanded(next);
  };

  const collapseAllTaskSections = () => {
    const next: Record<string, boolean> = {};
    for (const s of displayTaskSections) next[s.key] = false;
    setTaskSectionExpanded(next);
  };

  const toggleTaskSection = (key: string) => {
    setTaskSectionExpanded((prev) => {
      const cur = prev[key] !== false;
      return { ...prev, [key]: !cur };
    });
  };
  const moveTaskToSection = (
    taskId: string,
    targetSectionKey: string,
    overTaskId?: string | null,
    targetParentTaskId?: string | null,
  ) => {
    if (!canEdit || tasksScope !== 'all') return;
    const targetSection = categorySections.find((s) => s.key === targetSectionKey);
    if (!targetSection) return;

    const nextTasks = [...normalizedTasks];
    const movingIdx = nextTasks.findIndex((t) => t.id === taskId);
    if (movingIdx < 0) return;

    const movingTask = nextTasks[movingIdx]!;
    const sourceParentTaskId = movingTask.parent_task_id ?? null;
    const isMovingSubtask = !!sourceParentTaskId;
    if (!targetParentTaskId && isMovingSubtask) {
      // Do not allow subtask to become top-level via drag.
      return;
    }
    if (isMovingSubtask && targetParentTaskId !== sourceParentTaskId) {
      // One-level constraint: subtask can only be reordered among siblings.
      return;
    }
    const sourceCategoryCode = movingTask.category_code ? String(movingTask.category_code).trim() : null;
    const sourceCategoryLabel = (movingTask.category || '').trim();
    const isSameCategory =
      sourceCategoryCode != null
        ? sourceCategoryCode === (targetSection.categoryCode ? String(targetSection.categoryCode).trim() : null)
        : sourceCategoryLabel === targetSection.label;

    movingTask.category_code = targetSection.categoryCode ?? null;
    movingTask.category = targetSection.label;
    movingTask.parent_task_id = targetParentTaskId ?? null;

    const targetRows = nextTasks.filter(
      (t) =>
        ((targetSection.categoryCode && String(t.category_code || '').trim() === String(targetSection.categoryCode).trim()) ||
          (!targetSection.categoryCode && (t.category || '').trim() === targetSection.label)) &&
        (targetParentTaskId ? t.parent_task_id === targetParentTaskId : !t.parent_task_id),
    );
    const targetIds = targetRows.map((r) => r.id).filter((id) => id !== taskId);
    const overIdx = overTaskId ? targetIds.findIndex((id) => id === overTaskId) : -1;
    if (overIdx >= 0) targetIds.splice(overIdx, 0, taskId);
    else targetIds.push(taskId);

    const sourceIds = isSameCategory && sourceParentTaskId === (targetParentTaskId ?? null)
      ? []
      : nextTasks
          .filter(
            (t) =>
              t.id !== taskId &&
              ((sourceCategoryCode && String(t.category_code || '').trim() === sourceCategoryCode) ||
                (!sourceCategoryCode && (t.category || '').trim() === sourceCategoryLabel)) &&
              t.parent_task_id === (isMovingSubtask ? sourceParentTaskId : null),
          )
          .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))
          .map((t) => t.id);

    targetIds.forEach((id, idx) => {
      const task = nextTasks.find((t) => t.id === id);
      if (task) task.sort_order = idx;
    });
    if (sourceIds.length > 0) {
      sourceIds.forEach((id, idx) => {
        const task = nextTasks.find((t) => t.id === id);
        if (task) task.sort_order = idx;
      });
    }

    onPersist({ ...board, tasks: nextTasks });
  };
  const canSchedule = !!onPreviewSchedule && !!onApplySchedule;
  const runSchedulePreview = async () => {
    if (!canSchedule || !onPreviewSchedule) return;
    setSchedulePreviewPending(true);
    try {
      const payload = {
        task_board: { ...(board as Record<string, unknown>), tasks: normalizedTasks as unknown[] },
        baseline_start_date: scheduleBaselineStartDate || null,
        changed_task_id: lastChangedTaskId,
      };
      const out = await onPreviewSchedule(payload);
      setSchedulePreviewBoard(out.task_board);
      setSchedulePreviewImpacts(
        (out.impacts || []).map((i) => ({
          task_id: String(i.task_id || ''),
          title: String(i.title || 'Task'),
          old_start_date: (i.old_start_date as string | null | undefined) ?? null,
          old_end_date: (i.old_end_date as string | null | undefined) ?? null,
          new_start_date: (i.new_start_date as string | null | undefined) ?? null,
          new_end_date: (i.new_end_date as string | null | undefined) ?? null,
        })),
      );
      setSchedulePreviewOpen(true);
    } catch {
      // errors are surfaced by caller service
    } finally {
      setSchedulePreviewPending(false);
    }
  };
  const applySchedule = async () => {
    if (!canSchedule || !onApplySchedule || !schedulePreviewBoard) return;
    setScheduleApplyPending(true);
    try {
      const out = await onApplySchedule({
        task_board: schedulePreviewBoard,
        baseline_start_date: scheduleBaselineStartDate || null,
        changed_task_id: lastChangedTaskId,
      });
      onPersist(out.task_board as CommercialProjectTaskBoard);
      setSchedulePreviewOpen(false);
    } finally {
      setScheduleApplyPending(false);
    }
  };
  const canDragInList = canEdit && tasksScope === 'all';
  const startResize = (col: string, ev: ReactMouseEvent) => {
    ev.preventDefault();
    ev.stopPropagation();
    const startX = ev.clientX;
    const startW = colWidths[col] ?? COL_DEFAULTS[col] ?? 120;
    const onMove = (e: globalThis.MouseEvent) => {
      const dx = e.clientX - startX;
      setColWidths((prev) => ({ ...prev, [col]: Math.max(64, startW + dx) }));
    };
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };
  return (
    <>
      <div className={cn('w-full space-y-4', className)}>
        <div className="rounded-[10px] border border-[#e5e7eb] bg-white p-4 shadow-sm">
          <div className="flex flex-col gap-2 border-b border-[#e5e7eb] pb-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-base font-semibold text-[#101828]">{boardTitle}</h2>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-8 text-sm font-normal text-[#4a5565]"
                  onClick={expandAllTaskSections}
                >
                  Expand all
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-8 text-sm font-normal text-[#4a5565]"
                  onClick={collapseAllTaskSections}
                >
                  Collapse all
                </Button>
                <div className="inline-flex items-center rounded-lg border border-[#e5e7eb] p-0.5">
                  <Button
                    type="button"
                    size="sm"
                    className={cn(
                      'h-8 gap-1 px-2.5',
                      tasksLayout === 'list'
                        ? 'bg-[#030213] text-white hover:bg-[#030213] hover:text-white'
                        : 'bg-transparent font-normal text-[#4a5565] shadow-none hover:bg-transparent',
                    )}
                    onClick={() => setTasksLayout('list')}
                    aria-label="List view"
                  >
                    <LayoutList className="size-4" />
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    className={cn(
                      'h-8 gap-1 px-2.5',
                      tasksLayout === 'kanban'
                        ? 'bg-[#030213] text-white hover:bg-[#030213] hover:text-white'
                        : 'bg-transparent font-normal text-[#4a5565] shadow-none hover:bg-transparent',
                    )}
                    onClick={() => setTasksLayout('kanban')}
                    aria-label="Kanban view"
                  >
                    <LayoutGrid className="size-4" />
                  </Button>
                </div>
                <Button
                  type="button"
                  size="icon"
                  className="size-9 shrink-0 rounded-md bg-[#e7000b] text-white hover:bg-[#e7000b]/90"
                  onClick={() => openNewTask()}
                    aria-label="Add task"
                    disabled={!canEdit}
                  >
                  <Plus className="size-4" />
                </Button>
              </div>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
              <h3 className="text-sm font-semibold text-[#101828]">{tasksGroupLabel}</h3>
              <div className="flex flex-wrap items-center gap-2">
                <div className="inline-flex rounded-lg border border-[#fecaca] bg-[#fef2f2] p-0.5">
                  <Button
                    type="button"
                    size="sm"
                    className={cn(
                      'h-8 rounded-md px-3 text-sm font-medium',
                      tasksScope === 'my'
                        ? 'bg-[#e7000b] text-white shadow-none hover:bg-[#e7000b]/90'
                        : 'bg-white font-normal text-[#4a5565] shadow-none hover:bg-[#fafafa]',
                    )}
                    onClick={() => setTasksScope('my')}
                  >
                    My tasks
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    className={cn(
                      'h-8 rounded-md px-3 text-sm font-medium',
                      tasksScope === 'all'
                        ? 'bg-[#e7000b] text-white shadow-none hover:bg-[#e7000b]/90'
                        : 'bg-white font-normal text-[#4a5565] shadow-none hover:bg-[#fafafa]',
                    )}
                    onClick={() => setTasksScope('all')}
                  >
                    All tasks
                  </Button>
                </div>
                <Button type="button" variant="outline" size="sm" className="h-8" onClick={() => setColWidths({ ...COL_DEFAULTS })}>
                  Reset columns
                </Button>
              </div>
            </div>
            <div className="flex flex-wrap items-end gap-2 pt-1">
              <div className="min-w-[220px] flex-1">
                <Label className="mb-1 block text-xs text-[#6a7282]">Search</Label>
                <Input
                  value={taskSearchQuery}
                  onChange={(e) => setTaskSearchQuery(e.target.value)}
                  placeholder="Task, assignee, status..."
                  className="h-8"
                />
              </div>
              <div className="min-w-[150px]">
                <Label className="mb-1 block text-xs text-[#6a7282]">Start from</Label>
                <Input type="date" value={filterStartDate} onChange={(e) => setFilterStartDate(e.target.value)} className="h-8" />
              </div>
              <div className="min-w-[150px]">
                <Label className="mb-1 block text-xs text-[#6a7282]">End until</Label>
                <Input type="date" value={filterEndDate} onChange={(e) => setFilterEndDate(e.target.value)} className="h-8" />
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-8"
                onClick={() => {
                  setTaskSearchQuery('');
                  setFilterStartDate('');
                  setFilterEndDate('');
                }}
              >
                Clear
              </Button>
              {canSchedule ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-8"
                  disabled={!canEdit || schedulePreviewPending}
                  onClick={() => void runSchedulePreview()}
                >
                  Recalculate schedule
                </Button>
              ) : null}
            </div>
          </div>

          <div className="pt-4">
        {tasksLayout === 'kanban' ? (
          <div className="flex gap-3 overflow-x-auto pb-2">
            {taskStatuses.map((st) => {
              const tasksInCol = (board.tasks ?? []).filter((tk) => {
                const q = taskSearchQuery.trim().toLowerCase();
                const match = (tk.status_code || '') === st.code;
                if (!match) return false;
                if (tasksScope === 'my') return tk.assignee_user_id === sessionUserId;
                const textBlob = [
                  (tk.title || '').toLowerCase(),
                  (userNameMap.get(tk.assignee_user_id || '') || '').toLowerCase(),
                  (statusLabelMap.get(tk.status_code || '') || '').toLowerCase(),
                  (tk.status_code || '').toLowerCase(),
                ].join(' ');
                if (q && !textBlob.includes(q)) return false;
                const taskStart = tk.start_date ? String(tk.start_date).slice(0, 10) : '';
                const taskEnd = tk.end_date ? String(tk.end_date).slice(0, 10) : '';
                if (filterStartDate && (!taskStart || taskStart < filterStartDate)) return false;
                if (filterEndDate && (!taskEnd || taskEnd > filterEndDate)) return false;
                return true;
              });
              return (
                <div key={st.code} className="bg-background min-w-[260px] shrink-0 rounded-lg border p-2 shadow-sm">
                  <div className="mb-2 flex items-center justify-between gap-2 font-medium text-sm">
                    <span>{st.label}</span>
                    <Badge variant="secondary">{tasksInCol.length}</Badge>
                  </div>
                  <div className="space-y-2">
                    {tasksInCol.map((tk) => (
                      <Card
                        key={tk.id}
                        className={cn(
                          'border p-2 shadow-none',
                          tasksScope === 'my'
                            ? 'border-sky-200 bg-sky-50/70'
                            : 'border-red-200/80 bg-red-50/60',
                        )}
                      >
                        <div className="flex items-start gap-2">
                          <div className="min-w-0 flex-1">
                            <TaskTitleInline
                              title={tk.title ?? ''}
                              disabled={!canEdit}
                              onCommit={(next) => patchTask(tk.id, { title: next })}
                            />
                          </div>
                          <div className="flex shrink-0 items-start gap-0.5">
                            {activitiesParent ? (
                              <TaskActivitiesButton
                                variant={
                                  activitiesParent.variant === 'project' ? 'project_task' : 'master_quotation_task'
                                }
                                parentId={activitiesParent.parentId}
                                taskId={tk.id}
                                taskTitle={tk.title ?? ''}
                                canPost={canEdit}
                              />
                            ) : null}
                            <TaskDescriptionPopover
                              taskId={tk.id}
                              description={tk.description as string | null | undefined}
                              canEdit={canEdit}
                              onSaveDescription={(next) => patchTask(tk.id, { description: next })}
                            />
                          </div>
                        </div>
                        <div className="mt-2 flex justify-end gap-1">
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="size-8"
                            disabled={!canEdit}
                            onClick={() => openEditTask(tk)}
                          >
                            <Pencil className="size-4" />
                          </Button>
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="size-8"
                            disabled={!canEdit}
                            onClick={() => deleteTask(tk.id)}
                          >
                            <Trash2 className="size-4" />
                          </Button>
                        </div>
                      </Card>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        ) : filteredTaskSections.length === 0 ? (
          <p className="text-muted-foreground px-2 py-6 text-center text-sm">No tasks yet.</p>
        ) : (
          filteredTaskSections.map((section) => {
            const doneInSection = section.rows.filter((t) => isTaskDoneCode(t.status_code)).length;
            const totalInSection = section.rows.length;
            const open = taskSectionOpen(section.key);
            const isMySection = section.key === '__my_tasks';
            return (
            <Card
              key={section.key}
              className={cn(
                'overflow-hidden shadow-none',
                isMySection
                  ? 'border border-sky-200/90 bg-sky-50/80'
                  : 'border border-red-200/70 bg-red-50/45',
                dragOverSectionKey === section.key && !isMySection && 'ring-1 ring-[#e7000b]/30',
              )}
            >
              <CardHeader
                className={cn(
                  'flex flex-row items-center justify-between gap-2 px-4 py-3',
                  isMySection ? 'bg-sky-100/55' : 'bg-red-100/45',
                )}
              >
                <button
                  type="button"
                  className="flex min-w-0 flex-1 items-center gap-2 text-start"
                  onClick={() => toggleTaskSection(section.key)}
                >
                  <ChevronDown
                    className={cn('size-4 shrink-0 text-[#6a7282] transition-transform', open ? 'rotate-0' : '-rotate-90')}
                    aria-hidden
                  />
                  <CardTitle
                    className={cn(
                      'text-base font-semibold text-[#101828]',
                      isMySection ? 'text-sky-900' : 'text-[#991b1b]',
                    )}
                  >
                    {section.label}
                    <span className="ms-2 text-sm font-normal text-[#6a7282]">
                      {doneInSection}/{totalInSection} done
                    </span>
                  </CardTitle>
                </button>
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  className="size-8 shrink-0 border-[#e7000b] text-[#e7000b]"
                  aria-label={`Add task in ${section.label}`}
                  disabled={!canEdit}
                  onClick={(e) => {
                    e.stopPropagation();
                    openNewTask(
                      section.label,
                      section.categoryCode,
                      section.key === '__my_tasks' ? sessionUserId : undefined,
                    );
                  }}
                >
                  <Plus className="size-4" />
                </Button>
              </CardHeader>
              {open ? (
              <CardContent
                className={cn('overflow-x-auto px-0 pt-0', isMySection ? 'bg-sky-50/30' : 'bg-red-50/25')}
                onDragOver={(e) => {
                  if (!canDragInList || isMySection || !draggingTaskId) return;
                  e.preventDefault();
                  setDragOverSectionKey(section.key);
                }}
                onDrop={(e) => {
                  if (!canDragInList || isMySection || !draggingTaskId) return;
                  if ((e.target as HTMLElement).closest('[data-task-row="true"]')) return;
                  e.preventDefault();
                  e.stopPropagation();
                  moveTaskToSection(draggingTaskId, section.key, null);
                  setDraggingTaskId(null);
                  setDragOverSectionKey(null);
                }}
              >
                <Table className="min-w-[800px]" style={{ tableLayout: 'fixed' }}>
                  <TableHeader>
                    <TableRow
                      className={cn(
                        'border-b hover:bg-transparent',
                        isMySection ? 'border-sky-200/70 bg-sky-100/40' : 'border-red-200/60 bg-red-100/35',
                      )}
                    >
                      <TableHead className="relative text-xs font-medium uppercase tracking-wide text-[#6a7282]" style={{ width: colWidths.title }}>
                        Task
                        <span
                          className="bg-border absolute end-0 top-0 h-full w-1 cursor-col-resize hover:bg-[#e7000b]/30"
                          onMouseDown={(e) => startResize('title', e)}
                          role="separator"
                          aria-hidden
                        />
                      </TableHead>
                      <TableHead className="relative text-xs font-medium uppercase tracking-wide text-[#6a7282]" style={{ width: colWidths.status }}>
                        Status
                        <span
                          className="bg-border absolute end-0 top-0 h-full w-1 cursor-col-resize hover:bg-[#e7000b]/30"
                          onMouseDown={(e) => startResize('status', e)}
                          role="separator"
                          aria-hidden
                        />
                      </TableHead>
                      <TableHead className="relative text-xs font-medium uppercase tracking-wide text-[#6a7282]" style={{ width: colWidths.assignee }}>
                        Assigned to
                        <span
                          className="bg-border absolute end-0 top-0 h-full w-1 cursor-col-resize hover:bg-[#e7000b]/30"
                          onMouseDown={(e) => startResize('assignee', e)}
                          role="separator"
                          aria-hidden
                        />
                      </TableHead>
                      <TableHead className="text-xs font-medium uppercase tracking-wide text-[#6a7282]" style={{ width: colWidths.timeline }}>
                        Timeline
                      </TableHead>
                      <TableHead className="text-end text-xs font-medium uppercase tracking-wide text-[#6a7282]" style={{ width: colWidths.actions }}>
                        Actions
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(sectionRowViews.get(section.key)?.length ?? 0) === 0 ? (
                      <TableRow>
                        <TableCell
                          colSpan={5}
                          className={cn(
                            'py-10 text-center text-sm text-[#6a7282]',
                            isMySection ? 'bg-sky-50/20' : 'bg-red-50/20',
                          )}
                        >
                          No tasks here yet.
                        </TableCell>
                      </TableRow>
                    ) : (
                    (sectionRowViews.get(section.key) ?? []).map((row) => {
                      const t = row.task;
                      const isSubtask = row.depth === 1;
                      const startVal =
                        t.start_date && String(t.start_date).length >= 10
                          ? String(t.start_date).slice(0, 10)
                          : '';
                      const endVal =
                        t.end_date && String(t.end_date).length >= 10 ? String(t.end_date).slice(0, 10) : '';
                      const statusColor = statusColorMap.get((t.status_code || '').trim());
                      return (
                      <TableRow
                        key={t.id}
                        data-task-row="true"
                        className={cn(
                          'border-b',
                          isMySection
                            ? 'border-sky-100 bg-sky-50/40 hover:bg-sky-100/30'
                            : 'border-red-100 bg-red-50/35 hover:bg-red-100/25',
                          isSubtask && 'bg-opacity-70',
                        )}
                        onDragOver={(e) => {
                          if (!canDragInList || isMySection || !draggingTaskId) return;
                          e.preventDefault();
                          setDragOverSectionKey(section.key);
                        }}
                        onDrop={(e) => {
                          if (!canDragInList || isMySection || !draggingTaskId) return;
                          e.preventDefault();
                          e.stopPropagation();
                          const dropParentId = isSubtask ? row.parentId : null;
                          moveTaskToSection(draggingTaskId, section.key, t.id, dropParentId);
                          setDraggingTaskId(null);
                          setDragOverSectionKey(null);
                        }}
                      >
                        <TableCell className="align-top py-2">
                          <div className="flex items-start gap-2">
                            {!isMySection ? (
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                className={cn(
                                  'size-8 mt-0.5 text-[#6a7282]',
                                  canDragInList ? 'cursor-grab active:cursor-grabbing' : 'cursor-not-allowed opacity-50',
                                )}
                                disabled={!canDragInList}
                                draggable={canDragInList}
                                aria-label="Drag to reorder task"
                                onDragStart={() => {
                                  setDraggingTaskId(t.id);
                                  setDragOverSectionKey(section.key);
                                }}
                                onDragEnd={() => {
                                  setDraggingTaskId(null);
                                  setDragOverSectionKey(null);
                                }}
                              >
                                <GripVertical className="size-4" />
                              </Button>
                            ) : null}
                            <div className="min-w-0 flex-1" style={{ paddingInlineStart: isSubtask ? 16 : 0 }}>
                              <TaskTitleInline
                                title={t.title ?? ''}
                                disabled={!canEdit}
                                onCommit={(next) => patchTask(t.id, { title: next })}
                              />
                            </div>
                            <div className="flex shrink-0 items-start gap-0.5">
                              {!isSubtask ? (
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="icon"
                                  className="size-8 text-[#4a5565]"
                                  disabled={!canEdit}
                                  onClick={() => openNewTask(section.label, section.categoryCode, t.assignee_user_id ?? undefined, t.id)}
                                  aria-label="Add subtask"
                                >
                                  <Plus className="size-4" />
                                </Button>
                              ) : null}
                              {activitiesParent ? (
                                <TaskActivitiesButton
                                  variant={
                                    activitiesParent.variant === 'project' ? 'project_task' : 'master_quotation_task'
                                  }
                                  parentId={activitiesParent.parentId}
                                  taskId={t.id}
                                  taskTitle={t.title ?? ''}
                                  canPost={canEdit}
                                />
                              ) : null}
                              <TaskDescriptionPopover
                                taskId={t.id}
                                description={t.description as string | null | undefined}
                                canEdit={canEdit}
                                onSaveDescription={(next) => patchTask(t.id, { description: next })}
                              />
                            </div>
                          </div>
                        </TableCell>
                        <TableCell className="align-top py-2">
                          <Select
                            value={(t.status_code && t.status_code.trim()) || '__none__'}
                            disabled={!canEdit}
                            onValueChange={(code) => {
                              if (code === '__none__') patchTask(t.id, { status_code: null });
                              else patchTask(t.id, { status_code: code });
                            }}
                          >
                            <SelectTrigger
                              className="h-8 w-full min-w-[6rem] border-[#e5e7eb] text-xs font-medium text-[#101828]"
                              style={
                                statusColor
                                  ? {
                                      borderColor: hexToRgba(statusColor, 0.45),
                                      backgroundColor: hexToRgba(statusColor, 0.14),
                                    }
                                  : undefined
                              }
                            >
                              <SelectValue placeholder="Status" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="__none__">—</SelectItem>
                              {taskStatuses.map((s) => (
                                <SelectItem key={s.id} value={s.code}>
                                  <span className="inline-flex items-center gap-2">
                                    <span
                                      className="inline-block size-2.5 rounded-full border border-black/10"
                                      style={{ backgroundColor: s.color_hex || '#E7000B' }}
                                    />
                                    {s.label}
                                  </span>
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </TableCell>
                        <TableCell className="align-top py-2">
                          <Select
                            value={t.assignee_user_id || '__none__'}
                            disabled={!canEdit}
                            onValueChange={(v) =>
                              patchTask(t.id, {
                                assignee_user_id: v === '__none__' ? null : v,
                              })
                            }
                          >
                            <SelectTrigger className="h-8 w-full min-w-[7rem] border-[#e5e7eb] bg-white text-xs">
                              <SelectValue placeholder="Assign" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="__none__">Unassigned</SelectItem>
                              {usersSelect.map((u) => (
                                <SelectItem key={u.id} value={u.id}>
                                  {(u.name || '').trim() || u.email}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </TableCell>
                        <TableCell className="align-top py-2">
                          <div className="flex items-center gap-2">
                            <Input
                              type="date"
                              className="h-8 border-[#e5e7eb] bg-white text-xs"
                              value={startVal}
                              disabled={!canEdit}
                              onChange={(e) => patchTask(t.id, { start_date: e.target.value ? e.target.value : null })}
                            />
                            <span className="text-xs font-medium text-[#6a7282]">-</span>
                            <Input
                              type="date"
                              className="h-8 border-[#e5e7eb] bg-white text-xs"
                              value={endVal}
                              disabled={!canEdit}
                              onChange={(e) => patchTask(t.id, { end_date: e.target.value ? e.target.value : null })}
                            />
                          </div>
                        </TableCell>
                        <TableCell className="space-x-1 text-end align-top py-2">
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="text-[#6a7282]"
                            disabled={!canEdit}
                            onClick={() => openEditTask(t)}
                          >
                            <Pencil className="size-4" />
                          </Button>
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="text-[#e7000b]"
                            disabled={!canEdit}
                            onClick={() => deleteTask(t.id)}
                          >
                            <Trash2 className="size-4" />
                          </Button>
                        </TableCell>
                      </TableRow>
                      );
                    })
                    )}
                  </TableBody>
                </Table>
              </CardContent>
              ) : null}
            </Card>
          );
          })
        )}
          </div>
        </div>
      </div>
      <Dialog open={taskDialogOpen} onOpenChange={setTaskDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editingTask ? 'Edit task' : 'Add task'}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 py-2">
            <div className="grid gap-2">
              <Label>Title</Label>
              <Input value={taskForm.title} onChange={(e) => setTaskForm((f) => ({ ...f, title: e.target.value }))} />
            </div>
            <div className="grid gap-2">
              <Label>Description</Label>
              <Textarea
                value={taskForm.description}
                onChange={(e) => setTaskForm((f) => ({ ...f, description: e.target.value }))}
                rows={3}
              />
            </div>
            <div className="grid gap-2">
              <Label>Category</Label>
              {taskForm.parent_task_id ? (
                <Input value={taskById.get(taskForm.parent_task_id)?.category || 'Inherited from parent'} disabled readOnly />
              ) : taskCategories.some((c) => c.is_active) ? (
                <Select
                  value={
                    taskForm.category_code?.trim()
                      ? taskForm.category_code
                      : (taskCategories.find((c) => c.is_active)?.code ?? '')
                  }
                  onValueChange={(v) => {
                    const row = taskCategories.find((c) => c.code === v);
                    setTaskForm((f) => ({
                      ...f,
                      category_code: v,
                      category: row?.label ?? '',
                    }));
                  }}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Category" />
                  </SelectTrigger>
                  <SelectContent>
                    {taskCategories
                      .filter((c) => c.is_active)
                      .map((c) => (
                        <SelectItem key={c.code} value={c.code}>
                          {c.label}
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>
              ) : (
                <Input
                  value={taskForm.category}
                  onChange={(e) =>
                    setTaskForm((f) => ({ ...f, category: e.target.value, category_code: '' }))
                  }
                  placeholder="Category"
                />
              )}
            </div>
            <div className="grid gap-2">
              <Label>Assignee</Label>
              <Select
                value={taskForm.assignee_user_id || '__none__'}
                onValueChange={(v) => setTaskForm((f) => ({ ...f, assignee_user_id: v === '__none__' ? '' : v }))}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Assignee" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">—</SelectItem>
                  {usersSelect.map((u) => (
                    <SelectItem key={u.id} value={u.id}>
                      {(u.name || '').trim() || u.email}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2 sm:grid-cols-2 sm:gap-4">
              <div className="grid gap-2">
                <Label>Sort order</Label>
                <Input
                  type="number"
                  value={taskForm.sort_order}
                  onChange={(e) => setTaskForm((f) => ({ ...f, sort_order: Number(e.target.value) }))}
                />
              </div>
              <div className="grid gap-2">
                <Label>Status</Label>
                <Select
                  value={taskForm.status_code || '__none__'}
                  onValueChange={(v) => setTaskForm((f) => ({ ...f, status_code: v === '__none__' ? '' : v }))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Status" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">—</SelectItem>
                    {taskStatuses.map((s) => (
                      <SelectItem key={s.id} value={s.code}>
                        <span className="inline-flex items-center gap-2">
                          <span
                            className="inline-block size-2.5 rounded-full border border-black/10"
                            style={{ backgroundColor: s.color_hex || '#E7000B' }}
                          />
                          {s.label}
                        </span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid gap-2 sm:grid-cols-2 sm:gap-4">
              <div className="grid gap-2">
                <Label>Lead time (working days)</Label>
                <Input
                  type="number"
                  min={1}
                  value={taskForm.lead_time_days}
                  onChange={(e) =>
                    setTaskForm((f) => ({ ...f, lead_time_days: Math.max(1, Number(e.target.value) || 1) }))
                  }
                />
              </div>
              <div className="grid gap-2">
                <Label>Depends on</Label>
                <Popover open={dependencyPickerOpen} onOpenChange={setDependencyPickerOpen}>
                  <PopoverTrigger asChild>
                    <Button type="button" variant="outline" className="justify-between font-normal">
                      <span className="truncate text-left">
                        {taskForm.dependency_task_ids.length
                          ? `${taskForm.dependency_task_ids.length} task(s) selected`
                          : 'Select dependencies...'}
                      </span>
                      <ChevronDown className="ml-2 size-4 shrink-0 opacity-70" />
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent align="start" className="w-[360px] p-0">
                    <Command>
                      <CommandInput placeholder="Search tasks..." />
                      <CommandList>
                        <CommandEmpty>No matching tasks.</CommandEmpty>
                        <CommandGroup>
                          {normalizedTasks
                            .filter((t) => !editingTask || t.id !== editingTask.id)
                            .map((t) => {
                              const checked = taskForm.dependency_task_ids.includes(t.id);
                              return (
                                <CommandItem
                                  key={t.id}
                                  value={`${t.title || 'Task'} ${t.category || ''}`}
                                  onSelect={() =>
                                    setTaskForm((f) => ({
                                      ...f,
                                      dependency_task_ids: checked
                                        ? f.dependency_task_ids.filter((id) => id !== t.id)
                                        : [...f.dependency_task_ids, t.id],
                                    }))
                                  }
                                >
                                  <Check className={cn('mr-2 size-4', checked ? 'opacity-100' : 'opacity-0')} />
                                  <span className="truncate">{t.title || 'Task'}</span>
                                </CommandItem>
                              );
                            })}
                        </CommandGroup>
                      </CommandList>
                    </Command>
                  </PopoverContent>
                </Popover>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setTaskDialogOpen(false)}>
              Cancel
            </Button>
            <Button type="button" onClick={submitTaskDialog} disabled={!canEdit}>
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog open={schedulePreviewOpen} onOpenChange={setSchedulePreviewOpen}>
        <DialogContent className="max-h-[80vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Schedule impact preview</DialogTitle>
          </DialogHeader>
          {!schedulePreviewImpacts.length ? (
            <p className="text-sm text-[#6a7282]">No task date changes detected.</p>
          ) : (
            <div className="space-y-2">
              {schedulePreviewImpacts.map((imp) => (
                <div key={imp.task_id} className="rounded-md border p-3 text-sm">
                  <div className="mb-2 font-medium text-[#101828]">{imp.title}</div>
                  <div className="grid gap-2 md:grid-cols-[1fr_auto_1fr] md:items-center">
                    <div className="rounded-md border border-[#e5e7eb] bg-[#f9fafb] px-2 py-1.5">
                      <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-[#6a7282]">Before</div>
                      <div className="text-xs text-[#364153]">
                        <span className="inline-block rounded bg-white px-2 py-0.5">{imp.old_start_date || '—'}</span>
                        <span className="mx-1 text-[#9ca3af]">to</span>
                        <span className="inline-block rounded bg-white px-2 py-0.5">{imp.old_end_date || '—'}</span>
                      </div>
                    </div>
                    <div className="text-center text-xs font-semibold text-[#6a7282]">→</div>
                    <div className="rounded-md border border-[#fecaca] bg-[#fef2f2] px-2 py-1.5">
                      <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-[#9f0712]">After</div>
                      <div className="text-xs text-[#7f1d1d]">
                        <span className="inline-block rounded bg-white px-2 py-0.5">{imp.new_start_date || '—'}</span>
                        <span className="mx-1 text-[#f87171]">to</span>
                        <span className="inline-block rounded bg-white px-2 py-0.5">{imp.new_end_date || '—'}</span>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setSchedulePreviewOpen(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              onClick={() => void applySchedule()}
              disabled={scheduleApplyPending || !schedulePreviewBoard || !canEdit}
            >
              Apply
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
