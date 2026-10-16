"""Tenant-scoped structured feedback and reviewed dataset endpoints."""
import uuid
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.auth import require_roles
from app.db import get_db
from app.models import QaItem, User
from app.quality_models import QualityFeedback
from app.services import quality_feedback as service

router=APIRouter(prefix='/quality')


def identifier(raw):
    try: return uuid.UUID(raw)
    except ValueError: raise service.error('not_found','找不到資料',404)


def own_qa(db,user,raw):
    row=db.scalar(select(QaItem).where(QaItem.id==identifier(raw),QaItem.org_id==user.org_id))
    if row is None or (row.user_id != user.id and user.role not in ('admin','supervisor')):
        raise service.error('not_found','找不到資料',404)
    return row


@router.post('/qa/{qa_id}/feedback')
def submit(qa_id:str,body:service.Correction,user:User=Depends(require_roles('caregiver','supervisor','admin')),
           db:Session=Depends(get_db)):
    row=service.submit(db,own_qa(db,user,qa_id),user,body)
    return {'id':str(row.id),'status':row.status,'revision':row.revision}


@router.get('/qa/{qa_id}/feedback')
def mine(qa_id:str,user:User=Depends(require_roles('caregiver','supervisor','admin')),db:Session=Depends(get_db)):
    item=own_qa(db,user,qa_id)
    row=db.scalar(select(QualityFeedback).where(QualityFeedback.qa_id==item.id,QualityFeedback.submitted_by==user.id))
    return {'id':str(row.id),'status':row.status} if row else None


@router.get('/feedback')
def list_feedback(status:Literal['pending_review','verified','rejected']|None=None,
                  gold_readiness:Literal['ready','needs_review','not_eligible']|None=None, gold_queue:bool=False,
                  user:User=Depends(require_roles('supervisor','admin')),db:Session=Depends(get_db)):
    query=select(QualityFeedback).where(QualityFeedback.org_id==user.org_id)
    if gold_queue:
        if user.role != 'admin': raise service.error('gold_admin_only','Gold queue 僅限管理員',403)
        status='verified'; gold_readiness='needs_review'
    if status: query=query.where(QualityFeedback.status==status)
    rows=list(db.scalars(query.order_by(QualityFeedback.created_at.desc())))
    if gold_readiness: rows=[r for r in rows if service.gold_readiness(r)['state']==gold_readiness]
    if gold_queue: rows.sort(key=lambda r: (service.gold_priority(r),r.created_at,str(r.id)))
    return [service.out(r,user) for r in rows[:200]]


@router.get('/gold/stats')
def gold_stats(user:User=Depends(require_roles('admin')),db:Session=Depends(get_db)):
    counts={'pending_review':0,'needs_review':0,'ready':0,'not_eligible':0}
    for row in db.scalars(select(QualityFeedback).where(QualityFeedback.org_id==user.org_id)):
        if row.status=='pending_review': counts['pending_review']+=1
        elif row.status=='verified': counts[service.gold_readiness(row)['state']]+=1
    return counts


@router.get('/feedback/{feedback_id}')
def detail(feedback_id:str,user:User=Depends(require_roles('supervisor','admin')),db:Session=Depends(get_db)):
    row=db.scalar(select(QualityFeedback).where(QualityFeedback.id==identifier(feedback_id),QualityFeedback.org_id==user.org_id))
    if row is None: raise service.error('not_found','找不到資料',404)
    return dict(service.out(row,user),review_history=service.review_history(db,row))


@router.post('/feedback/{feedback_id}/review')
def review(feedback_id:str,body:service.ReviewIn,user:User=Depends(require_roles('supervisor','admin')),db:Session=Depends(get_db)):
    row=db.scalar(select(QualityFeedback).where(QualityFeedback.id==identifier(feedback_id),QualityFeedback.org_id==user.org_id).with_for_update())
    if row is None: raise service.error('not_found','找不到資料',404)
    return service.out(service.review(db,row,user,body),user)


@router.get('/dataset/export')
def export(format:Literal['json','jsonl','csv']='json',user:User=Depends(require_roles('supervisor','admin')),db:Session=Depends(get_db)):
    body=service.encode_export(service.export_records(db,user),format)
    media={'json':'application/json','jsonl':'application/x-ndjson','csv':'text/csv'}[format]
    return Response(content=body,media_type=media,headers={'Content-Disposition':f'attachment; filename="quality-verified.{format}"'})


@router.get('/dataset/gold/export')
def export_gold(format:Literal['json','jsonl','csv']='json',user:User=Depends(require_roles('admin')),db:Session=Depends(get_db)):
    body=service.encode_export(service.export_records(db,user,gold=True),format)
    media={'json':'application/json','jsonl':'application/x-ndjson','csv':'text/csv'}[format]
    return Response(content=body,media_type=media,headers={'Content-Disposition':f'attachment; filename="quality-gold.{format}"'})
