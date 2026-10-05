"""外委队伍准入接口：建档补录、提交审核、资质续期、撤回，以及安全员备案留痕。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.contractor import ACTIONS, REQUIRED_FIELDS, STATUS_ORDER, ContractorService

router = APIRouter(prefix="/api/contractor", tags=["外委队伍准入"])

service = ContractorService()


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按队伍名称或统一社会信用代码检索"),
    status: str | None = Query(default=None, description="待审核、准入有效、已退出"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按关键字与状态过滤准入台账；列表读取时会先把两证过期的队伍移出名单。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    if status and status not in STATUS_ORDER:
        raise HTTPException(status_code=400, detail=f"状态「{status}」不在允许的状态序列里")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/filings", response_model=dict)
def list_filings(operator: str | None = Query(default=None, description="按安全员姓名过滤")) -> dict[str, Any]:
    """安全员备案记录：一人挂多家单位时以最近一次备案为准，历史全部留痕。"""
    return {"items": service.filings(operator)}


@router.post("/filings", response_model=ActionResult)
def create_filing(payload: EntryPayload) -> ActionResult:
    """新增一条安全员单位备案；旧备案不删除，归属判定自动以最新一条为准。"""
    filing, missing = service.file_operator(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="备案已登记，归属以最近一次备案为准", entry=filing)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出准入台账：返回当前全量队伍清单。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "contractor", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单支队伍明细；任何单位都可查看，改动只能走动作接口。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"外委队伍 {entry_id} 不存在或已归档")
    return entry


@router.get("/{entry_id}/reviews", response_model=dict)
def list_reviews(entry_id: int) -> dict[str, Any]:
    """审核历史：每条记录封存当时的材料快照，续期重审不会回写历史结论。"""
    if service.get_entry(entry_id) is None:
        raise HTTPException(status_code=404, detail=f"外委队伍 {entry_id} 不存在或已归档")
    return {"items": service.reviews(entry_id)}


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记或补录一支外委队伍；统一社会信用代码重复时拒绝建档。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        if all(item in REQUIRED_FIELDS for item in missing):
            return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
        return ActionResult(ok=False, message="；".join(missing))
    return ActionResult(ok=True, message=f"外委队伍已{entry['来源']}建档，待提交准入审核", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """提交审核、资质续期、撤回；越权提交当场拒绝并写明缺哪项授权。"""
    action = str(payload.values.get("action") or "").strip()
    if action not in ACTIONS:
        return ActionResult(ok=False, message=f"动作「{action}」不属于外委队伍准入可执行范围")
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
