"""汇总层送审与粒度声明复核的受理号流转测试。

覆盖：送审受理号生成、确认资格校验、历史回执兼容、粒度关联冲突时
暂停-确认-签收链路，以及一个受理号不能交给两组。
"""
from __future__ import annotations

import pytest

from app.review_board import ReviewBoard
from app.services.grain_declare import GrainDeclareService
from app.services.summary_layer import SummaryLayerService
from app.store import store


@pytest.fixture()
def board(monkeypatch):
    """每个测试一份干净的看板（含种子历史回执），避免受理号互相污染。"""
    fresh = ReviewBoard()
    monkeypatch.setattr("app.services.summary_layer.review_board", fresh)
    monkeypatch.setattr("app.services.grain_declare.review_board", fresh)
    return fresh


@pytest.fixture()
def services(board):
    return SummaryLayerService(), GrainDeclareService()


def _grain_row(declare_id: str) -> dict:
    for row in store.rows("grain_declare"):
        if row.get("声明编号") == declare_id:
            return row
    raise AssertionError(f"种子数据缺少粒度声明 {declare_id}")


def _receipt_of(message: str) -> str:
    return message.split("受理号 ")[1].split("，")[0]


class TestReviewSubmit:
    def test_submit_gets_receipt_unassigned(self, services, board):
        sl, _ = services
        entry, message = sl.run_action(1, "提交送审")
        assert entry is not None
        assert "受理号 ACC-" in message
        assert "尚未分配复核人" in message
        ticket = board.ticket_by_receipt(_receipt_of(message))
        assert ticket["status"] == "已受理"
        assert ticket["复核组"] is None

    def test_submit_requires_confirmation_eligibility(self, services):
        sl, _ = services
        entry, message = sl.run_action(2, "提交送审")  # 待派生
        assert entry is None
        assert "没有确认资格" in message
        entry, message = sl.run_action(4, "提交送审")  # 派生中
        assert entry is None
        assert "没有确认资格" in message

    def test_resubmit_reuses_open_receipt(self, services, board):
        sl, _ = services
        _, first = sl.run_action(1, "提交送审")
        _, second = sl.run_action(1, "提交送审")
        receipt = _receipt_of(first)
        assert "沿用历史回执" in second
        assert receipt in second
        open_tickets = [
            t for t in board.tickets()
            if t["汇总id"] == 1 and t["status"] != "已办结"
        ]
        assert len(open_tickets) == 1

    def test_historical_receipt_compatible(self, services, board):
        """SUM-101 已有已办结的历史回执 ACC-0001，重新送审开新号且旧回执留痕。"""
        sl, _ = services
        _, message = sl.run_action(3, "提交送审")
        assert "受理号 ACC-" in message
        assert "历史回执 ACC-0001 已办结" in message
        receipts = [t["受理号"] for t in board.history_for(3)]
        assert "ACC-0001" in receipts
        assert len(receipts) == 2

    def test_list_annotates_review_fields(self, services):
        sl, _ = services
        sl.run_action(1, "提交送审")
        items, _ = sl.list_entries(filters={}, keyword=None, status=None, page=1, size=20)
        by_id = {row["id"]: row for row in items}
        assert by_id[1]["review_receipt"].startswith("ACC-")
        assert by_id[1]["review_status"] == "已受理"
        assert by_id[1]["review_eligible"] is False
        assert by_id[2]["review_eligible"] is False  # 待派生无确认资格
        assert by_id[3]["review_eligible"] is True   # 已派生且无未结回执


class TestGrainConflict:
    def test_revision_pauses_then_confirm_then_sign(self, services, board):
        """月份汇总送审→粒度声明修订→回执暂停→签收被拒→确认新关联→签收成功。"""
        sl, gd = services
        _, message = sl.run_action(1, "提交送审")
        receipt = _receipt_of(message)
        ticket = board.ticket_by_receipt(receipt)
        assert ticket["status"] == "已受理"
        assert ticket["复核组"] is None

        grain = _grain_row("GRN-001")
        snapshot = dict(grain)
        try:
            entry, message = gd.run_action(int(grain["id"]), "提交修订")
            assert entry is not None
            assert receipt in message
            assert "已暂停" in message
            assert ticket["status"] == "已暂停"
            assert ticket["待确认关联"] is not None

            ok, sign_msg, _ = gd.sign_receipt(receipt)
            assert not ok
            assert "一个受理号不能交给两组" in sign_msg

            entry, confirm_msg = sl.run_action(1, "确认新关联")
            assert entry is not None
            assert receipt in confirm_msg
            assert ticket["status"] == "已受理"
            assert ticket["待确认关联"] is None

            ok, sign_msg, signed = gd.sign_receipt(receipt)
            assert ok
            assert signed is not None
            assert signed["复核组"] == "复核组-GRN-001"

            ok, sign_msg, _ = gd.sign_receipt(receipt, group="复核组-另一组")
            assert not ok
            assert "一个受理号不能交给两组" in sign_msg
        finally:
            grain.clear()
            grain.update(snapshot)

    def test_revise_grain_pauses_with_new_candidate(self, services, board):
        sl, gd = services
        _, message = sl.run_action(1, "提交送审")
        receipt = _receipt_of(message)

        grain = _grain_row("GRN-001")
        snapshot = dict(grain)
        try:
            ok, msg = gd.revise_grain("GRN-001", "客户+产品+月份")
            assert ok
            assert receipt in msg
            ticket = board.ticket_by_receipt(receipt)
            assert ticket["status"] == "已暂停"
            assert ticket["待确认关联"]["维度组合"] == "客户+产品+月份"
        finally:
            grain.clear()
            grain.update(snapshot)

    def test_confirm_without_pause_rejected(self, services):
        sl, _ = services
        sl.run_action(1, "提交送审")
        entry, message = sl.run_action(1, "确认新关联")
        assert entry is None
        assert "无需确认" in message

    def test_sign_unknown_receipt(self, services):
        _, gd = services
        ok, message, _ = gd.sign_receipt("ACC-9999")
        assert not ok
        assert "不存在" in message
