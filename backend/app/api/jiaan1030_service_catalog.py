"""10/30 Jiaan BA/GA/SC catalog API. No clinical/patient data."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.auth import require_roles
from app.db import get_db
from app.models import User
from app.services import audit

router = APIRouter()
ALL = ('caregiver', 'supervisor', 'director', 'admin')
REVIEWERS = ('supervisor', 'director', 'admin')
APPROVERS = ('director', 'admin')


def _catalog(db: Session, reviewed_only: bool):
    filter_clause = ' WHERE reviewed = TRUE' if reviewed_only else ''
    rows = db.execute(text('SELECT slot, code, name, reviewed FROM jiaan1030_ba_services'
                           + filter_clause + ' ORDER BY slot')).mappings().all()
    forms = db.execute(text('SELECT code, title, fields_json, reviewed, schema_status FROM jiaan1030_service_forms'
                            + (" WHERE reviewed = TRUE AND schema_status = 'approved'" if reviewed_only else '') + ' ORDER BY code')).mappings().all()
    return {
        'ba_services': [dict(slot=r['slot'], code=r['code'], name=r['name'], reviewed=r['reviewed']) for r in rows],
        'service_forms': [dict(code=r['code'], title=r['title'], fields=r['fields_json'], reviewed=r['reviewed'],
                               schema_status=r['schema_status']) for r in forms],
        'notice': 'Only reviewed content is displayed' if reviewed_only else 'Unreviewed metadata for authorized staff only',
    }


@router.get('/jiaan1030/service-catalog')
def public_catalog(user: User = Depends(require_roles(*ALL)), db: Session = Depends(get_db)) -> dict:
    """Authenticated staff; hide every unreviewed record."""
    return _catalog(db, reviewed_only=True)


@router.get('/jiaan1030/service-catalog/review')
def review_catalog(user: User = Depends(require_roles(*REVIEWERS)), db: Session = Depends(get_db)) -> dict:
    """Supervisors/director/admin may inspect draft metadata, no write operations."""
    return _catalog(db, reviewed_only=False)


class ApproveBaServiceBody(BaseModel):
    reviewed: bool


@router.post('/jiaan1030/ba-services/{code}/approve')
def approve_ba_service(code: str, body: ApproveBaServiceBody, user: User = Depends(require_roles(*APPROVERS)),
                       db: Session = Depends(get_db)) -> dict:
    """主任/admin 核准（或撤銷核准）單一 BA 服務項目名稱／代碼；只切換 reviewed 旗標，不改名稱或代碼。"""
    result = db.execute(text('UPDATE jiaan1030_ba_services SET reviewed = :v WHERE code = :code'),
                        {'v': body.reviewed, 'code': code})
    if result.rowcount != 1:
        raise HTTPException(status_code=404, detail={'code': 'not_found', 'message': '找不到此 BA 服務項目'})
    audit.record(db, 'jiaan1030_ba_service.approve', actor=user, target_type='jiaan1030_ba_service',
                target_id=code, meta={'code': code, 'status_to': 'reviewed' if body.reviewed else 'unreviewed'})
    db.commit()
    row = db.execute(text('SELECT slot, code, name, reviewed FROM jiaan1030_ba_services WHERE code = :code'),
                     {'code': code}).mappings().one()
    return dict(row)
