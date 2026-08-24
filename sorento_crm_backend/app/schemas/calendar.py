"""Calendar and working days schemas."""
from datetime import date as dt_date, datetime, time
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class PublicHolidayBase(BaseModel):
    date: dt_date
    name: str
    description: Optional[str] = None


class PublicHolidayCreate(PublicHolidayBase):
    pass


class PublicHolidayUpdate(BaseModel):
    date: Optional[dt_date] = None
    name: Optional[str] = None
    description: Optional[str] = None


class PublicHolidayResponse(PublicHolidayBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkCalendarConfigBase(BaseModel):
    monday: bool
    tuesday: bool
    wednesday: bool
    thursday: bool
    friday: bool
    saturday: bool
    sunday: bool
    work_day_start_time: time
    work_day_end_time: time


class WorkCalendarConfigUpdate(BaseModel):
    monday: Optional[bool] = None
    tuesday: Optional[bool] = None
    wednesday: Optional[bool] = None
    thursday: Optional[bool] = None
    friday: Optional[bool] = None
    saturday: Optional[bool] = None
    sunday: Optional[bool] = None
    work_day_start_time: Optional[time] = None
    work_day_end_time: Optional[time] = None


class WorkCalendarConfigResponse(WorkCalendarConfigBase):
    id: str
    config_key: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ExternalWorkingDayRange(BaseModel):
    """One contiguous run of working days (Monday - Sunday order)."""

    model_config = ConfigDict(populate_by_name=True)

    start_weekday: str = Field(
        ...,
        description="First calendar day in this range (e.g. Monday).",
    )
    end_weekday: str = Field(
        ...,
        description="Last calendar day in this range (e.g. Friday).",
    )


class ExternalWorkCalendarSummary(BaseModel):
    """External API: working days as ranges plus shared daily working hours."""

    model_config = ConfigDict(populate_by_name=True)

    timezone: str = Field(
        ...,
        description="IANA timezone used for working-hours interpretation (e.g. Asia/Kuala_Lumpur).",
    )
    working_hours_start: str = Field(
        ...,
        description='Local start of working hours in 12-hour form (e.g. "09:00 A.M.").',
    )
    working_hours_end: str = Field(
        ...,
        description='Local end of working hours in 12-hour form (e.g. "05:30 P.M.").',
    )
    working_day_ranges: List[ExternalWorkingDayRange] = Field(
        default_factory=list,
        description="Contiguous working weekday ranges; gaps create separate entries.",
    )


class ExternalWorkingDayCheckResponse(BaseModel):
    """External API: whether the current (or evaluated) calendar day is a working day."""

    model_config = ConfigDict(populate_by_name=True)

    is_working_day: bool = Field(
        ...,
        description="True if the local calendar date is an enabled weekday and not a public holiday.",
    )
    timezone: str = Field(
        ...,
        description="IANA timezone used to interpret “now” (default Asia/Kuala_Lumpur when omitted).",
    )
    local_datetime: str = Field(
        ...,
        description="Instant evaluated, as ISO 8601 in the requested timezone.",
    )
    local_date: dt_date = Field(..., description="Calendar date in that timezone.")
    weekday: str = Field(..., description="English weekday name (Monday - Sunday).")
    is_public_holiday: bool = Field(
        ...,
        description="True if this local_date matches a row in the CRM public holiday calendar.",
    )
