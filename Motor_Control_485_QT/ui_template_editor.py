# -*- coding: gbk -*-
"""
工况模板配置 Widget
支持：新增/编辑/删除工况模板，设置各段动作+时长、循环次数、采集间隔、报警阈值。
"""
import json
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QDoubleSpinBox,
    QSpinBox, QComboBox, QTableWidget, QTableWidgetItem,
    QGroupBox, QMessageBox, QHeaderView
)
from PyQt5.QtCore import Qt, pyqtSignal

from database import save_template, load_templates, delete_template


class TemplateEditor(QWidget):
    """工况模板编辑器"""
    templates_changed = pyqtSignal()    # 通知外部刷新模板列表

    def __init__(self, parent=None):
        super().__init__(parent)
        self._editing_id = None         # None = 新增模式
        self._build()
        self._refresh_table()

    def _build(self):
        root = QHBoxLayout(self)
        root.setSpacing(12)

        # ── 左侧：模板列表 ────────────────────────────────────────────
        left = QVBoxLayout()
        lbl = QLabel("已保存的工况模板")
        lbl.setStyleSheet("font-weight: bold; font-size: 13px;")
        left.addWidget(lbl)

        self._tbl = QTableWidget(0, 3)
        self._tbl.setHorizontalHeaderLabels(["ID", "名称", "循环次数"])
        self._tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._tbl.setSelectionBehavior(QTableWidget.SelectRows)
        self._tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tbl.itemSelectionChanged.connect(self._on_select)
        left.addWidget(self._tbl)

        btn_row = QHBoxLayout()
        self._btn_load   = QPushButton("载入编辑")
        self._btn_delete = QPushButton("删除")
        self._btn_new    = QPushButton("新建")
        btn_row.addWidget(self._btn_new)
        btn_row.addWidget(self._btn_load)
        btn_row.addWidget(self._btn_delete)
        left.addLayout(btn_row)

        self._btn_load.clicked.connect(self._load_selected)
        self._btn_delete.clicked.connect(self._delete_selected)
        self._btn_new.clicked.connect(self._new_template)

        # ── 右侧：编辑区 ─────────────────────────────────────────────
        right = QVBoxLayout()

        name_box = QGroupBox("基本信息")
        name_grid = QGridLayout(name_box)
        name_grid.addWidget(QLabel("模板名称"), 0, 0)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("例如: 正反转-30s")
        name_grid.addWidget(self._name_edit, 0, 1)

        name_grid.addWidget(QLabel("目标循环次数"), 1, 0)
        self._loops_spin = QSpinBox()
        self._loops_spin.setRange(1, 99999)
        self._loops_spin.setValue(100)
        name_grid.addWidget(self._loops_spin, 1, 1)

        name_grid.addWidget(QLabel("采集间隔（每N次）"), 2, 0)
        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(1, 9999)
        self._interval_spin.setValue(10)
        name_grid.addWidget(self._interval_spin, 2, 1)

        right.addWidget(name_box)

        alarm_box = QGroupBox("报警阈值（电流 A）")
        alarm_grid = QGridLayout(alarm_box)
        alarm_grid.addWidget(QLabel("下限"), 0, 0)
        self._alarm_min = QDoubleSpinBox()
        self._alarm_min.setRange(0, 100)
        self._alarm_min.setDecimals(2)
        self._alarm_min.setValue(0.1)
        alarm_grid.addWidget(self._alarm_min, 0, 1)

        alarm_grid.addWidget(QLabel("上限"), 0, 2)
        self._alarm_max = QDoubleSpinBox()
        self._alarm_max.setRange(0, 100)
        self._alarm_max.setDecimals(2)
        self._alarm_max.setValue(5.0)
        alarm_grid.addWidget(self._alarm_max, 0, 3)
        right.addWidget(alarm_box)

        step_box = QGroupBox("动作步骤（按顺序执行，循环运行）")
        step_vbox = QVBoxLayout(step_box)

        self._step_table = QTableWidget(0, 2)
        self._step_table.setHorizontalHeaderLabels(["动作", "持续时长(秒)"])
        self._step_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        step_vbox.addWidget(self._step_table)

        step_btn = QHBoxLayout()
        btn_add_step  = QPushButton("＋ 添加步骤")
        btn_del_step  = QPushButton("－ 删除步骤")
        btn_up        = QPushButton("↑")
        btn_down      = QPushButton("↓")
        step_btn.addWidget(btn_add_step)
        step_btn.addWidget(btn_del_step)
        step_btn.addWidget(btn_up)
        step_btn.addWidget(btn_down)
        step_vbox.addLayout(step_btn)

        btn_add_step.clicked.connect(self._add_step)
        btn_del_step.clicked.connect(self._del_step)
        btn_up.clicked.connect(self._move_up)
        btn_down.clicked.connect(self._move_down)

        right.addWidget(step_box)

        import styles as _s
        save_btn = QPushButton("保存工况模板")
        save_btn.setFixedHeight(38)
        save_btn.setStyleSheet(_s.BTN_PRIMARY)
        save_btn.clicked.connect(self._save_template)
        right.addWidget(save_btn)

        root.addLayout(left, 2)
        root.addLayout(right, 3)

        # 默认添加两个步骤
        self._add_step("forward", 30)
        self._add_step("reverse", 30)

    # ── 步骤操作 ──────────────────────────────────────────────────────
    def _add_step(self, action: str = "forward", duration: float = 10):
        row = self._step_table.rowCount()
        self._step_table.insertRow(row)

        combo = QComboBox()
        combo.addItems(["forward（正转）", "reverse（反转）", "stop（停止）"])
        if action == "reverse":
            combo.setCurrentIndex(1)
        elif action == "stop":
            combo.setCurrentIndex(2)
        self._step_table.setCellWidget(row, 0, combo)

        spin = QDoubleSpinBox()
        spin.setRange(0.5, 3600)
        spin.setDecimals(1)
        spin.setValue(duration)
        self._step_table.setCellWidget(row, 1, spin)

    def _del_step(self):
        row = self._step_table.currentRow()
        if row >= 0:
            self._step_table.removeRow(row)

    def _move_up(self):
        row = self._step_table.currentRow()
        if row > 0:
            self._swap_rows(row - 1, row)
            self._step_table.selectRow(row - 1)

    def _move_down(self):
        row = self._step_table.currentRow()
        if row < self._step_table.rowCount() - 1:
            self._swap_rows(row, row + 1)
            self._step_table.selectRow(row + 1)

    def _swap_rows(self, r1: int, r2: int):
        # 读出两行的 widget 参数值，交换
        combo1 = self._step_table.cellWidget(r1, 0)
        spin1  = self._step_table.cellWidget(r1, 1)
        combo2 = self._step_table.cellWidget(r2, 0)
        spin2  = self._step_table.cellWidget(r2, 1)

        idx1, val1 = combo1.currentIndex(), spin1.value()
        idx2, val2 = combo2.currentIndex(), spin2.value()

        combo1.setCurrentIndex(idx2)
        spin1.setValue(val2)
        combo2.setCurrentIndex(idx1)
        spin2.setValue(val1)

    # ── 模板保存/加载 ─────────────────────────────────────────────────
    def _save_template(self):
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入模板名称")
            return
        if self._step_table.rowCount() == 0:
            QMessageBox.warning(self, "提示", "请至少添加一个动作步骤")
            return

        action_map = {0: "forward", 1: "reverse", 2: "stop"}
        steps = []
        for r in range(self._step_table.rowCount()):
            combo = self._step_table.cellWidget(r, 0)
            spin  = self._step_table.cellWidget(r, 1)
            steps.append({
                "action":     action_map[combo.currentIndex()],
                "duration_s": spin.value()
            })

        save_template(
            name, steps,
            self._loops_spin.value(),
            self._interval_spin.value(),
            self._alarm_min.value(),
            self._alarm_max.value()
        )
        QMessageBox.information(self, "成功", f"工况模板「{name}」已保存")
        self._refresh_table()
        self.templates_changed.emit()

    def _refresh_table(self):
        self._tbl.setRowCount(0)
        for tmpl in load_templates():
            r = self._tbl.rowCount()
            self._tbl.insertRow(r)
            self._tbl.setItem(r, 0, QTableWidgetItem(str(tmpl["id"])))
            self._tbl.setItem(r, 1, QTableWidgetItem(tmpl["name"]))
            self._tbl.setItem(r, 2, QTableWidgetItem(str(tmpl["target_loops"])))

    def _on_select(self):
        pass   # 仅用于按钮启用/禁用可扩展

    def _load_selected(self):
        row = self._tbl.currentRow()
        if row < 0:
            return
        tid = int(self._tbl.item(row, 0).text())
        templates = {t["id"]: t for t in load_templates()}
        tmpl = templates.get(tid)
        if not tmpl:
            return
        self._name_edit.setText(tmpl["name"])
        self._loops_spin.setValue(tmpl["target_loops"])
        self._interval_spin.setValue(tmpl["collect_interval"])
        self._alarm_min.setValue(tmpl["alarm_min"])
        self._alarm_max.setValue(tmpl["alarm_max"])

        self._step_table.setRowCount(0)
        action_idx = {"forward": 0, "reverse": 1, "stop": 2}
        for step in tmpl["steps"]:
            self._add_step(step["action"], step["duration_s"])

    def _delete_selected(self):
        row = self._tbl.currentRow()
        if row < 0:
            return
        name = self._tbl.item(row, 1).text()
        tid  = int(self._tbl.item(row, 0).text())
        ret = QMessageBox.question(self, "确认删除",
                                   f"确定删除工况模板「{name}」？",
                                   QMessageBox.Yes | QMessageBox.No)
        if ret == QMessageBox.Yes:
            delete_template(tid)
            self._refresh_table()
            self.templates_changed.emit()

    def _new_template(self):
        self._editing_id = None
        self._name_edit.clear()
        self._loops_spin.setValue(100)
        self._interval_spin.setValue(10)
        self._alarm_min.setValue(0.1)
        self._alarm_max.setValue(5.0)
        self._step_table.setRowCount(0)
        self._add_step("forward", 30)
        self._add_step("reverse", 30)

    def get_templates(self) -> list:
        return load_templates()
