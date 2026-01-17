import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

/**
 * Transform Prisma contact agent access to frontend expected format (snake_case)
 */
function transformContactAgentAccess(access: {
  id: string;
  respondContactId: string;
  agentId: string;
  agent?: { code: string; name: string } | null;
  isAllowed: boolean;
  validFrom: Date | null;
  validTo: Date | null;
  createdAt: Date;
  createdBy: string | null;
  syncedToExcel: boolean;
  lastSyncedToExcel: Date | null;
  updatedAt: Date | null;
}) {
  return {
    id: access.id,
    respond_contact_id: access.respondContactId,
    agent_id: access.agentId,
    agent_code: access.agent?.code,
    agent_name: access.agent?.name,
    is_allowed: access.isAllowed,
    valid_from: access.validFrom,
    valid_to: access.validTo,
    created_at: access.createdAt,
    created_by: access.createdBy,
    synced_to_excel: access.syncedToExcel,
    last_synced_to_excel: access.lastSyncedToExcel,
    updated_at: access.updatedAt,
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
    const agentId = searchParams.get('agent_id') || null;
    const contactId = searchParams.get('contact_id') || null;

    // Build where clause with filters
    const whereClause: {
      agentId?: string;
      respondContactId?: { contains: string; mode: 'insensitive' } | string;
      OR?: Array<{
        respondContactId?: { contains: string; mode: 'insensitive' };
        agent?: {
          code?: { contains: string; mode: 'insensitive' };
          name?: { contains: string; mode: 'insensitive' };
        };
      }>;
    } = {
      ...(agentId && agentId !== 'all' ? { agentId } : {}),
      ...(contactId ? { respondContactId: { contains: contactId, mode: 'insensitive' } } : {}),
      ...(query
        ? {
            OR: [
              { respondContactId: { contains: query, mode: 'insensitive' } },
              { agent: { code: { contains: query, mode: 'insensitive' } } },
              { agent: { name: { contains: query, mode: 'insensitive' } } },
            ],
          }
        : {}),
    };

    const totalCount = await prisma.contactAgentAccess.count({ where: whereClause });

    // Map sort field
    const sortMap: Record<string, string> = {
      respond_contact_id: 'respondContactId',
      agent_code: 'agent.code',
      agent_name: 'agent.name',
      created_at: 'createdAt',
      updated_at: 'updatedAt',
    };
    const mappedSortField = sortMap[sortField] || 'createdAt';

    const contactAccesses = await prisma.contactAgentAccess.findMany({
      where: whereClause,
      skip: (page - 1) * limit,
      take: limit,
      include: {
        agent: {
          select: {
            id: true,
            code: true,
            name: true,
          },
        },
      },
      orderBy: mappedSortField.includes('.') 
        ? { agent: { [mappedSortField.split('.')[1]]: sortDirection } }
        : { [mappedSortField]: sortDirection },
    });

    // Transform to snake_case for frontend
    const transformedContactAccesses = contactAccesses.map(transformContactAgentAccess);

    return NextResponse.json({
      data: transformedContactAccesses,
      pagination: {
        total: totalCount,
        page,
        limit,
      },
      empty: totalCount === 0,
    });
  } catch (error) {
    console.error('Error fetching contact access agents:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}
