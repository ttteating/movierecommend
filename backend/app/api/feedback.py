"""用户反馈接口:搜不到电影时提交反馈,管理员查看并处理。"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from tortoise.transactions import in_transaction

from app import auth
from app.models import AdminOperationLog, AdminUser, MovieFeedback, User

router = APIRouter()


class FeedbackCreate(BaseModel):
    moviename: str = Field(..., min_length=1, max_length=500, description="缺失的电影名/关键词")
    note: Optional[str] = Field(None, max_length=1000, description="补充说明:年份/导演/主演等")

    @field_validator("moviename", "note", mode="before")
    @classmethod
    def strip_fields(cls, value):
        return value.strip() if isinstance(value, str) else value


class FeedbackResolve(BaseModel):
    status: Literal["resolved", "pending"]


async def _feedback_rows(feedbacks):
    rows = await feedbacks.values("feedbackid", "user_id", "moviename", "note", "status", "created_at", "resolved_at")
    if not rows:
        return []
    user_ids = {row["user_id"] for row in rows}
    users = await User.filter(userid__in=user_ids).values("userid", "username")
    user_map = {u["userid"]: u["username"] for u in users}
    return [
        {
            "feedbackid": row["feedbackid"],
            "userid": row["user_id"],
            "username": user_map.get(row["user_id"]),
            "moviename": row["moviename"],
            "note": row["note"],
            "status": row["status"],
            "created_at": row["created_at"],
            "resolved_at": row["resolved_at"],
        }
        for row in rows
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_feedback(data: FeedbackCreate, current_user: User = Depends(auth.get_current_user)):
    fb = await MovieFeedback.create(
        user=current_user,
        moviename=data.moviename,
        note=data.note,
        status="pending",
    )
    return {"code": 201, "msg": "反馈已提交，管理员核实后将尽快补录影片", "data": {"feedbackid": fb.feedbackid, "status": fb.status}}


@router.get("/me")
async def list_my_feedback(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(auth.get_current_user),
):
    qs = MovieFeedback.filter(user_id=current_user.userid)
    total = await qs.count()
    rows = await _feedback_rows(qs.order_by("-created_at", "-feedbackid").offset((page - 1) * page_size).limit(page_size))
    return {"code": 200, "data": {"items": rows, "total": total, "page": page, "page_size": page_size}}


@router.get("/admin/list")
async def list_feedback_admin(
    feedback_status: Optional[Literal["pending", "resolved"]] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    admin: AdminUser = Depends(auth.get_current_admin),
):
    qs = MovieFeedback.all()
    if feedback_status:
        qs = qs.filter(status=feedback_status)
    total = await qs.count()
    rows = await _feedback_rows(qs.order_by("-created_at", "-feedbackid").offset((page - 1) * page_size).limit(page_size))
    return {"code": 200, "data": {"items": rows, "total": total, "page": page, "page_size": page_size}}


@router.put("/admin/{feedbackid}")
async def resolve_feedback(
    feedbackid: int,
    data: FeedbackResolve,
    admin: AdminUser = Depends(auth.get_current_admin),
):
    async with in_transaction() as connection:
        fb = await MovieFeedback.filter(feedbackid=feedbackid).using_db(connection).select_for_update().first()
        if fb is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="反馈不存在")
        from datetime import datetime, timezone

        fb.status = data.status
        fb.resolved_at = datetime.now(timezone.utc) if data.status == "resolved" else None
        await fb.save(using_db=connection, update_fields=["status", "resolved_at"])
        await AdminOperationLog.create(
            admin=admin,
            action="feedback.resolve",
            target_type="feedback",
            target_id=str(feedbackid),
            detail={"status": data.status},
            using_db=connection,
        )
    return {"code": 200, "msg": "反馈状态已更新", "data": {"feedbackid": feedbackid, "status": data.status}}
