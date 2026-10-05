"""作业票接口：开票引用准入名单校验、开工完工流转与准入结论待办清单。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.workticket import WorkticketService

router = APIRouter(prefix="/api/workticket", tags=["作业票"])

service = WorkticketService()


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按作业票编号检索"),
    status: str | None = Query(default=None, description="待开工、已开工、已完工"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按作业票编号与状态过滤列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/todos", response_model=dict)
def list_todos(all: bool = Query(default=False, description="为 true 时连已办结一起返回")) -> dict[str, Any]:
    """准入结论待办清单：审核通过、到期退出、撤回、续期待审都会同步到这里。"""
    return {"items": service.list_todos(only_open=not all)}


@router.post("/todos/{todo_id}/actions", response_model=ActionResult)
def close_todo(todo_id: int) -> ActionResult:
    """办结一条准入待办；已办结的重复处理会被拦下。"""
    todo, message = service.close_todo(todo_id)
    if todo is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=todo)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出作业票清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "workticket", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单张作业票明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"作业票 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """开具作业票：引用的外委队伍必须在准入名单内，否则当场拒绝。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"开票被拒绝：{'、'.join(missing)}")
    return ActionResult(ok=True, message="作业票已开具", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单张作业票执行开工、完工；开工前会复核队伍是否仍在准入名单内。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
