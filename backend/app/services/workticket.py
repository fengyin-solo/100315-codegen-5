"""作业票业务规则：开票引用外委队伍时强校验准入名单，待办清单承接准入结论。

名单外的队伍（未建档、待审核、已退回、已撤回、已退出）一律不允许被作业票引用；
准入台账的结论（通过、退回、到期退出）由 ContractorService 写入待办清单，这里负责办结。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.contractor import ContractorService
from app.store import store

MODULE = "workticket"
REQUIRED_FIELDS = ["外委队伍信用代码", "作业内容", "作业区域", "计划日期"]
STATUSES = ["待开工", "作业中", "已叫停", "已完工"]
ACTIONS = ["开工", "叫停", "完工", "办结待办"]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


class WorkTicketService:
    def __init__(self) -> None:
        self.contractors = ContractorService()

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        self.contractors.sync_expired()
        rows = list(store.rows(MODULE))
        if keyword:
            rows = [
                row for row in rows
                if keyword in str(row.get("作业票编号", ""))
                or keyword in str(row.get("外委队伍名称", ""))
                or keyword in str(row.get("外委队伍信用代码", ""))
            ]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        rows.sort(key=lambda row: int(row.get("id", 0)))
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        self.contractors.sync_expired()
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        self.contractors.sync_expired()
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        code = str(values["外委队伍信用代码"]).strip().upper()
        team = next((row for row in store.rows("contractor") if str(row.get("统一社会信用代码")) == code), None)
        if team is None:
            return None, f"统一社会信用代码 {code} 未在准入台账建档，名单外的队伍不允许被作业票引用"
        if team.get("status") != "准入有效":
            return None, (
                f"队伍《{team.get('队伍名称')}》当前为准入状态「{team.get('status')}」，"
                "不在准入名单内，作业票不得引用"
            )
        rows = store.rows(MODULE)
        number = str(values.get("作业票编号") or "").strip()
        if not number:
            number = f"ZYP-{datetime.now():%Y}-{max((int(row.get('id', 0)) for row in rows), default=0) + 1:04d}"
        if any(str(row.get("作业票编号")) == number for row in rows):
            return None, f"作业票编号 {number} 已存在，请更换编号"
        entry = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "作业票编号": number,
            "外委队伍信用代码": code,
            "外委队伍名称": team.get("队伍名称"),
            "作业内容": str(values["作业内容"]).strip(),
            "作业区域": str(values["作业区域"]).strip(),
            "计划日期": str(values["计划日期"]).strip(),
            "status": "待开工",
            "pending": True,
            "abnormal": False,
            "待办清单": [{
                "内容": f"外委队伍准入核验：准入有效（资质至{team.get('资质有效期至')}，协议至{team.get('协议有效期至')}）",
                "状态": "已完成",
                "来源": "准入台账",
                "时间": _now(),
            }],
        }
        rows.append(entry)
        return entry, ""

    def run_action(self, entry_id: int, action: str, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        self.contractors.sync_expired()
        ticket = store.find(MODULE, entry_id)
        if ticket is None:
            return None, f"作业票 {entry_id} 不存在或已归档"
        if action not in ACTIONS:
            return None, f"动作「{action}」不属于作业票可执行范围"
        if action == "办结待办":
            return self._close_todo(ticket, values)
        if ticket.get("status") == "已完工":
            return None, "作业票已完工，不能再变更状态"
        if action == "开工":
            if ticket.get("status") != "待开工":
                return None, f"当前状态「{ticket.get('status')}」不可开工"
            open_todos = [todo for todo in ticket.get("待办清单", []) if todo.get("状态") == "待办"]
            if open_todos:
                return None, f"还有 {len(open_todos)} 条待办未办结（最新：{open_todos[-1].get('内容')}），不能开工"
            ticket["status"] = "作业中"
            return ticket, "作业票已开工"
        if action == "叫停":
            ticket["status"] = "已叫停"
            ticket["pending"] = True
            ticket["abnormal"] = True
            return ticket, "作业票已叫停"
        ticket["status"] = "已完工"
        ticket["pending"] = False
        return ticket, "作业票已完工"

    def _close_todo(self, ticket: dict[str, Any], values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        todos = ticket.get("待办清单", [])
        try:
            index = int(values.get("待办序号"))
        except (TypeError, ValueError):
            return None, "办结待办需要带上待办序号"
        if index < 0 or index >= len(todos):
            return None, f"待办序号 {index} 超出范围（共 {len(todos)} 条）"
        todo = todos[index]
        if todo.get("状态") != "待办":
            return None, "该待办已办结，请勿重复操作"
        todo["状态"] = "已完成"
        todo["办结时间"] = _now()
        if not any(item.get("状态") == "待办" for item in todos):
            ticket["pending"] = ticket.get("status") not in ("已完工",)
            ticket["abnormal"] = False
        return ticket, f"待办「{todo.get('内容')}」已办结"
