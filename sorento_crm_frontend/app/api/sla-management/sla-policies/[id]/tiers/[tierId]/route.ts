import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

/**
 * Transform Prisma SLA policy tier to frontend expected format (snake_case)
 */
function transformSLAPolicyTier(tier: any) {
  return {
    id: tier.id,
    policy_id: tier.policyId,
    tier_level: tier.tierLevel,
    tier_name: tier.tierName,
    response_hours: tier.responseHours,
    created_at: tier.createdAt,
    updated_at: tier.updatedAt,
  };
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string; tierId: string }> },
) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const { id, tierId } = await params;

    // Validate that id is a valid UUID format
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRegex.test(id) || !uuidRegex.test(tierId)) {
      return NextResponse.json(
        { message: 'Invalid ID format' },
        { status: 400 },
      );
    }

    const body = await request.json();

    const tier = await prisma.sLAPolicyTier.update({
      where: { id: tierId },
      data: {
        tierLevel: body.tier_level,
        tierName: body.tier_name,
        responseHours: body.response_hours,
      },
    });

    // Verify it belongs to the policy
    if (tier.policyId !== id) {
      return NextResponse.json(
        { message: 'Tier does not belong to this policy' },
        { status: 400 },
      );
    }

    // Transform to snake_case for frontend
    const transformedTier = transformSLAPolicyTier(tier);

    return NextResponse.json(transformedTier);
  } catch (error) {
    console.error('Error updating SLA policy tier:', error);
    
    // Handle unique constraint violation
    if (error instanceof Error && error.message.includes('Unique constraint')) {
      return NextResponse.json(
        { message: 'Tier level already exists for this policy. Please use a different tier level.' },
        { status: 400 },
      );
    }

    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string; tierId: string }> },
) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const { id, tierId } = await params;

    // Validate that id is a valid UUID format
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRegex.test(id) || !uuidRegex.test(tierId)) {
      return NextResponse.json(
        { message: 'Invalid ID format' },
        { status: 400 },
      );
    }

    // Check if tier exists
    const tier = await prisma.sLAPolicyTier.findUnique({
      where: { id: tierId },
    });

    if (!tier) {
      return NextResponse.json(
        { message: 'SLA policy tier not found' },
        { status: 404 },
      );
    }

    // Verify it belongs to the policy
    if (tier.policyId !== id) {
      return NextResponse.json(
        { message: 'Tier does not belong to this policy' },
        { status: 400 },
      );
    }

    // Permanently delete the tier
    await prisma.sLAPolicyTier.delete({
      where: { id: tierId },
    });

    return NextResponse.json({ message: 'SLA policy tier deleted successfully' });
  } catch (error) {
    console.error('Error deleting SLA policy tier:', error);

    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}
