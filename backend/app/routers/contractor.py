"""外委队伍准入接口：台账查询、补录建档、审核动作、备案管理与审核留痕。

操作人身份经 X-Operator-Name 请求头传入（前端对中文名做了 URL 编码）；
读取 类接口不做单位限制（跨单位可查看），写操作在 service 层做授权校验。
"""
from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from fastapi import APIRouter, Header, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.contractor import ContractorService

router = APIRouter(prefix="/api/contractor", tags=["外委队伍准入"])

service = ContractorService()

LIST_FIELDS = ["统一社会信用代码", "队伍名称", "归属单位", "资质有效期至", "协议有效期至", "进场时间", "准入状态"]
STATUSES = ["待审核", "准入有效", "已退回", "已撤回", "已退出（证件过期）"]


def _operator(x_operator_name: str | None) -> str:
    return unquote(x_operator_name or "").strip() or "值班管理员"


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按信用代码或队伍名称检索"),
    status: str | None = Query(default=None, description="待审核、准入有效、已退回、已撤回、已退出（证件过期）"),
    unit: str | None = Query(default=None, description="按归属安全管理单位过滤"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按条件过滤外委队伍台账；读取前先把证件过期的在册队伍移出名单。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, unit=unit, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats")
def stats() -> dict[str, int]:
    """准入有效、待审核、已退出与临期预警的汇总卡片数据。"""
    return service.stats()


@router.get("/identity")
def identity(name: str = Query(default="", description="安全员姓名")) -> dict[str, Any]:
    """解析某人当前归属单位：同一个人挂多家单位时以最近一次备案为准，备案全程留痕。"""
    return service.identity(name.strip())


@router.get("/filings")
def list_filings() -> dict[str, Any]:
    """备案列表：全量备案记录 + 每个人按最近一次备案解析出的当前归属。"""
    filings = service.filings()
    current: dict[str, str] = {}
    for row in filings:
        current[str(row.get("安全员姓名"))] = str(row.get("归属单位"))
    return {"total": len(filings), "items": filings, "当前归属": current}


@router.post("/filings", response_model=ActionResult)
def add_filing(payload: EntryPayload) -> ActionResult:
    """新增一条人员单位备案；旧备案保留作留痕，归属自动切换到最近一次。"""
    entry, message = service.add_filing(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=f"已备案：{entry['安全员姓名']} 现归属{entry['归属单位']}", entry=entry)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出外委队伍准入台账：返回当前全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "contractor", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单支队伍明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"外委队伍 {entry_id} 不存在或已归档")
    return entry


@router.get("/{entry_id}/reviews")
def list_reviews(entry_id: int) -> dict[str, Any]:
    """审核留痕：每次提交、撤回、结论都按当时的材料快照保留。"""
    if service.get_entry(entry_id) is None:
        raise HTTPException(status_code=404, detail=f"外委队伍 {entry_id} 不存在或已归档")
    items = service.reviews(entry_id)
    return {"total": len(items), "items": items}


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload, x_operator_name: str | None = Header(default=None)) -> ActionResult:
    """补录建档：按统一社会信用代码唯一建档，归属单位取操作人当前备案单位。"""
    entry, message = service.create_entry(payload.values, _operator(x_operator_name))
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=f"外委队伍已建档（{entry['status']}）", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(
    entry_id: int,
    payload: EntryPayload,
    x_operator_name: str | None = Header(default=None),
) -> ActionResult:
    """提交审核、撤回、审核通过、审核退回；越权当场拒绝并写明缺哪项授权。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values, _operator(x_operator_name))
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
