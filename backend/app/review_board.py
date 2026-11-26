"""复核回执看板：汇总层送审与粒度声明复核共用的受理号状态机。

状态机：已受理（未分配复核人）→ 复核中（已签收）→ 已办结。
粒度声明被修订时，绑定该声明且仍在已受理的回执先暂停，
由汇总员确认新粒度关联后恢复受理——一个受理号同一时刻只绑定
一组粒度关联、只交给一个复核组，暂停期间签收一律拒绝。
"""
from __future__ import annotations

from typing import Any

from app.seed import SEED_REVIEWS

OPEN_STATUSES = ("已受理", "已暂停", "复核中")


class ReviewBoard:
    def __init__(self) -> None:
        self._tickets: list[dict[str, Any]] = [
            {**ticket, "粒度关联": dict(ticket["粒度关联"]),
             "历史": [dict(event) for event in ticket.get("历史", [])]}
            for ticket in SEED_REVIEWS
        ]
        self._seq = len(self._tickets)

    def tickets(self) -> list[dict[str, Any]]:
        return list(self._tickets)

    def ticket_by_receipt(self, receipt: str) -> dict[str, Any] | None:
        for ticket in self._tickets:
            if ticket.get("受理号") == receipt:
                return ticket
        return None

    def open_ticket_for(self, summary_id: int) -> dict[str, Any] | None:
        """汇总条目当前未结的复核回执（已受理/已暂停/复核中）。"""
        for ticket in self._tickets:
            if ticket.get("汇总id") == summary_id and ticket.get("status") in OPEN_STATUSES:
                return ticket
        return None

    def history_for(self, summary_id: int) -> list[dict[str, Any]]:
        return [t for t in self._tickets if t.get("汇总id") == summary_id]

    def submit(self, summary: dict[str, Any], declaration: dict[str, Any]) -> dict[str, Any]:
        """受理送审：生成受理号，尚未分配复核人。"""
        self._seq += 1
        ticket = {
            "受理号": f"ACC-{self._seq:04d}",
            "汇总id": int(summary.get("id", 0)),
            "汇总编号": summary.get("汇总编号", ""),
            "来源事实表": summary.get("来源事实表", ""),
            "粒度关联": self._association_of(declaration),
            "待确认关联": None,
            "status": "已受理",
            "复核组": None,
            "历史": [{"事件": "受理", "说明": "送审已受理，待分配复核人"}],
        }
        self._tickets.append(ticket)
        return ticket

    def pause_for_declaration(
        self, declare_id: str, candidate: dict[str, str],
    ) -> list[dict[str, Any]]:
        """粒度声明修订：暂停绑定该声明且仍未分配的回执，记下待确认的新关联。"""
        paused = []
        for ticket in self._tickets:
            assoc = ticket.get("粒度关联") or {}
            if assoc.get("声明编号") != declare_id:
                continue
            if ticket.get("status") != "已受理":
                continue
            ticket["status"] = "已暂停"
            ticket["待确认关联"] = dict(candidate)
            ticket.setdefault("历史", []).append({
                "事件": "暂停",
                "说明": f"粒度声明 {declare_id} 已修订，新旧粒度关联冲突，待汇总员确认",
            })
            paused.append(ticket)
        return paused

    def confirm_association(self, summary_id: int) -> tuple[dict[str, Any] | None, str]:
        """汇总员确认新粒度关联：回执恢复已受理，受理号不变。"""
        ticket = self.open_ticket_for(summary_id)
        if ticket is None:
            return None, "没有待确认的复核回执"
        if ticket.get("status") != "已暂停":
            return None, f"回执 {ticket['受理号']} 当前为{ticket.get('status')}，无需确认新关联"
        candidate = ticket.get("待确认关联")
        if candidate:
            ticket["粒度关联"] = dict(candidate)
        ticket["待确认关联"] = None
        ticket["status"] = "已受理"
        ticket.setdefault("历史", []).append({
            "事件": "确认新关联",
            "说明": f"汇总员确认新粒度关联 {ticket['粒度关联'].get('声明编号')}，回执恢复受理",
        })
        return ticket, f"回执 {ticket['受理号']} 已确认新粒度关联，恢复受理"

    def sign(
        self, receipt: str, group: str | None = None,
    ) -> tuple[bool, str, dict[str, Any] | None]:
        """复核组签收：只有已受理的回执能签收，一个受理号不能交给两组。"""
        ticket = self.ticket_by_receipt(receipt)
        if ticket is None:
            return False, f"复核回执 {receipt} 不存在", None
        status = ticket.get("status")
        if status == "已暂停":
            return False, (
                f"回执 {receipt} 已暂停：粒度关联待汇总员确认，一个受理号不能交给两组"
            ), None
        if status == "复核中":
            return False, (
                f"回执 {receipt} 已被 {ticket.get('复核组')} 签收，一个受理号不能交给两组"
            ), None
        if status != "已受理":
            return False, f"回执 {receipt} 当前为{status}，不能签收", None
        assoc = ticket.get("粒度关联") or {}
        ticket["复核组"] = group or f"复核组-{assoc.get('声明编号', '未定')}"
        ticket["status"] = "复核中"
        ticket.setdefault("历史", []).append({
            "事件": "签收",
            "说明": f"{ticket['复核组']} 签收，粒度关联 {assoc.get('声明编号')}",
        })
        return True, f"回执 {receipt} 已由 {ticket['复核组']} 签收", ticket

    @staticmethod
    def _association_of(declaration: dict[str, Any]) -> dict[str, str]:
        return {
            "声明编号": str(declaration.get("声明编号", "")),
            "维度组合": str(declaration.get("维度组合", "")),
            "声明版本": str(declaration.get("声明版本", "")),
        }


review_board = ReviewBoard()
