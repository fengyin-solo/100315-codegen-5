"""作业票业务规则：开票引用校验与准入结论待办清单。

作业票引用外委队伍时，队伍必须在准入名单内（准入有效）；准入结论由
contractor 服务同步进待办清单，这里负责展示与办结。
"""
from __future__ import annotations

from typing import Any

from app.services.contractor import ContractorService
from app.store import store

MODULE = "workticket"
TODO_TABLE = "workticket_todo"
REQUIRED_FIELDS = ["作业票编号", "统一社会信用代码", "作业地点", "作业内容", "计划日期"]
STATUS_ORDER = ["待开工", "已开工", "已完工"]
ACTION_RULES = {"开工": "已开工", "完工": "已完工"}

contractors = ContractorService()


class WorkticketService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("作业票编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        credit_code = str(values["统一社会信用代码"]).strip()
        team = contractors.find_by_credit_code(credit_code)
        if team is None:
            return None, [f"统一社会信用代码 {credit_code} 未建档，名单外队伍不允许被作业票引用"]
        if team.get("status") != "准入有效":
            return None, [f"队伍「{team.get('队伍名称')}」当前为准入{team.get('status')}状态，不在准入名单内，不允许被作业票引用"]
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in REQUIRED_FIELDS:
            entry[field] = str(values.get(field) or "").strip()
        entry["队伍名称"] = team.get("队伍名称")
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"作业票 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于作业票可执行范围"
        target = ACTION_RULES[action]
        if target == "已开工":
            team = contractors.find_by_credit_code(str(entry.get("统一社会信用代码", "")))
            if team is None or team.get("status") != "准入有效":
                return None, f"队伍「{entry.get('队伍名称')}」已不在准入名单内，作业票不能开工"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        return entry, f"作业票已{action}"

    # ---- 待办清单 ----

    def list_todos(self, *, only_open: bool = True) -> list[dict[str, Any]]:
        rows = store.rows(TODO_TABLE)
        if only_open:
            rows = [row for row in rows if row.get("状态") == "待办"]
        return sorted(rows, key=lambda row: (str(row.get("时间", "")), int(row.get("id", 0))), reverse=True)

    def close_todo(self, todo_id: int) -> tuple[dict[str, Any] | None, str]:
        todo = store.find(TODO_TABLE, todo_id)
        if todo is None:
            return None, f"待办 {todo_id} 不存在或已办结"
        if todo.get("状态") != "待办":
            return None, "该待办已办结，无需重复处理"
        todo["状态"] = "已办"
        todo["pending"] = False
        return todo, "待办已办结"
