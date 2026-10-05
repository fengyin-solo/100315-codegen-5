"""外委队伍准入业务规则：建档、有效期管控、分单位授权与审核留痕都收在这里。

准入名单判定口径：资质证书与安全协议任一过期即退出名单；名单外队伍不允许被作业票引用。
授权口径：只有队伍归属单位的安全员（以最近一次备案为准）能提交审核、撤回和续期。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "contractor"
REVIEW_TABLE = "contractor_review"
FILING_TABLE = "contractor_filing"
TODO_TABLE = "workticket_todo"

REQUIRED_FIELDS = ["统一社会信用代码", "队伍名称", "归属单位", "资质证书编号", "资质到期日", "安全协议编号", "协议到期日", "进场时间"]
STATUS_ORDER = ["待审核", "准入有效", "已退出"]
ACTIONS = ["提交审核", "资质续期", "撤回"]
EXPIRING_SOON_DAYS = 30


def _today() -> date:
    return date.today()


def _parse_day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or "").strip())
    except ValueError:
        return None


def _expired_items(entry: dict[str, Any], today: date) -> list[str]:
    """返回已经过期的材料说明；空列表表示两证都在有效期内。"""
    expired: list[str] = []
    for label, field in (("资质证书", "资质到期日"), ("安全协议", "协议到期日")):
        day = _parse_day(entry.get(field))
        if day is None or day < today:
            shown = entry.get(field) or "未登记"
            expired.append(f"{label}（{shown}）")
    return expired


def _next_id(table: str) -> int:
    return max((int(row.get("id", 0)) for row in store.rows(table)), default=0) + 1


def _append_review(entry: dict[str, Any], *, operator: str, unit: str, conclusion: str, note: str) -> dict[str, Any]:
    """写一条审核记录：材料快照按当时状态封存，后续续期不会回写历史。"""
    review = {
        "id": _next_id(REVIEW_TABLE),
        "队伍id": entry["id"],
        "统一社会信用代码": entry.get("统一社会信用代码"),
        "队伍名称": entry.get("队伍名称"),
        "审核时间": str(_today()),
        "操作人": operator,
        "操作人单位": unit,
        "结论": conclusion,
        "材料快照": {
            "资质证书编号": entry.get("资质证书编号"),
            "资质到期日": entry.get("资质到期日"),
            "安全协议编号": entry.get("安全协议编号"),
            "协议到期日": entry.get("协议到期日"),
        },
        "备注": note,
    }
    store.rows(REVIEW_TABLE).append(review)
    return review


def _sync_ticket_todo(entry: dict[str, Any], *, conclusion: str, content: str) -> None:
    """把准入结论同步到作业票待办清单，作业票侧按待办跟进处置。"""
    store.rows(TODO_TABLE).append({
        "id": _next_id(TODO_TABLE),
        "时间": str(_today()),
        "来源": "准入审核",
        "统一社会信用代码": entry.get("统一社会信用代码"),
        "队伍名称": entry.get("队伍名称"),
        "结论": conclusion,
        "内容": content,
        "状态": "待办",
        "pending": True,
        "abnormal": conclusion != "通过",
    })


class ContractorService:
    """外委队伍准入台账：一支队伍按统一社会信用代码建档。"""

    # ---- 查询 ----

    def refresh_expiry(self) -> int:
        """把两证任一过期的在册队伍移出准入名单，并留系统审核记录、同步待办。"""
        today = _today()
        changed = 0
        for entry in store.rows(MODULE):
            if entry.get("status") != "准入有效":
                continue
            expired = _expired_items(entry, today)
            if not expired:
                continue
            entry["status"] = "已退出"
            entry["pending"] = False
            entry["abnormal"] = True
            note = f"{'、'.join(expired)}已过期，自动退出准入名单"
            _append_review(entry, operator="系统", unit="系统", conclusion="到期退出", note=note)
            _sync_ticket_todo(entry, conclusion="到期退出", content=f"{entry.get('队伍名称')}{note}，相关作业票不得再引用该队伍")
            changed += 1
        return changed

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        self.refresh_expiry()
        rows = store.rows(MODULE)
        if keyword:
            rows = [
                row for row in rows
                if keyword in str(row.get("队伍名称", "")) or keyword in str(row.get("统一社会信用代码", ""))
            ]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        rows = sorted(rows, key=lambda row: str(row.get("进场时间", "")))
        today = _today()
        for row in rows:
            row["临期"] = self._expiring_soon(row, today)
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        self.refresh_expiry()
        entry = store.find(MODULE, entry_id)
        if entry is not None:
            entry["临期"] = self._expiring_soon(entry, _today())
        return entry

    def find_by_credit_code(self, credit_code: str) -> dict[str, Any] | None:
        self.refresh_expiry()
        for row in store.rows(MODULE):
            if str(row.get("统一社会信用代码", "")) == credit_code:
                return row
        return None

    def reviews(self, entry_id: int) -> list[dict[str, Any]]:
        return [row for row in store.rows(REVIEW_TABLE) if int(row.get("队伍id", 0)) == entry_id]

    def _expiring_soon(self, entry: dict[str, Any], today: date) -> bool:
        if entry.get("status") != "准入有效":
            return False
        for field in ("资质到期日", "协议到期日"):
            day = _parse_day(entry.get(field))
            if day is not None and 0 <= (day - today).days <= EXPIRING_SOON_DAYS:
                return True
        return False

    # ---- 建档与补录 ----

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        credit_code = str(values["统一社会信用代码"]).strip()
        if self.find_by_credit_code(credit_code) is not None:
            return None, [f"统一社会信用代码 {credit_code} 已建档，一支队伍只建一档"]
        backfill = bool(values.get("补录"))
        entry = {"id": _next_id(MODULE)}
        for field in REQUIRED_FIELDS:
            entry[field] = str(values.get(field) or "").strip()
        entry["来源"] = "补录" if backfill else "新登记"
        entry["status"] = "待审核"
        entry["pending"] = True
        entry["abnormal"] = False
        store.rows(MODULE).append(entry)
        note = "存量队伍按进场时间补录建档" if backfill else "新队伍登记建档"
        _append_review(entry, operator=str(values.get("操作人") or "系统"), unit=str(values.get("归属单位") or ""), conclusion="登记", note=note)
        _sync_ticket_todo(entry, conclusion="待审核", content=f"{entry.get('队伍名称')}已{entry['来源']}建档，待归属单位安全员提交准入审核")
        return entry, []

    # ---- 授权 ----

    def current_unit(self, operator: str) -> str | None:
        """一人挂多家单位时，以最近一次备案为准；历史备案全部保留备查。"""
        filings = [row for row in store.rows(FILING_TABLE) if row.get("安全员") == operator]
        if not filings:
            return None
        latest = max(filings, key=lambda row: (str(row.get("备案时间", "")), int(row.get("id", 0))))
        return str(latest.get("单位") or "")

    def filings(self, operator: str | None = None) -> list[dict[str, Any]]:
        rows = store.rows(FILING_TABLE)
        if operator:
            rows = [row for row in rows if row.get("安全员") == operator]
        return sorted(rows, key=lambda row: (str(row.get("备案时间", "")), int(row.get("id", 0))), reverse=True)

    def file_operator(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in ("安全员", "单位") if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        filing = {
            "id": _next_id(FILING_TABLE),
            "安全员": str(values["安全员"]).strip(),
            "单位": str(values["单位"]).strip(),
            "备案时间": str(values.get("备案时间") or _today()),
        }
        store.rows(FILING_TABLE).append(filing)
        return filing, []

    def _missing_auth(self, entry: dict[str, Any], operator: str) -> list[str]:
        """越权判定：返回缺哪几项授权；空列表表示有权操作。"""
        if not operator:
            return ["操作人身份（请在页面顶部选择当前安全员）"]
        unit = self.current_unit(operator)
        if unit is None:
            return [f"安全员备案（{operator}未在任何安全管理单位备案）"]
        if unit != entry.get("归属单位"):
            return [f"「{entry.get('归属单位')}」安全员授权（{operator}当前备案单位为「{unit}」，跨单位仅可查看）"]
        return []

    # ---- 动作 ----

    def run_action(self, entry_id: int, action: str, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"外委队伍 {entry_id} 不存在或已归档"
        if action not in ACTIONS:
            return None, f"动作「{action}」不属于外委队伍准入可执行范围"
        operator = str(values.get("操作人") or "").strip()
        missing_auth = self._missing_auth(entry, operator)
        if missing_auth:
            return None, f"越权提交已拒绝，缺少授权：{'；'.join(missing_auth)}"
        if action == "提交审核":
            return self._submit_review(entry, operator)
        if action == "资质续期":
            return self._renew(entry, operator, values)
        return self._withdraw(entry, operator)

    def _submit_review(self, entry: dict[str, Any], operator: str) -> tuple[dict[str, Any] | None, str]:
        expired = _expired_items(entry, _today())
        if expired:
            return None, f"{'、'.join(expired)}已过期，不能通过准入审核；请先办理资质续期再重新提交"
        if entry.get("status") == "准入有效":
            return None, "该队伍已在准入名单内，无需重复提交审核"
        entry["status"] = "准入有效"
        entry["pending"] = False
        entry["abnormal"] = False
        unit = self.current_unit(operator) or ""
        _append_review(entry, operator=operator, unit=unit, conclusion="通过", note="材料齐全且两证在有效期内，准予准入")
        _sync_ticket_todo(entry, conclusion="通过", content=f"{entry.get('队伍名称')}准入审核通过，作业票可正常引用该队伍")
        return entry, "准入审核通过，队伍已进入准入名单"

    def _renew(self, entry: dict[str, Any], operator: str, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        today = _today()
        renewed: list[str] = []
        for label, field in (("资质证书", "资质到期日"), ("安全协议", "协议到期日")):
            new_day = str(values.get(field) or "").strip()
            if not new_day:
                continue
            parsed = _parse_day(new_day)
            if parsed is None:
                return None, f"{label}新有效期「{new_day}」不是有效日期（应为 YYYY-MM-DD）"
            if parsed < today:
                return None, f"{label}新有效期 {new_day} 早于今天，续期日期必须晚于今天"
            entry[field] = new_day
            renewed.append(f"{label}续期至 {new_day}")
        if not renewed:
            return None, "缺少续期内容：请至少提供资质到期日或协议到期日的新有效期"
        entry["status"] = "待审核"
        entry["pending"] = True
        entry["abnormal"] = False
        unit = self.current_unit(operator) or ""
        _append_review(entry, operator=operator, unit=unit, conclusion="续期登记", note="；".join(renewed) + "，需重新走一遍准入审核")
        _sync_ticket_todo(entry, conclusion="待审核", content=f"{entry.get('队伍名称')}{'；'.join(renewed)}，重新准入审核通过前作业票不得引用")
        return entry, "续期已登记，队伍回到待审核状态，需重新提交准入审核"

    def _withdraw(self, entry: dict[str, Any], operator: str) -> tuple[dict[str, Any] | None, str]:
        if entry.get("status") == "已退出":
            return None, "该队伍已退出准入名单，无需重复撤回"
        entry["status"] = "已退出"
        entry["pending"] = False
        entry["abnormal"] = True
        unit = self.current_unit(operator) or ""
        _append_review(entry, operator=operator, unit=unit, conclusion="撤回", note="安全员撤回准入，队伍退出准入名单")
        _sync_ticket_todo(entry, conclusion="撤回", content=f"{entry.get('队伍名称')}被撤回准入，相关作业票不得再引用该队伍")
        return entry, "已撤回准入，队伍退出准入名单"
