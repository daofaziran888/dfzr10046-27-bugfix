"""粒度声明领域服务：声明事实表业务粒度数据集和度量可加性，校验聚合转换规则。"""
from __future__ import annotations

from typing import Any

from app.review_board import review_board
from app.services.base import BaseModuleService
from app.store import store


class GrainDeclareService(BaseModuleService):
    MODULE = "grain_declare"
    ENTITY = "粒度声明"
    LIST_FIELDS = ["声明编号", "所属事实表", "一行代表", "维度组合", "度量可加性", "重复判定键", "声明版本", "最近核对"]
    REQUIRED_FIELDS = ["声明编号", "所属事实表", "一行代表"]
    STATUS_ORDER = ["草稿", "已声明", "待修订", "已作废"]
    ACTION_RULES = {"确认声明": "已声明", "提交修订": "待修订", "作废声明": "已作废"}
    NEGATIVE_ACTIONS = []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry, message = super().run_action(entry_id, action)
        if entry is not None and action == "提交修订":
            paused = self._pause_review_tickets(entry)
            if paused:
                receipts = "、".join(t["受理号"] for t in paused)
                message = (
                    f"{message}；关联复核回执 {receipts} 已暂停，"
                    f"待汇总员确认新粒度关联"
                )
        return entry, message

    def review_todos(self) -> list[dict[str, Any]]:
        """复核待办：粒度页签收台看到的全部回执（含历史回执留痕）。"""
        return review_board.tickets()

    def sign_receipt(
        self, receipt: str, group: str | None = None,
    ) -> tuple[bool, str, dict[str, Any] | None]:
        """签收复核回执：暂停中或已签收的回执拒绝，一个受理号不能交给两组。"""
        return review_board.sign(receipt, group)

    @staticmethod
    def _pause_review_tickets(declaration: dict[str, Any]) -> list[dict[str, Any]]:
        candidate = {
            "声明编号": str(declaration.get("声明编号", "")),
            "维度组合": str(declaration.get("维度组合", "")),
            "声明版本": str(declaration.get("声明版本", "")),
        }
        return review_board.pause_for_declaration(candidate["声明编号"], candidate)

    def declare_grain(
        self, declare_id: str, fact_table: str, one_row_means: str,
        dim_combo: str, additivity: str, dedup_key: str, version: str,
    ) -> tuple[bool, str, dict[str, Any] | None]:
        """声明事实表粒度：一行代表 + 维度组合 + 度量可加性。"""
        rows = store.rows(self.MODULE)
        entry = {
            "声明编号": declare_id, "所属事实表": fact_table,
            "一行代表": one_row_means, "维度组合": dim_combo,
            "度量可加性": additivity, "重复判定键": dedup_key,
            "声明版本": version, "最近核对": "2026-11-21",
            "status": "已声明", "pending": False, "abnormal": False,
        }
        entry["id"] = max((int(r.get("id", 0)) for r in rows), default=0) + 1
        rows.append(entry)
        return True, f"粒度声明 {declare_id} 已生效：{one_row_means}", entry

    def revise_grain(self, declare_id: str, new_dims: str) -> tuple[bool, str]:
        """修订粒度声明：触发汇总层重算与下游引用更新，关联复核回执同步暂停。"""
        rows = store.rows(self.MODULE)
        for r in rows:
            if r.get("声明编号") == declare_id:
                r["status"] = "待修订"
                r["维度组合"] = new_dims
                r["pending"] = True
                paused = self._pause_review_tickets(r)
                suffix = ""
                if paused:
                    receipts = "、".join(t["受理号"] for t in paused)
                    suffix = f"；关联复核回执 {receipts} 已暂停，待汇总员确认新粒度关联"
                return True, f"粒度声明 {declare_id} 已提交修订：{new_dims}{suffix}"
        return False, f"粒度声明 {declare_id} 不存在"
