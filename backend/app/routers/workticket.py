"""作业票接口：开票校验外委队伍准入名单，待办清单承接准入结论并可办结。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.workticket import WorkTicketService

router = APIRouter(prefix="/api/workticket", tags=["作业票管理"])

service = WorkTicketService()

LIST_FIELDS = ["作业票编号", "外委队伍名称", "外委队伍信用代码", "作业内容", "作业区域", "计划日期", "状态"]
STATUSES = ["待开工", "作业中", "已叫停", "已完工"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按作业票编号、队伍名称或信用代码检索"),
    status: str | None = Query(default=None, description="待开工、作业中、已叫停、已完工"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按条件过滤作业票列表；读取前同步一次准入名单的到期退出。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出作业票清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "workticket", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单张作业票明细（含待办清单）；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"作业票 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """开具作业票：引用的外委队伍必须在准入名单内，否则当场拒绝并说明原因。"""
    entry, message = service.create_entry(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=f"作业票 {entry['作业票编号']} 已开具", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """开工、叫停、完工、办结待办；有未办结待办时不能开工。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
