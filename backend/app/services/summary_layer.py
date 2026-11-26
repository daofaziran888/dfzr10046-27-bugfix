"""汇总层派生领域服务：校验事实批次派生汇总条目，版本化绑定依赖批次，产出汇总条目数据集。"""
from __future__ import annotations

from typing import Any

from app.review_board import review_board
from app.services.base import BaseModuleService
from app.store import store

REVIEW_SUBMIT_ACTION = "提交送审"
REVIEW_CONFIRM_ACTION = "确认新关联"


class SummaryLayerService(BaseModuleService):
    MODULE = "summary_layer"
    ENTITY = "汇总条目"
    LIST_FIELDS = ["汇总编号", "来源事实表", "汇总粒度", "度量表达式", "派生行数", "依赖批次", "刷新方式", "派生时间"]
    REQUIRED_FIELDS = ["汇总编号", "来源事实表", "汇总粒度"]
    STATUS_ORDER = ["待派生", "派生中", "已派生", "派生失败"]
    ACTION_RULES = {"启动派生": "派生中", "确认派生": "已派生", "标记失败": "派生失败"}
    NEGATIVE_ACTIONS = ["标记失败"]

    def list_entries(self, **kwargs: Any) -> tuple[list[dict[str, Any]], int]:
        """列表行附带送审资格与复核回执，供页面判断哪些选择仍有确认资格。"""
        items, total = super().list_entries(**kwargs)
        annotated = []
        for item in items:
            row = dict(item)
            ticket = review_board.open_ticket_for(int(row.get("id", 0)))
            row["review_eligible"] = row.get("status") == "已派生" and ticket is None
            row["review_receipt"] = ticket["受理号"] if ticket else ""
            row["review_status"] = ticket["status"] if ticket else ""
            annotated.append(row)
        return annotated, total

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        if action == REVIEW_SUBMIT_ACTION:
            return self._submit_review(entry_id)
        if action == REVIEW_CONFIRM_ACTION:
            return self._confirm_new_association(entry_id)
        return super().run_action(entry_id, action)

    def _submit_review(self, entry_id: int) -> tuple[dict[str, Any] | None, str]:
        """送审：只有已派生（仍有确认资格）的汇总条目能受理，历史回执沿用不重复。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return None, f"{self.ENTITY} {entry_id} 不存在或已归档"
        if entry.get("status") != "已派生":
            return None, (
                f"汇总条目 {entry.get('汇总编号')} 当前为{entry.get('status')}，"
                f"没有确认资格，不能送审"
            )
        existing = review_board.open_ticket_for(entry_id)
        if existing is not None:
            return entry, (
                f"汇总条目 {entry.get('汇总编号')} 已有复核回执 {existing['受理号']}"
                f"（{existing['status']}），沿用历史回执不重复受理"
            )
        declaration = self._active_declaration(str(entry.get("来源事实表", "")))
        if declaration is None:
            return None, (
                f"事实表 {entry.get('来源事实表')} 没有已声明的粒度声明，无法送审"
            )
        ticket = review_board.submit(entry, declaration)
        closed = [
            t for t in review_board.history_for(entry_id)
            if t.get("受理号") != ticket["受理号"]
        ]
        compat = (
            f"；历史回执 {'、'.join(t['受理号'] for t in closed)} 已办结归档，本次重新受理"
            if closed else ""
        )
        return entry, (
            f"汇总条目 {entry.get('汇总编号')} 送审已受理，受理号 {ticket['受理号']}，"
            f"尚未分配复核人{compat}"
        )

    def _confirm_new_association(self, entry_id: int) -> tuple[dict[str, Any] | None, str]:
        """粒度关联冲突时由汇总员确认新关联，回执恢复受理资格。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return None, f"{self.ENTITY} {entry_id} 不存在或已归档"
        ticket, message = review_board.confirm_association(entry_id)
        if ticket is None:
            return None, message
        return entry, message

    @staticmethod
    def _active_declaration(fact_table: str) -> dict[str, Any] | None:
        for row in store.rows("grain_declare"):
            if row.get("所属事实表") == fact_table and row.get("status") == "已声明":
                return row
        return None

    def derive_summary(
        self, summary_id: str, source_table: str, granularity: str,
        expression: str, dependency_batch: str, refresh_method: str,
        expected_rows: int,
    ) -> tuple[bool, str, dict[str, Any] | None]:
        """派生汇总条目：绑定具体依赖批次，重派生不得覆盖已被引用的旧批次。"""
        rows = store.rows(self.MODULE)
        for r in rows:
            if r.get("依赖批次") == dependency_batch and r.get("status") == "已派生":
                return False, (
                    f"依赖批次 {dependency_batch} 已有汇总条目 {r.get('汇总编号')}，"
                    f"重派生不得覆盖已被引用的旧批次"
                ), None

        entry = {
            "汇总编号": summary_id, "来源事实表": source_table,
            "汇总粒度": granularity, "度量表达式": expression,
            "派生行数": expected_rows, "依赖批次": dependency_batch,
            "刷新方式": refresh_method, "派生时间": "2026-11-21",
            "status": "已派生", "pending": False, "abnormal": False,
        }
        entry["id"] = max((int(r.get("id", 0)) for r in rows), default=0) + 1
        rows.append(entry)
        return True, f"汇总条目 {summary_id} 已派生：{expected_rows} 行", entry

    def check_grain_consistency(
        self, summary_grain: str, declared_grain: str,
    ) -> tuple[bool, str]:
        """校验汇总粒度与粒度声明一致。"""
        if summary_grain != declared_grain:
            return False, f"汇总粒度 {summary_grain} 与声明粒度 {declared_grain} 不一致"
        return True, f"粒度一致：{summary_grain}"
