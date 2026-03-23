"""Calendar and working days schemas."""
from datetime import date, datetime, time
from typing import Optional
from pydantic import BaseModel


class PublicHolidayBase(BaseModel):
    date: date
    name: str
    description: Optional[str] = None


class PublicHolidayCreate(PublicHolidayBase):
    pass


class PublicHolidayUpdate(BaseModel):
    date: Optional[date] = None
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
