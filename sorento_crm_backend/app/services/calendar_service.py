"""Calendar service for business-day calculations."""
from datetime import date, datetime, timedelta
from typing import Optional, Set
from sqlalchemy.orm import Session
from app.models.calendar import PublicHoliday, WorkCalendarConfig


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
            )
            self.db.add(config)
            self.db.flush()
        return config

    def get_working_weekdays(self) -> Set[int]:
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

    def get_public_holidays_between(self, start_date: date, end_date: date) -> Set[date]:
        holidays = self.db.query(PublicHoliday).filter(
            PublicHoliday.date >= start_date,
            PublicHoliday.date <= end_date,
        ).all()
        return {holiday.date for holiday in holidays}

    def _to_date(self, value: Optional[date | datetime]) -> Optional[date]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        return value

    def _is_business_day(self, value: date, working_weekdays: Set[int], holidays: Set[date]) -> bool:
        return value.weekday() in working_weekdays and value not in holidays

    def add_business_days(self, start_value: date | datetime, days: int) -> Optional[datetime]:
        if start_value is None:
            return None
        if days <= 0:
            return start_value if isinstance(start_value, datetime) else datetime.combine(start_value, datetime.min.time())

        start_date = self._to_date(start_value)
        if start_date is None:
            return None
        working_weekdays = self.get_working_weekdays()
        end_date = start_date
        holidays = self.get_public_holidays_between(start_date, start_date + timedelta(days=days * 7 + 14))

        added = 0
        while added < days:
            end_date = end_date + timedelta(days=1)
            if self._is_business_day(end_date, working_weekdays, holidays):
                added += 1

        if isinstance(start_value, datetime):
            return datetime.combine(end_date, start_value.time())
        return datetime.combine(end_date, datetime.min.time())

    def business_days_between(self, start_value: date | datetime, end_value: date | datetime) -> int:
        start_date = self._to_date(start_value)
        end_date = self._to_date(end_value)
        if not start_date or not end_date:
            return 0
        if end_date < start_date:
            return 0

        working_weekdays = self.get_working_weekdays()
        holidays = self.get_public_holidays_between(start_date, end_date)
        total = 0
        current = start_date
        while current < end_date:
            current = current + timedelta(days=1)
            if self._is_business_day(current, working_weekdays, holidays):
                total += 1
        return total
