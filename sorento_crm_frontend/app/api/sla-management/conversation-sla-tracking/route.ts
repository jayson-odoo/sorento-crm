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

export async function GET(req: NextRequest) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const { searchParams } = new URL(req.url);
    const page = parseInt(searchParams.get('page') || '1', 10);
    const limit = parseInt(searchParams.get('limit') || '50', 10);
    const query = searchParams.get('query') || '';
    const sortField = searchParams.get('sort') || 'created_at';
    const sortDirection = searchParams.get('dir') === 'desc' ? 'desc' : 'asc';
    const policyId = searchParams.get('policy_id') || null;
    const status = searchParams.get('status') || 'all';
    const assignedTo = searchParams.get('assigned_to') || null;

    // Build where clause with filters
    const whereClause: any = {
      ...(policyId && policyId !== 'all' ? { policyId } : {}),
      ...(assignedTo && assignedTo !== 'all' ? { assignedTo } : {}),
      ...(status && status !== 'all'
        ? status === 'resolved'
          ? { isResolved: true }
          : status === 'escalated'
          ? { escalatedAt: { not: null } }
          : status === 'pending'
          ? { isResolved: false, escalatedAt: null }
          : {}
        : {}),
      ...(query
        ? {
            OR: [
              { respondContactId: { contains: query, mode: 'insensitive' } },
              { assignedTo: { contains: query, mode: 'insensitive' } },
              { policy: { name: { contains: query, mode: 'insensitive' } } },
              { policy: { code: { contains: query, mode: 'insensitive' } } },
            ],
          }
        : {}),
    };

    const totalCount = await prisma.conversationSLATracking.count({ where: whereClause });

    // Map sort field
    const sortMap: Record<string, string> = {
      respond_contact_id: 'respondContactId',
      policy_name: 'policy.name',
      current_tier: 'currentTier',
      assigned_to: 'assignedTo',
      initiated_at: 'initiatedAt',
      due_at: 'dueAt',
      escalated_at: 'escalatedAt',
      is_resolved: 'isResolved',
      resolved_at: 'resolvedAt',
      created_at: 'createdAt',
    };
    const mappedSortField = sortMap[sortField] || 'createdAt';

    const trackings = await prisma.conversationSLATracking.findMany({
      where: whereClause,
      skip: (page - 1) * limit,
      take: limit,
      include: {
        policy: {
          select: {
            id: true,
            code: true,
            name: true,
          },
        },
      },
      orderBy: mappedSortField.includes('.')
        ? { policy: { [mappedSortField.split('.')[1]]: sortDirection } }
        : { [mappedSortField]: sortDirection },
    });

    // Transform to snake_case for frontend
    const transformedTrackings = trackings.map(transformConversationSLATracking);

    return NextResponse.json({
      data: transformedTrackings,
      pagination: {
        total: totalCount,
        page,
        limit,
      },
      empty: totalCount === 0,
    });
  } catch (error) {
    console.error('Error fetching conversation SLA tracking:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}
