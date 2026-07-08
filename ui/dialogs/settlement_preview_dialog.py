"""只读结算预览对话框。"""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from models import LotteryDraw
from schemas.settlement_schema import OrderSettlementPreview
from services.draw_service import DrawService
from services.order_service import OrderService
from services.settlement_service import SettlementService
from ui.app_events import app_events
from settlement.exceptions import SettlementDataError


def _money(value: Decimal) -> str:
    return f"{value:.2f}"


def _dash(value: object | None) -> str:
    return str(value) if value not in (None, "") else "—"


def _format_numbers(numbers: list[str]) -> str:
    return " ".join(numbers)


class SettlementPreviewDialog(QDialog):
  def __init__(
      self,
      order_id: int,
      parent=None,
      order_service: OrderService | None = None,
      draw_service: DrawService | None = None,
      settlement_service: SettlementService | None = None,
  ):
      super().__init__(parent)
      self._order_id = order_id
      self._order_service = order_service or OrderService()
      self._draw_service = draw_service or DrawService()
      self._settlement_service = settlement_service or SettlementService()
      self._draws: list[LotteryDraw] = []
      self._preview_done = False
      self._invalid = False
      self._current_preview: OrderSettlementPreview | None = None
      self._settlement_committed = False

      self.setWindowTitle("结算预览")
      self.setMinimumSize(820, 640)

      root = QVBoxLayout(self)
      root.setContentsMargins(12, 10, 12, 10)
      root.setSpacing(8)

      root.addWidget(self._build_order_section())
      root.addWidget(self._build_draw_section())
      root.addWidget(self._build_draw_detail_section())
      root.addLayout(self._build_preview_actions())
      root.addWidget(self._build_summary_section())
      root.addWidget(self._build_result_table(), stretch=1)
      root.addWidget(self._build_disclaimer())

      self._apply_stylesheet()
      self._load_order()
      app_events.draws_changed.connect(self._on_draws_changed)
      if not self._invalid:
          self._reload_draws()

  def is_valid(self) -> bool:
      return not self._invalid

  def settlement_committed(self) -> bool:
      return self._settlement_committed

  def _build_order_section(self) -> QFrame:
      frame = QFrame()
      frame.setObjectName("sectionFrame")
      grid = QGridLayout(frame)
      grid.setContentsMargins(8, 6, 8, 6)
      grid.setHorizontalSpacing(16)
      grid.setVerticalSpacing(4)

      self._lbl_order_no = QLabel()
      self._lbl_region = QLabel()
      self._lbl_total = QLabel()
      self._lbl_customer = QLabel()
      self._lbl_channel = QLabel()
      self._lbl_created = QLabel()
      self._lbl_status = QLabel()

      fields = (
          ("订单号", self._lbl_order_no),
          ("订单地区", self._lbl_region),
          ("订单总金额", self._lbl_total),
          ("客户名称", self._lbl_customer),
          ("渠道", self._lbl_channel),
          ("创建时间", self._lbl_created),
          ("订单状态", self._lbl_status),
      )
      for row, (label, widget) in enumerate(fields):
          grid.addWidget(QLabel(label), row, 0)
          grid.addWidget(widget, row, 1)
      return frame

  def _build_draw_section(self) -> QFrame:
      frame = QFrame()
      frame.setObjectName("sectionFrame")
      layout = QVBoxLayout(frame)
      layout.setContentsMargins(8, 6, 8, 6)

      title = QLabel("开奖选择（地区固定为订单地区）")
      title.setObjectName("sectionTitle")
      layout.addWidget(title)

      row = QHBoxLayout()
      self._cmb_draw = QComboBox()
      self._cmb_draw.currentIndexChanged.connect(self._on_draw_changed)
      self._btn_refresh_draws = QPushButton("刷新开奖列表")
      self._btn_refresh_draws.clicked.connect(self._reload_draws)
      row.addWidget(QLabel("期号"))
      row.addWidget(self._cmb_draw, stretch=1)
      row.addWidget(self._btn_refresh_draws)
      layout.addLayout(row)

      self._lbl_no_draws = QLabel("当前地区暂无可用开奖结果")
      self._lbl_no_draws.setObjectName("hintLabel")
      self._lbl_no_draws.setVisible(False)
      layout.addWidget(self._lbl_no_draws)
      return frame

  def _build_draw_detail_section(self) -> QFrame:
      frame = QFrame()
      frame.setObjectName("sectionFrame")
      grid = QGridLayout(frame)
      grid.setContentsMargins(8, 6, 8, 6)

      self._lbl_regular = QLabel()
      self._lbl_special = QLabel()
      self._lbl_draw_date = QLabel()
      self._lbl_source = QLabel()
      self._lbl_draw_status = QLabel()

      for row, (label, widget) in enumerate(
          (
              ("普通号码", self._lbl_regular),
              ("特码", self._lbl_special),
              ("开奖日期", self._lbl_draw_date),
              ("数据来源", self._lbl_source),
              ("数据状态", self._lbl_draw_status),
          )
      ):
          grid.addWidget(QLabel(label), row, 0)
          grid.addWidget(widget, row, 1)
      return frame

  def _build_preview_actions(self) -> QHBoxLayout:
      row = QHBoxLayout()
      self._btn_preview = QPushButton("开始预览")
      self._btn_preview.setObjectName("primaryBtn")
      self._btn_preview.clicked.connect(self._on_start_preview)
      self._btn_commit = QPushButton("正式确认结算")
      self._btn_commit.setObjectName("dangerBtn")
      self._btn_commit.setEnabled(False)
      self._btn_commit.clicked.connect(self._on_commit_settlement)
      row.addWidget(self._btn_preview)
      row.addWidget(self._btn_commit)
      row.addStretch(1)
      return row

  def _build_summary_section(self) -> QFrame:
      frame = QFrame()
      frame.setObjectName("summaryFrame")
      grid = QGridLayout(frame)
      grid.setContentsMargins(8, 6, 8, 6)

      self._lbl_total_items = QLabel("—")
      self._lbl_supported = QLabel("—")
      self._lbl_unsupported = QLabel("—")
      self._lbl_winning = QLabel("—")
      self._lbl_losing = QLabel("—")
      self._lbl_total_bet = QLabel("—")
      self._lbl_total_payout = QLabel("—")
      self._lbl_total_rebate = QLabel("—")
      self._lbl_statistic_net = QLabel("—")

      for col, (label, widget) in enumerate(
          (
              ("订单明细总数", self._lbl_total_items),
              ("支持判定数量", self._lbl_supported),
              ("不支持数量", self._lbl_unsupported),
              ("中奖数量", self._lbl_winning),
              ("未中奖数量", self._lbl_losing),
              ("投注本金", self._lbl_total_bet),
              ("总中奖金额", self._lbl_total_payout),
              ("返水金额", self._lbl_total_rebate),
              ("统计结算金额", self._lbl_statistic_net),
          )
      ):
          row = 0 if col < 5 else 2
          display_col = col if col < 5 else col - 5
          grid.addWidget(QLabel(label), row, display_col)
          grid.addWidget(widget, row + 1, display_col)
      return frame

  def _build_result_table(self) -> QTableWidget:
      self._result_table = QTableWidget(0, 12)
      self._result_table.setHorizontalHeaderLabels(
          [
              "投注类型",
              "投注内容",
              "投注金额",
              "是否支持",
              "判定结果",
              "命中号码",
              "赔率",
              "中奖金额",
              "赔率来源/提示",
              "判定说明",
              "返水比例",
              "返水金额",
          ]
      )
      self._result_table.verticalHeader().setVisible(False)
      self._result_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
      self._result_table.setAlternatingRowColors(True)
      header = self._result_table.horizontalHeader()
      header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
      header.setStretchLastSection(True)
      return self._result_table

  def _build_disclaimer(self) -> QLabel:
      label = QLabel("返水和统计结算金额仅作记账统计，不代表真实付款、真实入账或客户余额变动。")
      label.setObjectName("hintLabel")
      label.setWordWrap(True)
      return label

  def _load_order(self) -> None:
      detail = self._order_service.get_order(self._order_id)
      if detail is None:
          self._invalid = True
          return
      self._order_detail = detail
      self._lbl_order_no.setText(detail.order_no)
      self._lbl_region.setText(detail.region)
      self._lbl_total.setText(_money(detail.total_amount))
      self._lbl_customer.setText(_dash(detail.customer_name))
      self._lbl_channel.setText(_dash(detail.channel))
      self._lbl_created.setText(detail.created_at.strftime("%Y-%m-%d %H:%M:%S"))
      self._lbl_status.setText(detail.status)

  def _reload_draws(self) -> None:
      if not hasattr(self, "_order_detail"):
          return
      selected_draw_id = self._cmb_draw.currentData()
      self._clear_preview_results()
      self._draws = self._draw_service.list_draws(region=self._order_detail.region, limit=100)
      self._cmb_draw.blockSignals(True)
      self._cmb_draw.clear()
      for draw in self._draws:
          text = (
              f"第{draw.issue_number}期｜{draw.draw_date:%Y-%m-%d}｜特码{draw.special_number}"
          )
          self._cmb_draw.addItem(text, draw.id)
      self._cmb_draw.blockSignals(False)

      has_draws = bool(self._draws)
      self._lbl_no_draws.setVisible(not has_draws)
      self._cmb_draw.setEnabled(has_draws)
      self._btn_preview.setEnabled(has_draws)
      self._btn_commit.setEnabled(False)

      if has_draws:
          selected_index = self._cmb_draw.findData(selected_draw_id)
          self._cmb_draw.setCurrentIndex(selected_index if selected_index >= 0 else 0)
          self._show_draw_detail(self._draws[self._cmb_draw.currentIndex()])
      else:
          self._clear_draw_detail()
          self._clear_preview_results()

  def _on_draws_changed(self) -> None:
      try:
          self._reload_draws()
      except Exception as exc:
          self._lbl_no_draws.setVisible(True)
          self._lbl_no_draws.setText(f"开奖数据已变更，但自动刷新失败：{exc}")

  def _on_draw_changed(self, index: int) -> None:
      if index < 0 or index >= len(self._draws):
          self._clear_draw_detail()
          return
      self._show_draw_detail(self._draws[index])
      if self._preview_done:
          self._clear_preview_results()

  def _show_draw_detail(self, draw: LotteryDraw) -> None:
      self._lbl_regular.setText(_format_numbers(list(draw.regular_numbers)))
      self._lbl_special.setText(draw.special_number)
      self._lbl_draw_date.setText(draw.draw_date.strftime("%Y-%m-%d"))
      self._lbl_source.setText(_dash(draw.source))
      self._lbl_draw_status.setText(draw.status)

  def _clear_draw_detail(self) -> None:
      for label in (
          self._lbl_regular,
          self._lbl_special,
          self._lbl_draw_date,
          self._lbl_source,
          self._lbl_draw_status,
      ):
          label.setText("—")

  def _on_start_preview(self) -> None:
      index = self._cmb_draw.currentIndex()
      if index < 0 or index >= len(self._draws):
          QMessageBox.warning(self, "结算确认", "请先选择开奖并完成结算预览")
          return
      draw_id = self._draws[index].id
      try:
          preview = self._settlement_service.preview_order(self._order_id, draw_id)
      except SettlementDataError as exc:
          QMessageBox.warning(self, "结算预览", str(exc))
          return
      self._preview_done = True
      self._current_preview = preview
      self._show_preview(preview)
      self._update_commit_button()

  def _show_preview(self, preview: OrderSettlementPreview) -> None:
      self._lbl_total_items.setText(str(preview.total_items))
      self._lbl_supported.setText(str(preview.supported_items))
      self._lbl_unsupported.setText(str(preview.unsupported_items))
      self._lbl_winning.setText(str(preview.winning_items))
      self._lbl_losing.setText(str(preview.losing_items))
      self._lbl_total_bet.setText(_money(preview.total_bet_amount))
      self._lbl_total_payout.setText(_money(preview.total_payout_amount))
      self._lbl_total_rebate.setText(_money(preview.total_rebate_amount))
      self._lbl_statistic_net.setText(_money(preview.statistic_net_amount))

      self._result_table.setRowCount(len(preview.results))
      for row_idx, item in enumerate(preview.results):
          if not item.is_supported:
              supported_text = "否"
              outcome = "暂不支持"
          elif item.is_winner:
              supported_text = "是"
              outcome = "中奖"
          else:
              supported_text = "是"
              outcome = "未中奖"

          values = [
              item.bet_type,
              item.selection,
              _money(item.amount),
              supported_text,
              outcome,
              _dash(item.matched_number),
              _dash(item.odds),
              _money(item.payout_amount),
              self._payout_hint(item),
              item.reason,
              self._rebate_rate_text(item.rebate_rate),
              _money(item.rebate_amount),
          ]
          for col_idx, value in enumerate(values):
              cell = QTableWidgetItem(value)
              cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
              if col_idx in (8, 9):
                  cell.setToolTip(item.reason)
              if col_idx == 8:
                  cell.setToolTip(self._payout_hint(item))
              self._result_table.setItem(row_idx, col_idx, cell)

  def _rebate_rate_text(self, value: Decimal | None) -> str:
      if value is None:
          return "—"
      return f"{(value * Decimal('100')).quantize(Decimal('0.01'))}%"

  def _payout_hint(self, item) -> str:
      source = item.odds_source or "未配置"
      plan = f" / {item.odds_plan_name}" if item.odds_plan_name else ""
      note = f"：{item.payout_note}" if item.payout_note else ""
      return f"{source}{plan}{note}"

  def _clear_preview_results(self) -> None:
      self._preview_done = False
      self._current_preview = None
      for label in (
          self._lbl_total_items,
          self._lbl_supported,
          self._lbl_unsupported,
          self._lbl_winning,
          self._lbl_losing,
          self._lbl_total_bet,
          self._lbl_total_payout,
          self._lbl_total_rebate,
          self._lbl_statistic_net,
      ):
          label.setText("—")
      self._result_table.setRowCount(0)
      if hasattr(self, "_btn_commit"):
          self._btn_commit.setEnabled(False)

  def _update_commit_button(self) -> None:
      can_commit = (
          self._preview_done
          and self._current_preview is not None
          and self._current_preview.unsupported_items == 0
          and getattr(self, "_order_detail", None) is not None
          and self._order_detail.status != "settled"
      )
      self._btn_commit.setEnabled(can_commit)

  def _selected_draw(self) -> LotteryDraw | None:
      index = self._cmb_draw.currentIndex()
      if index < 0 or index >= len(self._draws):
          return None
      return self._draws[index]

  def _on_commit_settlement(self) -> None:
      draw = self._selected_draw()
      if draw is None:
          QMessageBox.warning(self, "结算确认", "请先选择开奖并完成结算预览")
          return
      if not self._preview_done or self._current_preview is None:
          QMessageBox.warning(self, "结算确认", "请先开始预览")
          return
      if getattr(self, "_order_detail", None) is not None and self._order_detail.status == "settled":
          QMessageBox.warning(self, "结算确认", "该订单已结算，不能重复结算")
          self._btn_commit.setEnabled(False)
          return
      if self._current_preview.unsupported_items:
          QMessageBox.warning(self, "结算确认", "存在暂不支持玩法，暂不能正式结算")
          self._btn_commit.setEnabled(False)
          return

      order_no = getattr(self._order_detail, "order_no", "")
      message = (
          f"订单号 / 订单ID：{order_no} / {self._order_id}\n"
          f"开奖期号：{draw.issue_number}\n"
          f"中奖数量：{self._current_preview.winning_items}\n"
          f"未中奖数量：{self._current_preview.losing_items}\n"
          f"总明细数：{self._current_preview.total_items}\n\n"
          f"投注本金：{_money(self._current_preview.total_bet_amount)}\n"
          f"中奖金额：{_money(self._current_preview.total_payout_amount)}\n"
          f"返水金额：{_money(self._current_preview.total_rebate_amount)}\n"
          f"统计结算金额：{_money(self._current_preview.statistic_net_amount)}\n\n"
          "确认后将更新订单状态并写入操作日志。"
      )
      choice = QMessageBox.question(
          self,
          "正式确认结算",
          message,
          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
          QMessageBox.StandardButton.No,
      )
      if choice != QMessageBox.StandardButton.Yes:
          return

      try:
          result = self._settlement_service.commit_order_settlement(self._order_id, draw.id)
      except SettlementDataError as exc:
          text = str(exc)
          if "已结算" in text or "宸茬粨绠" in text:
              QMessageBox.warning(self, "结算确认", "该订单已结算，不能重复结算")
          else:
              QMessageBox.warning(self, "结算确认", text)
          self._load_order()
          self._update_commit_button()
          return
      except Exception as exc:
          QMessageBox.warning(self, "结算确认", f"结算失败：{exc}")
          return

      self._settlement_committed = True
      self._load_order()
      self._btn_commit.setEnabled(False)
      app_events.orders_changed.emit()
      app_events.settlements_changed.emit()
      app_events.logs_changed.emit()
      QMessageBox.information(
          self,
          "结算确认",
          (
              "结算成功\n"
              f"订单ID：{result.order_id}\n"
              f"开奖期号：{result.issue_number}\n"
              f"中奖数量：{result.win_count}\n"
              f"未中奖数量：{result.lose_count}\n"
              f"中奖金额：{_money(result.total_payout_amount)}\n"
              f"返水金额：{_money(result.total_rebate_amount)}\n"
              f"统计结算金额：{_money(result.statistic_net_amount)}\n"
              f"操作日志ID：{result.operation_log_id}"
          ),
      )

  def _apply_stylesheet(self) -> None:
      self.setStyleSheet(
          """
          QFrame#sectionFrame, QFrame#summaryFrame {
              border: 1px solid #bdc3c7;
              background: #ffffff;
          }
          QLabel#sectionTitle {
              font-weight: 600;
              font-size: 12px;
          }
          QLabel#hintLabel {
              color: #7f8c8d;
              font-size: 12px;
          }
          QComboBox, QPushButton {
              padding: 5px 10px;
              border: 1px solid #bdc3c7;
              background: #ffffff;
              font-size: 12px;
          }
          QPushButton:hover {
              background: #ebf5fb;
          }
          QPushButton#primaryBtn {
              background: #3498db;
              color: #ffffff;
              border: 1px solid #2980b9;
          }
          QPushButton#primaryBtn:hover {
              background: #5dade2;
          }
          QPushButton#primaryBtn:disabled {
              background: #bdc3c7;
              border-color: #95a5a6;
              color: #ecf0f1;
          }
          QPushButton#dangerBtn {
              background: #c0392b;
              color: #ffffff;
              border: 1px solid #922b21;
          }
          QPushButton#dangerBtn:hover {
              background: #e74c3c;
          }
          QPushButton#dangerBtn:disabled {
              background: #bdc3c7;
              border-color: #95a5a6;
              color: #ecf0f1;
          }
          QTableWidget {
              border: 1px solid #bdc3c7;
              font-size: 12px;
              gridline-color: #d5d8dc;
          }
          QHeaderView::section {
              background-color: #d6eaf8;
              padding: 6px 4px;
              border: 1px solid #aed6f1;
              font-weight: 600;
          }
          """
      )
