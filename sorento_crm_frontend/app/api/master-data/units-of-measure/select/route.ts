import { NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

/**
 * GET /api/master-data/units-of-measure/select
 * 
 * Fetch UOMs for dropdown/select components
 */
export async function GET() {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const uoms = await prisma.unitOfMeasure.findMany({
      select: {
        id: true,
        uomCode: true,
        uomName: true,
        baseUomId: true,
        conversionFactor: true,
      },
      orderBy: {
        uomName: 'asc',
      },
    });

    // Transform to snake_case for consistency with other API endpoints
    const transformedUOMs = uoms.map((uom) => ({
      id: uom.id,
      uom_code: uom.uomCode,
      uom_name: uom.uomName,
      base_uom_id: uom.baseUomId,
      conversion_factor: uom.conversionFactor ? Number(uom.conversionFactor) : null,
    }));

    return NextResponse.json(transformedUOMs);
  } catch (error) {
    console.error('Error fetching UOMs:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}
