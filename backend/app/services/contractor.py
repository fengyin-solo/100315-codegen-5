"""外委队伍准入业务规则：建档、有效期值守、分单位授权与审核留痕。

规则要点：
- 队伍按统一社会信用代码建档，全库唯一，存量队伍按进场时间补录排序；
- 资质证书、安全协议任一过期即退出准入名单：读取时惰性核对，退出即留痕，
  并给引用该队伍的未完工作业票写入待办；
- 提交、撤回、审核只有队伍归属单位的安全员能操作，归属以最近一次备案为准，
  越权当场拒绝并写明缺哪项授权；
- 每次审核都把当时的材料快照写进留痕，历史结论不随续期变化。
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.store import store

MODULE = "contractor"
REVIEW_MODULE = "contractor_review"
FILING_MODULE = "contractor_filing"
TICKET_MODULE = "workticket"

REQUIRED_FIELDS = ["队伍名称", "统一社会信用代码", "资质证书编号", "资质有效期至", "安全协议编号", "协议有效期至", "进场时间"]
MATERIAL_FIELDS = ["资质证书编号", "资质有效期至", "安全协议编号", "协议有效期至"]
STATUSES = ["待审核", "准入有效", "已退回", "已撤回", "已退出（证件过期）"]
EXPIRED_STATUS = "已退出（证件过期）"
ACTIONS = ["提交审核", "撤回", "审核通过", "审核退回"]
EXPIRING_SOON_DAYS = 30


def _today() -> date:
    return date.today()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or "").strip())
    except ValueError:
        return None


class ContractorService:
    # ---------- 备案与授权 ----------
    def filings(self, name: str | None = None) -> list[dict[str, Any]]:
        rows = store.rows(FILING_MODULE)
        if name:
            rows = [row for row in rows if row.get("安全员姓名") == name]
        return sorted(rows, key=lambda row: (str(row.get("备案时间", "")), int(row.get("id", 0))))

    def current_unit(self, name: str) -> str | None:
        """同一个人挂多家单位时，归属以最近一次备案为准。"""
        rows = self.filings(name)
        return str(rows[-1].get("归属单位")) if rows else None

    def identity(self, name: str) -> dict[str, Any]:
        return {"姓名": name, "当前单位": self.current_unit(name), "备案记录": self.filings(name)}

    def add_filing(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        missing = [field for field in ["安全员姓名", "归属单位"] if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        rows = store.rows(FILING_MODULE)
        entry = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "安全员姓名": str(values["安全员姓名"]).strip(),
            "归属单位": str(values["归属单位"]).strip(),
            "备案时间": str(values.get("备案时间") or "").strip() or _now(),
            "备注": str(values.get("备注") or "备案登记").strip(),
        }
        rows.append(entry)
        return entry, ""

    def _authorize(self, operator: str, team: dict[str, Any]) -> str | None:
        """越权当场拒绝并写明缺哪项授权；返回 None 表示放行。"""
        unit = self.current_unit(operator)
        if unit is None:
            return f"操作人「{operator}」缺少安全员备案：未在任何安全管理单位登记，不能提交或改动"
        if str(team.get("归属单位")) != unit:
            return (
                f"操作人「{operator}」缺少本单位授权：最近一次备案归属{unit}，"
                f"该队伍归属{team.get('归属单位')}，跨单位仅可查看"
            )
        return None

    # ---------- 有效期值守 ----------
    @staticmethod
    def expired_items(materials: dict[str, Any]) -> list[str]:
        items = []
        for label, field in [("资质证书", "资质有效期至"), ("安全协议", "协议有效期至")]:
            deadline = _parse_date(materials.get(field))
            if deadline is None or deadline < _today():
                items.append(f"{label}（{materials.get(field) or '未登记'}）")
        return items

    @staticmethod
    def expiring_soon_items(team: dict[str, Any]) -> list[str]:
        items = []
        for label, field in [("资质证书", "资质有效期至"), ("安全协议", "协议有效期至")]:
            deadline = _parse_date(team.get(field))
            if deadline is not None and 0 <= (deadline - _today()).days <= EXPIRING_SOON_DAYS:
                items.append(f"{label} {deadline.isoformat()} 到期")
        return items

    def sync_expired(self) -> list[dict[str, Any]]:
        """把证件已过期的在册队伍移出准入名单，留痕并同步作业票待办。幂等，可反复调用。"""
        dropped = []
        for team in store.rows(MODULE):
            if team.get("status") != "准入有效":
                continue
            items = self.expired_items(team)
            if not items:
                continue
            team["status"] = EXPIRED_STATUS
            team["pending"] = True
            team["abnormal"] = True
            remark = f"{'、'.join(items)}已过期，退出准入名单"
            self._record(team, "到期退出", "系统值守", "-", "退出", team, remark)
            self._sync_tickets(team, f"外委队伍已退出准入名单：{remark}，相关作业立即叫停并更换队伍", "待办")
            dropped.append(team)
        return dropped

    # ---------- 留痕与同步 ----------
    def _record(
        self,
        team: dict[str, Any],
        action: str,
        operator: str,
        unit: str,
        conclusion: str,
        materials: dict[str, Any],
        remark: str,
    ) -> dict[str, Any]:
        """写一条审核留痕：材料按当时报送内容快照保存，历史结论不被后续续期覆盖。"""
        rows = store.rows(REVIEW_MODULE)
        team_id = int(team.get("id", 0))
        submits = sum(1 for row in rows if int(row.get("队伍id", 0)) == team_id and row.get("动作") == "提交审核")
        round_no = submits + 1 if action == "提交审核" else submits
        entry = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "队伍id": team_id,
            "信用代码": team.get("统一社会信用代码"),
            "队伍名称": team.get("队伍名称"),
            "轮次": round_no,
            "动作": action,
            "结论": conclusion,
            "操作人": operator,
            "操作人单位": unit,
            "资质证书编号": materials.get("资质证书编号"),
            "资质有效期至": materials.get("资质有效期至"),
            "安全协议编号": materials.get("安全协议编号"),
            "协议有效期至": materials.get("协议有效期至"),
            "时间": _now(),
            "备注": remark,
        }
        rows.append(entry)
        return entry

    def _sync_tickets(self, team: dict[str, Any], content: str, todo_status: str) -> None:
        """把准入结论写进引用该队伍的未完工作业票待办清单。"""
        code = str(team.get("统一社会信用代码"))
        for ticket in store.rows(TICKET_MODULE):
            if str(ticket.get("外委队伍信用代码")) != code or ticket.get("status") == "已完工":
                continue
            todos = ticket.setdefault("待办清单", [])
            todos.append({"内容": content, "状态": todo_status, "来源": "准入审核", "时间": _now()})
            if todo_status == "待办":
                ticket["pending"] = True
                ticket["abnormal"] = True

    # ---------- 台账读取 ----------
    def _decorate(self, team: dict[str, Any]) -> dict[str, Any]:
        row = dict(team)
        row["临期提示"] = "、".join(self.expiring_soon_items(team))
        return row

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        unit: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        self.sync_expired()
        rows = list(store.rows(MODULE))
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("统一社会信用代码", "")) or keyword in str(row.get("队伍名称", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if unit:
            rows = [row for row in rows if row.get("归属单位") == unit]
        rows.sort(key=lambda row: (str(row.get("进场时间") or "9999-12-31"), int(row.get("id", 0))))
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self._decorate(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        self.sync_expired()
        team = store.find(MODULE, entry_id)
        return self._decorate(team) if team else None

    def stats(self) -> dict[str, int]:
        self.sync_expired()
        rows = store.rows(MODULE)
        return {
            "准入有效": sum(1 for row in rows if row.get("status") == "准入有效"),
            "待审核": sum(1 for row in rows if row.get("status") == "待审核"),
            "已退出": sum(1 for row in rows if row.get("status") == EXPIRED_STATUS),
            "临期预警": sum(1 for row in rows if row.get("status") == "准入有效" and self.expiring_soon_items(row)),
        }

    def reviews(self, entry_id: int) -> list[dict[str, Any]]:
        return [row for row in store.rows(REVIEW_MODULE) if int(row.get("队伍id", 0)) == entry_id]

    # ---------- 补录建档 ----------
    def create_entry(self, values: dict[str, Any], operator: str) -> tuple[dict[str, Any] | None, str]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        code = str(values["统一社会信用代码"]).strip().upper()
        if len(code) != 18:
            return None, f"统一社会信用代码应为 18 位，当前录入 {len(code)} 位"
        if any(str(row.get("统一社会信用代码")) == code for row in store.rows(MODULE)):
            return None, f"统一社会信用代码 {code} 已建档，一支队伍只建一档"
        unit = self.current_unit(operator)
        if unit is None:
            return None, f"操作人「{operator}」缺少安全员备案：未在任何安全管理单位登记，不能补录建档"
        claimed = str(values.get("归属单位") or unit).strip()
        if claimed != unit:
            return None, f"操作人「{operator}」缺少本单位授权：最近一次备案归属{unit}，不能将队伍补录到{claimed}"
        for field in ["资质有效期至", "协议有效期至", "进场时间"]:
            if _parse_date(values.get(field)) is None:
                return None, f"{field}「{values.get(field)}」不是有效日期（格式 YYYY-MM-DD）"
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: str(values.get(field)).strip() for field in REQUIRED_FIELDS})
        entry["统一社会信用代码"] = code
        entry["归属单位"] = unit
        entry["联系人"] = str(values.get("联系人") or "").strip()
        expired = self.expired_items(entry)
        entry["status"] = EXPIRED_STATUS if expired else "准入有效"
        entry["pending"] = bool(expired)
        entry["abnormal"] = bool(expired)
        rows.append(entry)
        remark = "存量队伍按进场时间补录"
        remark += f"；{'、'.join(expired)}已过期，需续期后重新报审" if expired else "，材料有效直接纳入准入名单"
        self._record(entry, "补录登记", operator, unit, "登记", entry, remark)
        return entry, ""

    # ---------- 审核动作 ----------
    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any],
        operator: str,
    ) -> tuple[dict[str, Any] | None, str]:
        self.sync_expired()
        team = store.find(MODULE, entry_id)
        if team is None:
            return None, f"外委队伍 {entry_id} 不存在或已归档"
        if action not in ACTIONS:
            return None, f"动作「{action}」不属于外委准入可执行范围"
        denial = self._authorize(operator, team)
        if denial:
            return None, denial
        if action == "提交审核":
            return self._submit(team, values, operator)
        if action == "撤回":
            return self._withdraw(team, operator)
        return self._conclude(team, action, values, operator)

    def _submit(self, team: dict[str, Any], values: dict[str, Any], operator: str) -> tuple[dict[str, Any] | None, str]:
        if team.get("status") == "待审核":
            return None, "该队伍已处于待审核状态，请勿重复提交"
        materials = {field: str(values.get(field) or team.get(field) or "").strip() for field in MATERIAL_FIELDS}
        expired = self.expired_items(materials)
        if expired:
            return None, f"送审材料中{'、'.join(expired)}已过期，请先续期再提交准入审核"
        team["status"] = "待审核"
        team["pending"] = True
        team["abnormal"] = False
        unit = self.current_unit(operator) or "-"
        record = self._record(team, "提交审核", operator, unit, "待审核", materials, str(values.get("备注") or "准入审核报审"))
        return team, f"已提交准入审核（第{record['轮次']}轮），材料以本次报送为准"

    def _withdraw(self, team: dict[str, Any], operator: str) -> tuple[dict[str, Any] | None, str]:
        if team.get("status") != "待审核":
            return None, f"当前状态「{team.get('status')}」不可撤回，仅待审核状态可撤回"
        team["status"] = "已撤回"
        team["pending"] = False
        team["abnormal"] = False
        unit = self.current_unit(operator) or "-"
        self._record(team, "撤回", operator, unit, "撤回", team, "安全员撤回本次报审")
        return team, "已撤回本次准入报审"

    def _conclude(
        self,
        team: dict[str, Any],
        action: str,
        values: dict[str, Any],
        operator: str,
    ) -> tuple[dict[str, Any] | None, str]:
        if team.get("status") != "待审核":
            return None, f"当前状态「{team.get('status')}」不在待审核中，无法给出审核结论"
        submits = [
            row for row in store.rows(REVIEW_MODULE)
            if int(row.get("队伍id", 0)) == int(team.get("id", 0)) and row.get("动作") == "提交审核"
        ]
        materials = submits[-1] if submits else team
        unit = self.current_unit(operator) or "-"
        remark = str(values.get("备注") or "").strip()
        if action == "审核退回":
            team["status"] = "已退回"
            team["pending"] = True
            team["abnormal"] = True
            record = self._record(team, "审核退回", operator, unit, "退回", materials, remark or "材料不符合要求，退回补正")
            self._sync_tickets(team, f"外委队伍准入结论：退回（第{record['轮次']}轮），{record['备注']}", "待办")
            return team, "已退回本次准入申请，结论已同步相关作业票待办"
        expired = self.expired_items(materials)
        if expired:
            return None, f"送审材料中{'、'.join(expired)}已过期，不能通过；请撤回并续期后重新报审"
        for field in MATERIAL_FIELDS:
            team[field] = materials.get(field)
        team["status"] = "准入有效"
        team["pending"] = False
        team["abnormal"] = False
        record = self._record(team, "审核通过", operator, unit, "通过", materials, remark or "材料齐全有效，准予准入")
        self._sync_tickets(
            team,
            f"外委队伍准入结论：通过（第{record['轮次']}轮），资质至{materials.get('资质有效期至')}、协议至{materials.get('协议有效期至')}",
            "已完成",
        )
        return team, "审核通过，队伍已纳入准入名单，结论已同步相关作业票待办"
