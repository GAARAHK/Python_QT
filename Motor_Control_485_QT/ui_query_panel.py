# -*- coding: gbk -*-
"""
数据查询与导出 Widget
支持按二维码/报警查询，导出 Excel/CSV。
"""
import csv
import os
import datetime

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QComboBox,
    QFileDialog, QMessageBox, QTabWidget, QGroupBox, QHeaderView
)
from PyQt5.QtCore import Qt

from database import (
    query_history_by_qrcode, query_current_logs_by_batch,
    query_alarm_logs, get_available_log_tables, get_conn
)


class QueryPanel(QWidget):
    """历史数据查询与导出"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)

        tabs = QTabWidget()
        tabs.addTab(self._build_history_tab(),  "运行历史")
        tabs.addTab(self._build_current_tab(),  "电流记录")
        tabs.addTab(self._build_alarm_tab(),    "报警记录")
        root.addWidget(tabs)

    # ── 运行历史 Tab ──────────────────────────────────────────────────
    def _build_history_tab(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("二维码："))
        self._hist_qr = QLineEdit()
        self._hist_qr.setPlaceholderText("输入或扫码")
        self._hist_qr.returnPressed.connect(self._search_history)
        search_row.addWidget(self._hist_qr)
        btn = QPushButton("查询")
        btn.clicked.connect(self._search_history)
        search_row.addWidget(btn)
        export_btn = QPushButton("导出CSV")
        export_btn.clicked.connect(lambda: self._export_table(self._hist_table, "运行历史"))
        search_row.addWidget(export_btn)
        vbox.addLayout(search_row)

        self._hist_table = QTableWidget(0, 6)
        self._hist_table.setHorizontalHeaderLabels(
            ["批次UUID", "电机ID", "二维码", "开始时间", "结束时间", "状态"]
        )
        self._hist_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._hist_table.setEditTriggers(QTableWidget.NoEditTriggers)
        vbox.addWidget(self._hist_table)
        return w

    def _search_history(self):
        qr = self._hist_qr.text().strip()
        if not qr:
            return
        rows = query_history_by_qrcode(qr)
        self._fill_table(self._hist_table,
                         ["batch_uuid", "motor_id", "qr_code",
                          "start_time", "end_time", "end_status"],
                         rows)

    # ── 电流记录 Tab ──────────────────────────────────────────────────
    def _build_current_tab(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("批次UUID："))
        self._cur_uuid = QLineEdit()
        self._cur_uuid.setPlaceholderText("从运行历史复制批次UUID")
        search_row.addWidget(self._cur_uuid)

        search_row.addWidget(QLabel("月份："))
        self._month_combo = QComboBox()
        self._refresh_month_combo()
        search_row.addWidget(self._month_combo)

        btn = QPushButton("查询")
        btn.clicked.connect(self._search_current)
        search_row.addWidget(btn)

        export_btn = QPushButton("导出Excel")
        export_btn.clicked.connect(self._export_current_excel)
        search_row.addWidget(export_btn)

        export_csv_btn = QPushButton("导出CSV")
        export_csv_btn.clicked.connect(lambda: self._export_table(self._cur_table, "电流记录"))
        search_row.addWidget(export_csv_btn)
        vbox.addLayout(search_row)

        self._cur_table = QTableWidget(0, 6)
        self._cur_table.setHorizontalHeaderLabels(
            ["ID", "批次UUID", "电机ID", "二维码", "循环次数", "电流(A)"]
        )
        self._cur_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._cur_table.setEditTriggers(QTableWidget.NoEditTriggers)
        vbox.addWidget(self._cur_table)
        return w

    def _refresh_month_combo(self):
        self._month_combo.clear()
        conn = get_conn()
        tables = get_available_log_tables(conn)
        conn.close()
        suffixes = [t.replace("current_logs_", "") for t in tables]
        if not suffixes:
            suffixes = [datetime.datetime.now().strftime("%Y_%m")]
        for s in suffixes:
            self._month_combo.addItem(s.replace("_", "-"), s)

    def _search_current(self):
        uuid_str = self._cur_uuid.text().strip()
        if not uuid_str:
            return
        suffix = self._month_combo.currentData()
        rows = query_current_logs_by_batch(uuid_str, suffix)
        self._fill_table(self._cur_table,
                         ["id", "batch_uuid", "motor_id",
                          "qr_code", "loop_count", "read_current"],
                         rows)

    def _export_current_excel(self):
        uuid_str = self._cur_uuid.text().strip()
        if not uuid_str:
            QMessageBox.warning(self, "提示", "请先输入批次UUID并查询")
            return
        self._export_table(self._cur_table, "电流记录", to_excel=True)

    # ── 报警记录 Tab ──────────────────────────────────────────────────
    def _build_alarm_tab(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("二维码（留空查全部）："))
        self._alarm_qr = QLineEdit()
        self._alarm_qr.setPlaceholderText("留空查全部报警")
        search_row.addWidget(self._alarm_qr)
        btn = QPushButton("查询")
        btn.clicked.connect(self._search_alarm)
        search_row.addWidget(btn)
        export_btn = QPushButton("导出CSV")
        export_btn.clicked.connect(lambda: self._export_table(self._alarm_table, "报警记录"))
        search_row.addWidget(export_btn)
        vbox.addLayout(search_row)

        self._alarm_table = QTableWidget(0, 7)
        self._alarm_table.setHorizontalHeaderLabels(
            ["ID", "批次UUID", "电机ID", "二维码", "循环次数", "超标电流", "时间"]
        )
        self._alarm_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._alarm_table.setEditTriggers(QTableWidget.NoEditTriggers)
        vbox.addWidget(self._alarm_table)
        return w

    def _search_alarm(self):
        qr = self._alarm_qr.text().strip() or None
        rows = query_alarm_logs(qr_code=qr)
        self._fill_table(self._alarm_table,
                         ["id", "batch_uuid", "motor_id",
                          "qr_code", "loop_count", "alarm_value", "timestamp"],
                         rows)

    # ── 工具方法 ──────────────────────────────────────────────────────
    @staticmethod
    def _fill_table(table: QTableWidget, cols: list, rows: list):
        table.setRowCount(0)
        for record in rows:
            r = table.rowCount()
            table.insertRow(r)
            for c, col in enumerate(cols):
                val = record.get(col, "")
                if val is None:
                    val = ""
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignCenter)
                table.setItem(r, c, item)

    def _export_table(self, table: QTableWidget, default_name: str,
                      to_excel: bool = False):
        if table.rowCount() == 0:
            QMessageBox.information(self, "提示", "没有数据可导出")
            return

        if to_excel:
            try:
                import openpyxl   # 可选依赖
                self._do_export_excel(table, default_name)
                return
            except ImportError:
                QMessageBox.warning(self, "提示",
                                    "未安装 openpyxl，将改用 CSV 格式导出。\n"
                                    "可运行: pip install openpyxl")

        # CSV 导出
        path, _ = QFileDialog.getSaveFileName(
            self, "保存 CSV", f"{default_name}.csv",
            "CSV Files (*.csv);;All Files (*)"
        )
        if not path:
            return
        headers = [table.horizontalHeaderItem(c).text()
                   for c in range(table.columnCount())]
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for r in range(table.rowCount()):
                row_data = [table.item(r, c).text() if table.item(r, c) else ""
                            for c in range(table.columnCount())]
                writer.writerow(row_data)
        QMessageBox.information(self, "导出成功", f"已保存到：\n{path}")

    def _do_export_excel(self, table: QTableWidget, default_name: str):
        import openpyxl
        path, _ = QFileDialog.getSaveFileName(
            self, "保存 Excel", f"{default_name}.xlsx",
            "Excel Files (*.xlsx);;All Files (*)"
        )
        if not path:
            return
        wb = openpyxl.Workbook()
        ws = wb.active
        headers = [table.horizontalHeaderItem(c).text()
                   for c in range(table.columnCount())]
        ws.append(headers)
        for r in range(table.rowCount()):
            row_data = [table.item(r, c).text() if table.item(r, c) else ""
                        for c in range(table.columnCount())]
            ws.append(row_data)
        wb.save(path)
        QMessageBox.information(self, "导出成功", f"已保存到：\n{path}")
