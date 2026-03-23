"""Calendar service for business-day calculations."""
from datetime import date, datetime, time, timedelta
from typing import Optional, Set
from zoneinfo import ZoneInfo
import logging
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.models.calendar import PublicHoliday, WorkCalendarConfig

logger = logging.getLogger(__name__)

# Default timezone for working-hours checks (tenant wall clock; align with Work Calendar UI).
DEFAULT_WORKING_TZ = ZoneInfo("Asia/Kuala_Lumpur")


class CalendarService:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create_work_calendar(self) -> WorkCalendarConfig:
        config = self.db.query(WorkCalendarConfig).filter(
            WorkCalendarConfig.config_key == "default"
        ).first()
        if not config:
            config = WorkCalendarConfig(
                config_key="default",
                monday=True,
                tuesday=True,
                wednesday=True,
                thursday=True,
                friday=True,
                saturday=False,
                sunday=False,
                work_day_start_time=time(9, 0, 0),
                work_day_end_time=time(17, 0, 0),
            )
            self.db.add(config)
            self.db.flush()
        return config

    def get_working_weekdays(self) -> Set[int]:
        try:
            config = self.get_or_create_work_calendar()
            weekday_map = {
                0: config.monday,
                1: config.tuesday,
                2: config.wednesday,
                3: config.thursday,
                4: config.friday,
                5: config.saturday,
                6: config.sunday,
            }
            return {day for day, is_working in weekday_map.items() if is_working}
        except SQLAlchemyError:
            logger.warning("Work calendar config unavailable; defaulting to Mon-Fri.")
            return {0, 1, 2, 3, 4}

    def get_working_hours(self) -> tuple[time, time]:
        """Start and end clock times for a standard working day (same every working weekday)."""
        try:
            config = self.get_or_create_work_calendar()
            start = config.work_day_start_time
            end = config.work_day_end_time
            if start is not None and end is not None:
                return (start, end)
        except SQLAlchemyError:
            logger.warning("Work calendar config unavailable; defaulting working hours 09:00–17:00.")
        return (time(9, 0, 0), time(17, 0, 0))

    def is_within_working_time(
        self,
        when: Optional[datetime] = None,
        *,
        tz: ZoneInfo = DEFAULT_WORKING_TZ,
    ) -> bool:
        """
        True if `when` falls on a configured business day (weekday + not a public holiday)
        and the local time-of-day is within work_day_start_time..work_day_end_time (inclusive).

        If `when` is None, uses current time in `tz`.
        If `when` is naive, it is interpreted as local wall time in `tz` (not UTC).
        """
        try:
            if when is None:
                dt_local = datetime.now(tz)
            elif when.tzinfo is None:
                dt_local = when.replace(tzinfo=tz)
            else:
                dt_local = when.astimezone(tz)

            d = dt_local.date()
            weekday = d.weekday()
            working_weekdays = self.get_working_weekdays()
            holidays = self.get_public_holidays_between(d, d)
            if not self._is_business_day(d, working_weekdays, holidays):
                return False

            start_t, end_t = self.get_working_hours()
            t = dt_local.time()
            return start_t <= t <= end_t
        except SQLAlchemyError:
            logger.warning("Work calendar unavailable for working-time check; treating as non-working.")
            return False

    def get_public_holidays_between(self, start_date: date, end_date: date) -> Set[date]:
        try:
            holidays = self.db.query(PublicHoliday).filter(
                PublicHoliday.date >= start_date,
                PublicHoliday.date <= end_date,
            ).all()
            return {holiday.date for holiday in holidays}
        except SQLAlchemyError:
            logger.warning("Public holidays table unavailable; ignoring holidays for now.")
            return set()

    def _to_date(self, value: Optional[date | datetime]) -> Optional[date]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        return value

    def _is_business_day(self, value: date, working_weekdays: Set[int], holidays: Set[date]) -> bool:
        return value.weekday() in working_weekdays and value not in holidays

    def add_business_days(
        self,
        start_value: date | datetime,
        days: int,
        working_weekdays: Optional[Set[int]] = None,
        holidays: Optional[Set[date]] = None,
    ) -> Optional[datetime]:
        if start_value is None:
            return None
        if days <= 0:
            return start_value if isinstance(start_value, datetime) else datetime.combine(start_value, datetime.min.time())

        start_date = self._to_date(start_value)
        if start_date is None:
            return None
        working_weekdays = working_weekdays or self.get_working_weekdays()
        end_date = start_date
        if holidays is None:
            holidays = self.get_public_holidays_between(start_date, start_date + timedelta(days=days * 7 + 14))

        added = 0
        while added < days:
            end_date = end_date + timedelta(days=1)
            if self._is_business_day(end_date, working_weekdays, holidays):
                added += 1

        if isinstance(start_value, datetime):
            return datetime.combine(end_date, start_value.time())
        return datetime.combine(end_date, datetime.min.time())

    def business_days_between(
        self,
        start_value: date | datetime,
        end_value: date | datetime,
        working_weekdays: Optional[Set[int]] = None,
        holidays: Optional[Set[date]] = None,
    ) -> int:
        start_date = self._to_date(start_value)
        end_date = self._to_date(end_value)
        if not start_date or not end_date:
            return 0
        if end_date < start_date:
            return 0

        working_weekdays = working_weekdays or self.get_working_weekdays()
        if holidays is None:
            holidays = self.get_public_holidays_between(start_date, end_date)
        total = 0
        current = start_date
        while current < end_date:
            current = current + timedelta(days=1)
            if self._is_business_day(current, working_weekdays, holidays):
                total += 1
        return total
