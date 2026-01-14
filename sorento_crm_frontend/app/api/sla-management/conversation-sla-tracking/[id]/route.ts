import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

/**
 * Transform Prisma conversation SLA tracking to frontend expected format (snake_case)
 */
function transformConversationSLATracking(tracking: any) {
  return {
    id: tracking.id,
    policy_id: tracking.policyId,
    policy_code: tracking.policy?.code,
    policy_name: tracking.policy?.name,
    current_tier: tracking.currentTier,
    assigned_to: tracking.assignedTo,
    initiated_at: tracking.initiatedAt,
    current_tier_started_at: tracking.currentTierStartedAt,
    due_at: tracking.dueAt,
    escalated_at: tracking.escalatedAt,
    escalation_reason: tracking.escalationReason,
    is_resolved: tracking.isResolved,
    resolved_at: tracking.resolvedAt,
    resolved_by: tracking.resolvedBy,
    created_at: tracking.createdAt,
    updated_at: tracking.updatedAt,
    respond_contact_id: tracking.respondContactId,
    synced_to_excel: tracking.syncedToExcel,
    last_synced_to_excel: tracking.lastSyncedToExcel,
    resolution_duration: tracking.resolutionDuration ? Number(tracking.resolutionDuration) : null,
  };
}

/**
 * Transform Prisma escalation log to frontend expected format (snake_case)
 */
function transformEscalationLog(log: any) {
  return {
    id: log.id,
    sla_tracking_id: log.slaTrackingId,
    from_tier: log.fromTier,
    to_tier: log.toTier,
    escalated_at: log.escalatedAt,
    reason: log.reason,
    assigned_to: log.assignedTo,
    due_at: log.dueAt,
    reminder_count: log.reminderCount,
    last_reminder_at: log.lastReminderAt,
    created_at: log.createdAt,
  };
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const { id } = await params;

    // Validate that id is a valid UUID format
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRegex.test(id)) {
      return NextResponse.json(
        { message: 'Invalid conversation SLA tracking ID format' },
        { status: 400 },
      );
    }

    const tracking = await prisma.conversationSLATracking.findUnique({
      where: { id },
      include: {
        policy: {
          select: {
            id: true,
            code: true,
            name: true,
          },
        },
        escalationLogs: {
          orderBy: {
            escalatedAt: 'desc',
          },
        },
      },
    });

    if (!tracking) {
      return NextResponse.json(
        { message: 'Conversation SLA tracking not found' },
        { status: 404 },
      );
    }

    // Transform to snake_case for frontend
    const transformedTracking = {
      ...transformConversationSLATracking(tracking),
      escalation_logs: tracking.escalationLogs.map(transformEscalationLog),
    };

    return NextResponse.json(transformedTracking);
  } catch (error) {
    console.error('Error fetching conversation SLA tracking:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}
