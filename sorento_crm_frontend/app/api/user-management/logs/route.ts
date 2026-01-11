import { NextRequest, NextResponse } from 'next/server';
import { Prisma } from '@prisma/client';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const page = parseInt(searchParams.get('page') || '1', 10);
  const limit = parseInt(searchParams.get('limit') || '10', 10);
  const query = searchParams.get('query') || '';
  const sortField = searchParams.get('sort') || 'createdAt';
  const sortDirection = searchParams.get('dir') === 'desc' ? 'desc' : 'asc';
  const createdAtFrom = searchParams.get('createdAtFrom'); // Start date
  const createdAtTo = searchParams.get('createdAtTo'); // End date

  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 }, // Unauthorized
      );
    }

    // Count total activity logs with filters
    const totalCount = await prisma.systemLog.count({
      where: {
        AND: [
          ...(createdAtFrom || createdAtTo
            ? [
                {
                  createdAt: {
                    ...(createdAtFrom ? { gte: new Date(createdAtFrom) } : {}), // Greater than or equal to `from`
                    ...(createdAtTo ? { lte: new Date(createdAtTo) } : {}), // Less than or equal to `to`
                  },
                },
              ]
            : []),
          {
            OR: [
              { event: { contains: query, mode: 'insensitive' } },
              { description: { contains: query, mode: 'insensitive' } },
              { ipAddress: { contains: query, mode: 'insensitive' } },
              { entityId: { contains: query, mode: 'insensitive' } },
              { entityType: { contains: query, mode: 'insensitive' } },
              { user: { name: { contains: query, mode: 'insensitive' } } },
            ],
          },
        ],
      },
    });

    // Handle sorting logic
    const orderBy =
      sortField === 'user_name'
        ? { user: { name: sortDirection as Prisma.SortOrder } } // Sort by user name
        : { [sortField]: sortDirection as Prisma.SortOrder }; // Default sorting

    // Fetch activity logs with filters, pagination, and sorting
    const logs = await prisma.systemLog.findMany({
      where: {
        AND: [
          ...(createdAtFrom || createdAtTo
            ? [
                {
                  createdAt: {
                    ...(createdAtFrom ? { gte: new Date(createdAtFrom) } : {}), // Greater than or equal to `from`
                    ...(createdAtTo ? { lte: new Date(createdAtTo) } : {}), // Less than or equal to `to`
                  },
                },
              ]
            : []),
          {
            OR: [
              { event: { contains: query, mode: 'insensitive' } },
              { description: { contains: query, mode: 'insensitive' } },
              { entityId: { contains: query, mode: 'insensitive' } },
              { ipAddress: { contains: query, mode: 'insensitive' } },
              { entityType: { contains: query, mode: 'insensitive' } },
              { user: { name: { contains: query, mode: 'insensitive' } } },
            ],
          },
        ],
      },
      skip: (page - 1) * limit,
      take: limit,
      orderBy,
      select: {
        id: true,
        event: true,
        entityId: true,
        entityType: true,
        description: true,
        createdAt: true,
        ipAddress: true,
        user: {
          select: {
            id: true,
            name: true,
            email: true,
            avatar: true,
          },
        },
      },
    });

    // Return response
    return NextResponse.json({
      data: logs,
      pagination: {
        total: totalCount,
        page,
        limit,
      },
    });
  } catch {
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}
