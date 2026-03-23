"""External API: configured working days (as contiguous ranges) and working hours.

Auth: X-API-Key header (get_external_api_user), same as other /external routes.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.schemas.calendar import ExternalWorkCalendarSummary, ExternalWorkingDayRange
from app.services.calendar_service import DEFAULT_WORKING_TZ, CalendarService

router = APIRouter()


@router.get(
    "",
    response_model=ExternalWorkCalendarSummary,
    summary="Get working day ranges and working hours",
)
async def get_work_calendar_summary(
    _current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """
    Returns how working days are configured:

    - **working_day_ranges**: each item is one contiguous block of working weekdays.
      Example: Mon–Fri with all five days on → one range Monday→Friday.
      If Wednesday is off → two ranges: Monday→Tuesday and Thursday→Friday.

    - **working_hours_start** / **working_hours_end**: local wall-clock times applied on each
      working day (same **timezone** as used elsewhere for business hours, e.g. next-assignee).
    """
    service = CalendarService(db)
    start_t, end_t = service.get_working_hours()
    ranges = service.get_working_day_ranges()
    tz_key = getattr(DEFAULT_WORKING_TZ, "key", None) or str(DEFAULT_WORKING_TZ)
    return ExternalWorkCalendarSummary(
        timezone=tz_key,
        working_hours_start=start_t.isoformat(),
        working_hours_end=end_t.isoformat(),
        working_day_ranges=[
            ExternalWorkingDayRange(start_weekday=r["start_weekday"], end_weekday=r["end_weekday"])
            for r in ranges
        ],
    )
