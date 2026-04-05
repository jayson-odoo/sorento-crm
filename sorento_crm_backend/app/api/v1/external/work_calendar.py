"""External API: configured working days (as contiguous ranges) and working hours.

Auth: X-API-Key header (get_external_api_user), same as other /external routes.
"""
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.schemas.calendar import (
    ExternalWorkCalendarSummary,
    ExternalWorkingDayCheckResponse,
    ExternalWorkingDayRange,
)
from app.services.calendar_service import DEFAULT_WORKING_TZ, CalendarService, format_time_12h_ampm

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

    - **working_hours_start** / **working_hours_end**: local wall-clock times in 12-hour form
      (e.g. 09:00 A.M.) on each working day (same **timezone** as used elsewhere).
    """
    service = CalendarService(db)
    start_t, end_t = service.get_working_hours()
    ranges = service.get_working_day_ranges()
    tz_key = getattr(DEFAULT_WORKING_TZ, "key", None) or str(DEFAULT_WORKING_TZ)
    return ExternalWorkCalendarSummary(
        timezone=tz_key,
        working_hours_start=format_time_12h_ampm(start_t),
        working_hours_end=format_time_12h_ampm(end_t),
        working_day_ranges=[
            ExternalWorkingDayRange(start_weekday=r["start_weekday"], end_weekday=r["end_weekday"])
            for r in ranges
        ],
    )


@router.get(
    "/is-working-day",
    response_model=ExternalWorkingDayCheckResponse,
    summary="Check if today is a working day",
)
async def get_is_working_day(
    timezone: Optional[str] = Query(
        None,
        alias="timezone",
        description="IANA timezone (e.g. Asia/Kuala_Lumpur). Omit to use Malaysia time.",
    ),
    _current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """
    Returns whether **now**, interpreted in the given timezone, falls on a **working day**
    per the CRM work calendar: enabled weekday (Mon–Sun flags) and not a **public holiday**.

    Clock time within the day is ignored; for working hours use the work-calendar summary
    and your own logic, or internal `is_within_working_time` patterns.

    **Auth:** `X-API-Key` header (external API key).
    """
    tz_key = (timezone or "").strip() or "Asia/Kuala_Lumpur"
    try:
        tz = ZoneInfo(tz_key)
    except ZoneInfoNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": f"Unknown IANA timezone: {tz_key}",
                "code": "INVALID_TIMEZONE",
            },
        )
    service = CalendarService(db)
    data = service.is_working_day(tz=tz)
    return ExternalWorkingDayCheckResponse.model_validate(data)
