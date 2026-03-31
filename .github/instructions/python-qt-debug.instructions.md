---
description: "Use when debugging Python QT errors, analyzing PyQt5/PyQt6/PySide6 tracebacks, fixing GUI crashes, diagnosing signal-slot issues, resolving import errors, threading violations, or any runtime problem in QT applications. Trigger: qt报错, pyqt error, qt崩溃, qt调试, qt debug, qt exception, qt traceback, signal slot error, qt thread error, qt import error"
applyTo: "**/*.py"
---
# Python QT 调试与报错分析规范

## 一、报错分析流程

1. **定位错误类型**：先识别是 Python 异常、Qt 运行时错误还是逻辑 bug
2. **读取上下文**：查看报错行的前后代码，理解控件/信号槽的完整关系
3. **给出根因**：说明"为什么"会出现该错误，而不只是告诉"怎么改"
4. **提供最小修复**：只改出错的代码，不重构无关部分

---

## 二、常见错误速查与修复模式

### 2.1 模块导入错误

```
ModuleNotFoundError: No module named 'PyQt5'
```
- **原因**：PyQt5 未安装或虚拟环境不匹配
- **修复**：
  ```bash
  pip install PyQt5
  # 或 PySide6
  pip install PySide6
  ```
- **验证**：`python -c "from PyQt5.QtWidgets import QApplication; print('OK')"`

---

### 2.2 线程安全违规（最常见崩溃原因）

```
QObject: Cannot create children for a parent that is in a different thread.
RuntimeError: wrapped C++ object of type QLabel has been deleted
```
- **原因**：在 `QThread` 工作线程中直接操作 UI 控件
- **错误模式**：
  ```python
  # ? 错误：在工作线程中直接设置 UI
  class Worker(QThread):
      def run(self):
          self.label.setText("done")  # 危险！
  ```
- **正确模式**：通过信号将结果发回主线程
  ```python
  # ? 正确：用信号跨线程通信
  class Worker(QThread):
      result_ready = pyqtSignal(str)

      def run(self):
          self.result_ready.emit("done")  # 安全

  # 主线程连接
  worker.result_ready.connect(self.label.setText)
  ```

---

### 2.3 信号槽连接错误

```
TypeError: connect() failed between signal and slot
AttributeError: 'NoneType' object has no attribute 'connect'
```
- **原因①**：槽函数参数类型与信号不匹配
  ```python
  # ? 信号发出 int，槽接收 str
  self.value_changed = pyqtSignal(int)
  self.value_changed.connect(self.on_value)  # on_value(self, text: str) ← 类型不符
  ```
- **原因②**：控件尚未初始化就连接信号
  - **修复**：确保在 `init_ui()` 中先创建控件，再 `connect()`

---

### 2.4 对象已被销毁

```
RuntimeError: wrapped C++ object of type QPushButton has been deleted
```
- **原因**：Python 持有的 Qt 对象已被 C++ 层销毁（通常因为没有父对象）
- **修复**：为控件指定父对象，或确保其生命周期与窗口一致
  ```python
  # ? 局部变量，函数结束即销毁
  def init_ui(self):
      btn = QPushButton("Click")  # 没有 self. 前缀

  # ? 实例变量，随窗口存活
  def init_ui(self):
      self.btn = QPushButton("Click", self)
  ```

---

### 2.5 布局重复设置

```
QLayout: Attempting to add QLayout "" to MainWindow "", which already has a layout
```
- **修复**：每个 `QWidget` 只能调用一次 `setLayout()`，不要重复设置

---

### 2.6 `exec_()` vs `exec()` 兼容性

```
AttributeError: 'QApplication' object has no attribute 'exec_'
```
- **原因**：PyQt6 / PySide6 中已移除 `exec_()` 别名
- **修复**：
  ```python
  # PyQt5
  sys.exit(app.exec_())
  # PyQt6 / PySide6
  sys.exit(app.exec())
  ```

---

### 2.7 图标/资源文件找不到

```
QPixmap: unable to open file ':/icons/logo.png'
```
- **修复**：确认 `.qrc` 文件已编译为 `_rc.py`
  ```bash
  pyrcc5 resources.qrc -o resources_rc.py   # PyQt5
  pyside6-rcc resources.qrc -o resources_rc.py  # PySide6
  ```
  并在代码顶部导入：`import resources_rc`

---

### 2.8 `QApplication` 实例缺失

```
RuntimeError: A QApplication must be created before any QWidget
```
- **修复**：确保在创建任何控件前先实例化 `QApplication`
  ```python
  app = QApplication(sys.argv)   # 必须最先执行
  window = MainWindow()
  ```

---

## 三、调试技巧

### 3.1 捕获 Qt 原生警告

```python
import sys
from PyQt5.QtCore import qInstallMessageHandler, QtMsgType

def qt_message_handler(mode, context, message):
    if mode == QtMsgType.QtWarningMsg:
        print(f"[QT WARNING] {message}")
    elif mode == QtMsgType.QtCriticalMsg:
        print(f"[QT CRITICAL] {message}")

qInstallMessageHandler(qt_message_handler)
```

### 3.2 全局异常钩子（防止 Qt 吞掉异常）

```python
import sys
import traceback

def exception_hook(exc_type, exc_value, exc_tb):
    traceback.print_exception(exc_type, exc_value, exc_tb)
    sys.exit(1)

sys.excepthook = exception_hook
```
> 将此代码放在 `QApplication` 创建之前，避免异常被 Qt 事件循环静默忽略。

### 3.3 信号槽调试打印

```python
# 验证信号是否触发
self.btn.clicked.connect(lambda: print("[DEBUG] button clicked"))
```

### 3.4 检查控件是否存在

```python
assert hasattr(self, 'btn'), "btn 未初始化，检查 init_ui() 调用顺序"
assert self.btn is not None, "btn 为 None，控件创建失败"
```

---

## 四、报错回答格式要求

分析用户的 Python QT 错误时，回答必须包含：

1. **错误类型**（一句话概括）
2. **根本原因**（解释为什么出错）
3. **修复代码**（最小改动，含注释）
4. **预防建议**（避免同类错误的一句话原则）
