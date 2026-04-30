from __future__ import annotations
import re
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session
from fastapi import status

from app.models.lookup import LookupOption, LookupOptionKeyword, LookupSet
from app.schemas.lookup import LookupResolveResponse
from app.services.error_handler import AppException, handle_not_found

_NORM_RE = re.compile(r"[^a-z0-9]+")


def _norm(s: str) -> str:
    return _NORM_RE.sub(" ", (s or "").lower()).strip()


class LookupResolverService:
    def __init__(self, db: Session):
        self.db = db

    def _set(self, set_key: str) -> LookupSet:
        s = self.db.query(LookupSet).filter(LookupSet.set_key == set_key).first()
        if not s:
            raise handle_not_found("LookupSet", set_key)
        return s

    def resolve(self, set_key: str, raw: str, locale: Optional[str] = None) -> LookupResolveResponse:
        s = self._set(set_key)
        raw_lower = (raw or "").strip().lower()
        if not raw_lower:
            raise AppException(status_code=status.HTTP_404_NOT_FOUND,
                               message=f"Could not resolve '{raw}' in {set_key}",
                               code="lookup_unresolved")

        # 1. exact value (case-sensitive first, then case-insensitive when the raw input
        #    already equals the stored value without any casing transformation)
        raw_stripped = (raw or "").strip()
        opt = self.db.query(LookupOption).filter(
            LookupOption.set_id == s.id, LookupOption.is_active.is_(True),
            LookupOption.value == raw_stripped,
        ).first()
        if opt:
            return LookupResolveResponse(value=opt.value, label=opt.label,
                                         matched_keyword=None, match_type="exact_value", score=1.0)

        # 2. exact label
        opt = self.db.query(LookupOption).filter(
            LookupOption.set_id == s.id, LookupOption.is_active.is_(True),
            func.lower(LookupOption.label) == raw_lower,
        ).first()
        if opt:
            return LookupResolveResponse(value=opt.value, label=opt.label,
                                         matched_keyword=None, match_type="exact_label", score=0.95)

        # 3. exact keyword
        kq = self.db.query(LookupOptionKeyword, LookupOption).join(
            LookupOption, LookupOption.id == LookupOptionKeyword.option_id
        ).filter(
            LookupOption.set_id == s.id, LookupOption.is_active.is_(True),
            func.lower(LookupOptionKeyword.keyword) == raw_lower,
        )
        if locale:
            kq = kq.filter((LookupOptionKeyword.locale == locale) | (LookupOptionKeyword.locale.is_(None)))
        row = kq.first()
        if row:
            kw, opt = row
            return LookupResolveResponse(value=opt.value, label=opt.label,
                                         matched_keyword=kw.keyword, match_type="exact_keyword", score=0.9)

        # 4. normalized
        norm = _norm(raw)
        if norm:
            options = self.db.query(LookupOption).filter(
                LookupOption.set_id == s.id, LookupOption.is_active.is_(True),
            ).all()
            for o in options:
                if _norm(o.value) == norm or _norm(o.label) == norm:
                    return LookupResolveResponse(value=o.value, label=o.label,
                                                 matched_keyword=None, match_type="normalized", score=0.8)
            kws = self.db.query(LookupOptionKeyword, LookupOption).join(
                LookupOption, LookupOption.id == LookupOptionKeyword.option_id
            ).filter(LookupOption.set_id == s.id, LookupOption.is_active.is_(True)).all()
            for k, o in kws:
                if _norm(k.keyword) == norm:
                    return LookupResolveResponse(value=o.value, label=o.label,
                                                 matched_keyword=k.keyword, match_type="normalized", score=0.8)

        raise AppException(status_code=status.HTTP_404_NOT_FOUND,
                           message=f"Could not resolve '{raw}' in {set_key}",
                           code="lookup_unresolved")
