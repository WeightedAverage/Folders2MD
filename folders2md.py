#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Folders2MD - 文件夹结构转 Markdown 工具
基于 PyQt5 实现，支持拖拽，深色主题
功能：文件命名优化、保存后打开文件夹、文件夹屏蔽、日志记录
"""

import json
import logging
import os
import platform
import re
import subprocess
import sys
import time
import warnings
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Optional

from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QDragEnterEvent, QDropEvent, QIcon, QPainter, QColor, QFont, QPen
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

warnings.filterwarnings("ignore", category=DeprecationWarning)

# ============================================================
# 日志系统
# ============================================================

LOGS_DIR = "logs"
MAX_LOG_BYTES = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5


class JsonFormatter(logging.Formatter):
    """JSON 格式日志格式化器"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "level": record.levelname,
            "logger": record.name,
            "operation": getattr(record, "operation", "UNKNOWN"),
            "target_path": getattr(record, "target_path", ""),
            "result": getattr(record, "result", "INFO"),
            "error": getattr(record, "error", ""),
            "duration_ms": getattr(record, "duration_ms", 0),
            "details": getattr(record, "details", {}),
            "message": record.getMessage(),
            "thread": record.thread,
        }
        return json.dumps(log_entry, ensure_ascii=False)


class DailyRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """支持按日期命名并自动轮转的日志处理器"""

    def __init__(self, filename: str, maxBytes: int = 0, backupCount: int = 0, encoding: Optional[str] = None) -> None:
        self.base_filename = filename
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        super().__init__(filename, maxBytes=maxBytes, backupCount=backupCount, encoding=encoding)

    def emit(self, record: logging.LogRecord) -> None:
        """检查日期是否变化，如变化则切换日志文件"""
        now_date = datetime.now().strftime("%Y-%m-%d")
        if now_date != self.current_date:
            self.current_date = now_date
            logs_dir = os.path.dirname(self.base_filename)
            new_filename = os.path.join(logs_dir, f"{now_date}.log")
            self.baseFilename = new_filename
            if self.stream:
                self.stream.close()
                self.stream = None
        super().emit(record)


class AppLogger:
    """应用程序日志管理器"""

    _instance = None
    _logger = None
    _enabled = False
    _handler = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._logger is not None:
            return
        self._logger = logging.getLogger("Folders2MD")
        self._logger.setLevel(logging.DEBUG)
        self._update_handler()

    def _get_logs_dir(self) -> str:
        """获取日志目录路径"""
        if getattr(sys, "frozen", False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_dir, LOGS_DIR)

    def _update_handler(self) -> None:
        """更新日志处理器"""
        if self._handler:
            self._logger.removeHandler(self._handler)
            self._handler.close()
            self._handler = None

        if not self._enabled:
            return

        logs_dir = self._get_logs_dir()
        os.makedirs(logs_dir, exist_ok=True)

        today = datetime.now().strftime("%Y-%m-%d")
        log_file = os.path.join(logs_dir, f"{today}.log")

        self._handler = DailyRotatingFileHandler(
            log_file,
            maxBytes=MAX_LOG_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        self._handler.setFormatter(JsonFormatter())
        self._logger.addHandler(self._handler)

    def set_enabled(self, enabled: bool) -> None:
        """启用或禁用日志"""
        self._enabled = enabled
        self._update_handler()

    def is_enabled(self) -> bool:
        """检查日志是否启用"""
        return self._enabled

    def log_operation(
        self,
        operation: str,
        target_path: str = "",
        result: str = "SUCCESS",
        error: str = "",
        duration_ms: float = 0,
        details: Optional[dict] = None,
        level: int = logging.INFO,
    ) -> None:
        """记录操作日志"""
        if not self._enabled or not self._handler:
            return

        extra = {
            "operation": operation,
            "target_path": target_path,
            "result": result,
            "error": error,
            "duration_ms": round(duration_ms, 3),
            "details": details or {},
        }
        self._logger.log(level, f"{operation}: {target_path}", extra=extra)

    def log_scan_progress(self, current_path: str, depth: int, entry_count: int) -> None:
        """记录扫描进度（用于诊断深层目录卡死）"""
        if not self._enabled or not self._handler:
            return
        self.log_operation(
            operation="SCAN_PROGRESS",
            target_path=current_path,
            details={"depth": depth, "entry_count": entry_count},
            level=logging.DEBUG,
        )


# 全局日志实例
app_logger = AppLogger()


# ============================================================
# 配置管理
# ============================================================

CONFIG_FILE = "folders2md_config.json"


def get_config_path() -> str:
    """获取配置文件路径"""
    if getattr(sys, "frozen", False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, CONFIG_FILE)


def load_config() -> dict:
    """加载配置文件"""
    config_path = get_config_path()
    default_config = {"blocked_folders": [], "logging_enabled": False}
    if not os.path.exists(config_path):
        return default_config
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
            # 确保新配置项存在
            for key, val in default_config.items():
                if key not in loaded:
                    loaded[key] = val
            return loaded
    except (json.JSONDecodeError, OSError):
        return default_config


def save_config(config: dict) -> None:
    """保存配置到文件"""
    config_path = get_config_path()
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"保存配置失败: {e}")


# ============================================================
# 工具函数
# ============================================================

def sanitize_filename(name: str) -> str:
    """清理文件名中的非法字符"""
    sanitized = re.sub(r'[<>:"/\\|?*]', "", name)
    sanitized = sanitized.strip(" .")
    if len(sanitized) > 240:
        sanitized = sanitized[:240]
    if not sanitized:
        sanitized = "untitled"
    return sanitized


def open_folder_in_explorer(folder_path: str) -> bool:
    """跨平台打开文件夹"""
    system = platform.system()
    try:
        if system == "Windows":
            os.startfile(folder_path)
        elif system == "Darwin":
            subprocess.run(["open", folder_path], check=True)
        else:
            subprocess.run(["xdg-open", folder_path], check=True)
        return True
    except Exception:
        return False


# ============================================================
# 后台线程：扫描文件夹（避免阻塞主线程）
# ============================================================

class ScanWorker(QThread):
    """后台扫描线程"""

    finished_signal = pyqtSignal(str, list)
    error_signal = pyqtSignal(str)

    def __init__(self, root_path: str, blocked_names: set) -> None:
        super().__init__()
        self.root_path = root_path
        self.blocked_names = blocked_names
        self._is_cancelled = False

    def cancel(self) -> None:
        """安全取消扫描"""
        self._is_cancelled = True

    def is_cancelled(self) -> bool:
        """检查是否已取消"""
        return self._is_cancelled

    def run(self) -> None:
        start_time = time.time()
        try:
            app_logger.log_operation(
                operation="SCAN_START",
                target_path=self.root_path,
                details={"blocked_count": len(self.blocked_names)},
            )

            tree_data = self._build_tree_data(self.root_path)

            # 如果已取消，不发送结果
            if self._is_cancelled:
                return

            md_text = self._format_markdown(self.root_path, tree_data)

            duration = (time.time() - start_time) * 1000
            app_logger.log_operation(
                operation="SCAN_COMPLETE",
                target_path=self.root_path,
                result="SUCCESS",
                duration_ms=duration,
                details={"node_count": len(tree_data)},
            )
            if not self._is_cancelled:
                self.finished_signal.emit(md_text, tree_data)
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            app_logger.log_operation(
                operation="SCAN_FAILED",
                target_path=self.root_path,
                result="FAILED",
                error=str(e),
                duration_ms=duration,
            )
            if not self._is_cancelled:
                self.error_signal.emit(str(e))

    def _build_tree_data(self, root_path: str) -> list:
        """构建树形数据"""
        result = []
        visited = set()  # 防止循环符号链接导致无限递归
        self._scan_dir(root_path, 0, result, visited)
        return result

    def _scan_dir(self, path: str, level: int, result: list, visited: set) -> None:
        """递归扫描目录，带循环链接检测"""
        if self._is_cancelled:
            return

        # 循环符号链接检测
        try:
            real_path = os.path.realpath(path)
            if real_path in visited:
                result.append((level, "<循环链接>", True, False))
                app_logger.log_operation(
                    operation="SYMLINK_LOOP",
                    target_path=path,
                    result="WARNING",
                    details={"real_path": real_path},
                )
                return
            visited.add(real_path)
        except OSError:
            pass

        try:
            entries = sorted(os.listdir(path))
        except PermissionError as e:
            result.append((level, "<无法访问>", True, False))
            app_logger.log_operation(
                operation="DIR_ACCESS_DENIED",
                target_path=path,
                result="FAILED",
                error=str(e),
            )
            return
        except OSError as e:
            result.append((level, "<无法读取>", True, False))
            app_logger.log_operation(
                operation="DIR_READ_ERROR",
                target_path=path,
                result="FAILED",
                error=str(e),
            )
            return

        # 记录扫描进度（用于诊断深层目录卡死）
        app_logger.log_scan_progress(path, level, len(entries))

        for entry in entries:
            if self._is_cancelled:
                return

            full_path = os.path.join(path, entry)
            is_dir = os.path.isdir(full_path)
            is_blocked = is_dir and entry in self.blocked_names

            result.append((level, entry, is_dir, is_blocked))

            if is_dir and not is_blocked:
                self._scan_dir(full_path, level + 1, result, visited)

    def _format_markdown(self, root_path: str, tree_data: list) -> str:
        """格式化 Markdown 输出"""
        root_name = os.path.basename(os.path.normpath(root_path))
        lines = [f"# 📁 {root_name}", "", "```", root_name]

        for level, name, is_dir, is_blocked in tree_data:
            prefix = "│   " * level
            connector = "├── "
            lines.append(prefix + connector + name)
            if is_blocked:
                lines.append(prefix + "│   └── <已屏蔽>")

        lines.append("```")
        lines.append("")
        return "\n".join(lines)

    def _build_block_note(self, root_path: str, blocked_names: set) -> str:
        """构建屏蔽信息备注（使用相对路径）"""
        if not blocked_names:
            return ""

        root_name = os.path.basename(os.path.normpath(root_path))
        # 相对路径格式: root_name/blocked_name
        relative_paths = sorted([f"{root_name}/{name}" for name in blocked_names])

        if len(relative_paths) == 1:
            return f"\n> 屏蔽了{relative_paths[0]}文件夹\n"
        else:
            paths_str = "、".join(relative_paths)
            return f"\n> 屏蔽了{paths_str}等文件夹\n"


# ============================================================
# 文件选择树面板（勾选机制）
# ============================================================

class FileTreePanel(QTreeWidget):
    """带勾选框的文件树面板，延迟加载避免大目录卡死"""

    item_toggled = pyqtSignal(str, bool)

    MAX_VISIBLE_NODES = 2000
    INITIAL_EXPAND_DEPTH = 2

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setColumnCount(1)
        self.setStyleSheet("""
            QTreeWidget {
                background-color: #1e1e1e;
                color: #dcdcdc;
                border: 1px solid #444;
                border-radius: 6px;
                padding: 6px;
                font-family: "Consolas", "Cascadia Code", monospace;
                font-size: 10pt;
                outline: none;
            }
            QTreeWidget::item {
                padding: 3px 0px;
                min-height: 20px;
            }
            QTreeWidget::item:selected {
                background-color: #264f78;
            }
            QTreeWidget::item:hover {
                background-color: #2a3f5c;
            }
            QTreeWidget::indicator {
                width: 14px;
                height: 14px;
            }
            QTreeWidget::indicator:unchecked {
                background-color: #3c3c3c;
                border: 1px solid #666;
                border-radius: 3px;
            }
            QTreeWidget::indicator:checked {
                background-color: #0078d4;
                border: 1px solid #0078d4;
                border-radius: 3px;
            }
        """)
        self.itemChanged.connect(self._on_item_changed)
        self.itemExpanded.connect(self._on_item_expanded)
        self._path_map = {}
        self._blocked_names = set()
        self._node_count = 0
        self._loaded_items = set()

    def load_directory(self, root_path: str, blocked_names: set) -> None:
        """加载目录到树形控件（延迟加载，仅展开前2层）"""
        # 加载时断开信号，避免勾选联动风暴
        self.itemChanged.disconnect(self._on_item_changed)

        self.clear()
        self._path_map.clear()
        self._loaded_items.clear()
        self._blocked_names = blocked_names
        self._node_count = 0

        root_name = os.path.basename(os.path.normpath(root_path))
        root_item = QTreeWidgetItem(self)
        root_item.setText(0, root_name)
        root_item.setFlags(root_item.flags() | Qt.ItemIsUserCheckable)
        root_item.setCheckState(0, Qt.Checked)
        root_item.setData(0, Qt.UserRole, root_path)
        self._path_map[id(root_item)] = root_path
        self._node_count = 1

        # 加载前2层
        self._add_children_lazy(root_item, root_path, depth=1)

        # 展开根节点
        self.expandItem(root_item)

        # 重新连接信号
        self.itemChanged.connect(self._on_item_changed)

    def _add_children_lazy(self, parent_item: QTreeWidgetItem, path: str, depth: int) -> None:
        """延迟加载子项：只加载到指定深度，更深层标记为待加载"""
        if self._node_count >= self.MAX_VISIBLE_NODES:
            return

        try:
            entries = sorted(os.listdir(path))
        except (PermissionError, OSError):
            return

        for entry in entries:
            if self._node_count >= self.MAX_VISIBLE_NODES:
                # 超出限制，添加省略提示
                remaining = QTreeWidgetItem(parent_item)
                remaining.setText(0, f"... (共 {len(entries)} 项，仅显示前 {self._node_count} 项)")
                remaining.setFlags(Qt.ItemIsEnabled)
                remaining.setData(0, Qt.UserRole, "")
                break

            full_path = os.path.join(path, entry)
            is_dir = os.path.isdir(full_path)
            is_blocked = is_dir and entry in self._blocked_names

            child = QTreeWidgetItem(parent_item)
            display_name = entry if not is_blocked else f"{entry} (已屏蔽)"
            child.setText(0, display_name)
            child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
            child.setCheckState(0, Qt.Checked)
            child.setData(0, Qt.UserRole, full_path)
            self._path_map[id(child)] = full_path
            self._node_count += 1

            if is_dir and not is_blocked:
                if depth < self.INITIAL_EXPAND_DEPTH:
                    # 在初始深度内，递归加载
                    self._add_children_lazy(child, full_path, depth + 1)
                else:
                    # 超出初始深度，添加占位子项（展开时再加载）
                    placeholder = QTreeWidgetItem(child)
                    placeholder.setText(0, "加载中...")
                    placeholder.setData(0, Qt.UserRole, "__placeholder__")
                    child.setData(0, Qt.UserRole + 1, full_path)

    def _on_item_expanded(self, item: QTreeWidgetItem) -> None:
        """展开时延迟加载子目录"""
        item_id = id(item)

        # 检查是否已加载
        if item_id in self._loaded_items:
            return

        # 获取真实路径（可能存储在 UserRole+1 中）
        full_path = item.data(0, Qt.UserRole + 1) or item.data(0, Qt.UserRole)
        if not full_path or not os.path.isdir(full_path):
            return

        # 检查是否有占位子项
        if item.childCount() == 1 and item.child(0).data(0, Qt.UserRole) == "__placeholder__":
            # 断开信号避免勾选风暴
            self.itemChanged.disconnect(self._on_item_changed)

            # 移除占位项
            item.takeChild(0)

            # 加载实际子项
            self._add_children_lazy(item, full_path, depth=self.INITIAL_EXPAND_DEPTH + 1)

            # 标记为已加载
            self._loaded_items.add(item_id)

            # 重新连接信号
            self.itemChanged.connect(self._on_item_changed)

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """勾选状态改变时同步子项和父项"""
        if column != 0:
            return

        state = item.checkState(0)
        path = item.data(0, Qt.UserRole)

        # 断开信号避免递归风暴
        self.itemChanged.disconnect(self._on_item_changed)
        self._sync_children(item, state)
        self._sync_parent(item)
        self.itemChanged.connect(self._on_item_changed)

        if path:
            self.item_toggled.emit(path, state == Qt.Checked)

    def _sync_children(self, item: QTreeWidgetItem, state: int) -> None:
        """同步所有子项的勾选状态"""
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, state)
            self._sync_children(child, state)

    def _sync_parent(self, item: QTreeWidgetItem) -> None:
        """同步父项的勾选状态"""
        parent = item.parent()
        if not parent:
            return

        checked_count = 0
        partial_count = 0
        for i in range(parent.childCount()):
            child_state = parent.child(i).checkState(0)
            if child_state == Qt.Checked:
                checked_count += 1
            elif child_state == Qt.PartiallyChecked:
                partial_count += 1

        if checked_count == parent.childCount():
            parent.setCheckState(0, Qt.Checked)
        elif checked_count == 0 and partial_count == 0:
            parent.setCheckState(0, Qt.Unchecked)
        else:
            parent.setCheckState(0, Qt.PartiallyChecked)

        self._sync_parent(parent)

    def get_checked_paths(self) -> list:
        """获取所有勾选的路径"""
        paths = []
        self._collect_checked(self.invisibleRootItem(), paths)
        return paths

    def _collect_checked(self, item: QTreeWidgetItem, paths: list) -> None:
        """递归收集勾选的路径"""
        for i in range(item.childCount()):
            child = item.child(i)
            if child.checkState(0) in (Qt.Checked, Qt.PartiallyChecked):
                path = child.data(0, Qt.UserRole)
                if path:
                    paths.append(path)
                self._collect_checked(child, paths)


# ============================================================
# 屏蔽列表管理对话框
# ============================================================

class BlockListDialog(QDialog):
    """屏蔽列表管理对话框，递归展示所有层级子文件夹，点击勾选屏蔽"""

    def __init__(self, current_path: str, blocked_folders: list, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("屏蔽文件夹")
        self.setMinimumSize(520, 600)
        self.current_path = current_path
        self.blocked_folders = set(blocked_folders)
        self._setup_ui()
        self._apply_styles()
        self._load_tree()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        # 标题
        title = QLabel("🚫 屏蔽文件夹")
        title.setStyleSheet("color: #e0e0e0; font-size: 12pt; font-weight: bold; padding: 0;")
        layout.addWidget(title)

        # 当前路径
        path_label = QLabel(f"当前目录: {self.current_path}")
        path_label.setWordWrap(True)
        path_label.setStyleSheet("color: #888; font-size: 9pt; padding: 0;")
        layout.addWidget(path_label)

        # 说明
        hint = QLabel("勾选要屏蔽的文件夹，扫描时将跳过这些目录及其所有子目录")
        hint.setStyleSheet("color: #a0a0a0; font-size: 9pt; padding: 0;")
        layout.addWidget(hint)

        # 树形控件（带勾选框）
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(1)
        self.tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.tree)

        # 已屏蔽数量提示
        self._count_label = QLabel(f"已屏蔽 {len(self.blocked_folders)} 个文件夹")
        self._count_label.setStyleSheet("color: #888; font-size: 9pt; padding: 0;")
        layout.addWidget(self._count_label)

        # 底部按钮
        btn_layout = QHBoxLayout()
        self.btn_expand = QPushButton("📂 展开全部")
        self.btn_expand.setCursor(Qt.PointingHandCursor)
        self.btn_expand.clicked.connect(lambda: self.tree.expandAll())
        self.btn_collapse = QPushButton("📁 收起全部")
        self.btn_collapse.setCursor(Qt.PointingHandCursor)
        self.btn_collapse.clicked.connect(lambda: self.tree.collapseAll())
        self.btn_unselect_all = QPushButton("取消全选")
        self.btn_unselect_all.setCursor(Qt.PointingHandCursor)
        self.btn_unselect_all.clicked.connect(self._unselect_all)
        self.btn_select_all = QPushButton("全选")
        self.btn_select_all.setCursor(Qt.PointingHandCursor)
        self.btn_select_all.clicked.connect(self._select_all)
        btn_layout.addWidget(self.btn_expand)
        btn_layout.addWidget(self.btn_collapse)
        btn_layout.addWidget(self.btn_unselect_all)
        btn_layout.addWidget(self.btn_select_all)
        btn_layout.addStretch()
        self.btn_ok = QPushButton("✅ 确定")
        self.btn_ok.setCursor(Qt.PointingHandCursor)
        self.btn_ok.clicked.connect(self.accept)
        self.btn_ok.setStyleSheet(
            "QPushButton { background-color: #0078d4; border: 1px solid #0078d4; }"
            "QPushButton:hover { background-color: #1a8ae8; border: 1px solid #1a8ae8; }"
        )
        btn_layout.addWidget(self.btn_ok)
        layout.addLayout(btn_layout)

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QDialog { background-color: #2b2b2b; }
            QWidget { background-color: #2b2b2b; color: #dcdcdc; font-family: "Microsoft YaHei", sans-serif; }
            QTreeWidget { background-color: #1e1e1e; color: #dcdcdc; border: 1px solid #444; border-radius: 6px; padding: 6px; font-size: 10pt; outline: none; }
            QTreeWidget::item { padding: 4px 6px; border-radius: 3px; }
            QTreeWidget::item:selected { background-color: #264f78; }
            QTreeWidget::item:hover { background-color: #2a3f5c; }
            QTreeWidget::indicator { width: 16px; height: 16px; }
            QTreeWidget::indicator:unchecked { background-color: #3c3c3c; border: 1px solid #666; border-radius: 3px; }
            QTreeWidget::indicator:checked { background-color: #0078d4; border: 1px solid #0078d4; border-radius: 3px; }
            QTreeWidget::indicator:indeterminate { background-color: #5a7a9a; border: 1px solid #5a7a9a; border-radius: 3px; }
            QPushButton { background-color: #3c3c3c; color: #e0e0e0; border: 1px solid #555; border-radius: 6px; padding: 8px 16px; font-size: 10pt; }
            QPushButton:hover { background-color: #505050; border: 1px solid #666; }
        """)

    def _load_tree(self) -> None:
        """递归扫描并加载树形结构"""
        self.tree.blockSignals(True)
        self.tree.clear()

        if not self.current_path or not os.path.isdir(self.current_path):
            root = QTreeWidgetItem(self.tree)
            root.setText(0, "⚠ 未选择文件夹")
            root.setFlags(Qt.ItemIsEnabled)
            self.tree.blockSignals(False)
            return

        root_name = os.path.basename(os.path.normpath(self.current_path))
        root = QTreeWidgetItem(self.tree)
        root.setText(0, f"📁 {root_name}")
        root.setFlags(root.flags() | Qt.ItemIsUserCheckable)
        root.setCheckState(0, Qt.Unchecked)
        root.setData(0, Qt.UserRole, "")

        self._add_subfolders(root, self.current_path)
        self.tree.expandToDepth(1)
        self.tree.blockSignals(False)
        self._update_parent_state(root)
        self._update_count()

    def _add_subfolders(self, parent_item: QTreeWidgetItem, path: str) -> None:
        """递归添加子文件夹"""
        try:
            entries = sorted(os.listdir(path))
        except (PermissionError, OSError):
            return

        entries = [e for e in entries if os.path.isdir(os.path.join(path, e))]

        for name in entries:
            full_path = os.path.join(path, name)
            child = QTreeWidgetItem(parent_item)
            child.setText(0, f"📁 {name}")
            child.setFlags(child.flags() | Qt.ItemIsUserCheckable)

            # 检查是否已屏蔽
            if name in self.blocked_folders:
                child.setCheckState(0, Qt.Checked)
            else:
                child.setCheckState(0, Qt.Unchecked)

            child.setData(0, Qt.UserRole, name)

            # 递归添加子文件夹
            self._add_subfolders(child, full_path)

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """勾选状态变化时同步子项和父项"""
        if column != 0:
            return

        self.tree.blockSignals(True)

        state = item.checkState(0)
        name = item.data(0, Qt.UserRole)

        # 同步子项
        self._sync_children(item, state)

        # 更新屏蔽列表
        self._update_blocked_from_tree()

        # 同步父项
        self._update_parent_state_recursive(item)

        self.tree.blockSignals(False)
        self._update_count()

    def _sync_children(self, item: QTreeWidgetItem, state: int) -> None:
        """同步所有子项的勾选状态"""
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, state)
            self._sync_children(child, state)

    def _update_parent_state_recursive(self, item: QTreeWidgetItem) -> None:
        """递归更新父项状态"""
        parent = item.parent()
        if not parent:
            return
        self._update_parent_state(parent)
        self._update_parent_state_recursive(parent)

    def _update_parent_state(self, parent: QTreeWidgetItem) -> None:
        """根据子项状态更新父项"""
        checked_count = 0
        partial_count = 0
        for i in range(parent.childCount()):
            state = parent.child(i).checkState(0)
            if state == Qt.Checked:
                checked_count += 1
            elif state == Qt.PartiallyChecked:
                partial_count += 1

        if checked_count == parent.childCount():
            parent.setCheckState(0, Qt.Checked)
        elif checked_count == 0 and partial_count == 0:
            parent.setCheckState(0, Qt.Unchecked)
        else:
            parent.setCheckState(0, Qt.PartiallyChecked)

    def _update_blocked_from_tree(self) -> None:
        """从树形控件状态更新屏蔽列表"""
        self.blocked_folders.clear()
        root = self.tree.topLevelItem(0)
        if root:
            self._collect_checked(root)

    def _collect_checked(self, item: QTreeWidgetItem) -> None:
        """递归收集勾选的文件夹"""
        for i in range(item.childCount()):
            child = item.child(i)
            name = child.data(0, Qt.UserRole)
            if name and child.checkState(0) == Qt.Checked:
                self.blocked_folders.add(name)
            self._collect_checked(child)

    def _update_count(self) -> None:
        """更新已屏蔽数量显示"""
        self._count_label.setText(f"已屏蔽 {len(self.blocked_folders)} 个文件夹")

    def _select_all(self) -> None:
        """全选"""
        self.tree.blockSignals(True)
        root = self.tree.topLevelItem(0)
        if root:
            root.setCheckState(0, Qt.Checked)
            self._sync_children(root, Qt.Checked)
        self._update_blocked_from_tree()
        self.tree.blockSignals(False)
        self._update_count()

    def _unselect_all(self) -> None:
        """取消全选"""
        self.tree.blockSignals(True)
        root = self.tree.topLevelItem(0)
        if root:
            root.setCheckState(0, Qt.Unchecked)
            self._sync_children(root, Qt.Unchecked)
        self._update_blocked_from_tree()
        self.tree.blockSignals(False)
        self._update_count()

    def get_blocked_folders(self) -> list:
        return list(self.blocked_folders)


# ============================================================
# 拖拽覆盖层组件
# ============================================================

class DragOverlayWidget(QWidget):
    """半透明拖拽覆盖层，带动画效果"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._visible = False
        self._icon_size = 80
        self.hide()

    def show_overlay(self):
        """显示覆盖层"""
        if self._visible:
            return
        self._visible = True
        if self.parent():
            self.setGeometry(0, 0, self.parent().width(), self.parent().height())
        self.show()
        self.raise_()
        self.update()

    def hide_overlay(self):
        """隐藏覆盖层"""
        if not self._visible:
            return
        self._visible = False
        self.hide()

    def paintEvent(self, event):
        """自定义绘制：半透明背景 + 图标 + 文字"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # 半透明背景
        painter.fillRect(self.rect(), QColor(30, 120, 220, 180))

        # 虚线边框
        pen = QPen(QColor(255, 255, 255, 200), 3, Qt.DashLine)
        painter.setPen(pen)
        margin = 20
        painter.drawRoundedRect(
            margin, margin,
            self.width() - 2 * margin,
            self.height() - 2 * margin,
            16, 16
        )

        # 中心绘制
        center_x = self.width() // 2
        center_y = self.height() // 2

        # 绘制文件夹图标（用文字代替，更流畅）
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Segoe UI Emoji", self._icon_size)
        painter.setFont(font)
        icon_rect = painter.fontMetrics().boundingRect("📁")
        painter.drawText(
            center_x - icon_rect.width() // 2,
            center_y - 40,
            icon_rect.width(),
            icon_rect.height(),
            Qt.AlignCenter,
            "📁"
        )

        # 绘制提示文字
        font.setPointSize(14)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255, 240))
        painter.drawText(
            center_x - 150,
            center_y + 60,
            300, 40,
            Qt.AlignCenter,
            "松开以生成目录结构"
        )

        painter.end()

    def resizeEvent(self, event):
        """父窗口大小改变时同步大小"""
        if self.parent():
            self.setGeometry(self.parent().rect())
        super().resizeEvent(event)


# ============================================================
# 主窗口
# ============================================================

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Folders2MD")
        self.setMinimumSize(900, 700)
        self.resize(900, 700)

        # 设置窗口图标
        self._set_window_icon()

        self.setAcceptDrops(True)

        self.current_markdown: str = ""
        self.current_source_path: str = ""
        self.current_tree_data: list = []

        self.config = load_config()
        self.blocked_folders: set = set(self.config.get("blocked_folders", []))

        # 初始化日志开关状态
        logging_enabled = self.config.get("logging_enabled", False)
        app_logger.set_enabled(logging_enabled)

        self.scan_worker: Optional[ScanWorker] = None

        self._setup_ui()
        self._apply_styles()

        # 初始化拖拽覆盖层
        self._drag_overlay = DragOverlayWidget(self.centralWidget())
        self._drag_overlay.hide()

        app_logger.log_operation(
            operation="APP_START",
            result="SUCCESS",
            details={"logging_enabled": logging_enabled, "blocked_count": len(self.blocked_folders)},
        )

    def _setup_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(10)

        # 路径显示栏
        path_layout = QHBoxLayout()
        path_label = QLabel("📁 当前路径:")
        self.path_display = QLineEdit()
        self.path_display.setReadOnly(True)
        self.path_display.setPlaceholderText("请拖入文件夹或点击选择...")
        self.btn_open = QPushButton("📂 选择文件夹")
        self.btn_open.setCursor(Qt.PointingHandCursor)
        self.btn_open.clicked.connect(self._on_open_folder)
        path_layout.addWidget(path_label)
        path_layout.addWidget(self.path_display, 1)
        path_layout.addWidget(self.btn_open)
        main_layout.addLayout(path_layout)

        # 左侧工具栏：屏蔽列表、刷新、日志
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(10)

        self.btn_block = QPushButton("🚫 屏蔽列表")
        self.btn_block.setCursor(Qt.PointingHandCursor)
        self.btn_block.clicked.connect(self._on_manage_block_list)

        self.btn_refresh = QPushButton("🔄 刷新")
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.clicked.connect(self._on_refresh)
        self.btn_refresh.setEnabled(False)

        self.btn_log_toggle = QPushButton("📝 日志: 关" if not app_logger.is_enabled() else "📝 日志: 开")
        self.btn_log_toggle.setCursor(Qt.PointingHandCursor)
        self.btn_log_toggle.clicked.connect(self._on_toggle_logging)

        toolbar_layout.addWidget(self.btn_block)
        toolbar_layout.addWidget(self.btn_refresh)
        toolbar_layout.addWidget(self.btn_log_toggle)
        toolbar_layout.addStretch()
        main_layout.addLayout(toolbar_layout)

        # 内容区域：左侧文件树 + 右侧 Markdown 预览
        content_layout = QHBoxLayout()
        content_layout.setSpacing(10)

        # 左侧文件树面板
        tree_container = QVBoxLayout()
        tree_label = QLabel("📂 文件结构（可勾选）")
        tree_label.setStyleSheet("color: #a0a0a0; font-size: 10pt; padding: 2px;")
        tree_container.addWidget(tree_label)

        self.file_tree = FileTreePanel()
        tree_container.addWidget(self.file_tree)
        content_layout.addLayout(tree_container, 1)

        # 右侧 Markdown 预览 + 操作按钮
        preview_container = QVBoxLayout()

        # 右侧顶部：标题 + 复制/保存按钮
        preview_header = QHBoxLayout()
        preview_label = QLabel("📝 Markdown 预览")
        preview_label.setStyleSheet("color: #a0a0a0; font-size: 10pt; padding: 2px;")
        preview_header.addWidget(preview_label)
        preview_header.addStretch()

        self.btn_copy = QPushButton("📋 复制")
        self.btn_copy.setCursor(Qt.PointingHandCursor)
        self.btn_copy.clicked.connect(self._on_copy)
        self.btn_copy.setStyleSheet(
            "QPushButton { background-color: #2d5a88; border: 1px solid #2d5a88; }"
            "QPushButton:hover { background-color: #3a7ab8; border: 1px solid #3a7ab8; }"
        )

        self.btn_save = QPushButton("💾 保存")
        self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.clicked.connect(self._on_save)
        self.btn_save.setStyleSheet(
            "QPushButton { background-color: #0078d4; border: 1px solid #0078d4; }"
            "QPushButton:hover { background-color: #1a8ae8; border: 1px solid #1a8ae8; }"
        )

        preview_header.addWidget(self.btn_copy)
        preview_header.addWidget(self.btn_save)
        preview_container.addLayout(preview_header)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setPlaceholderText("生成的 Markdown 目录树将显示在这里...")
        preview_container.addWidget(self.text_edit)

        # 复制/保存选项：一并复制屏蔽信息
        option_layout = QHBoxLayout()
        option_layout.addStretch()
        self.chk_copy_block_info = QCheckBox("一并复制屏蔽信息")
        self.chk_copy_block_info.setChecked(False)
        self.chk_copy_block_info.setStyleSheet("color: #a0a0a0; font-size: 9pt;")
        self.chk_copy_block_info.stateChanged.connect(self._on_copy_option_changed)
        option_layout.addWidget(self.chk_copy_block_info)
        preview_container.addLayout(option_layout)

        content_layout.addLayout(preview_container, 1)

        main_layout.addLayout(content_layout, 1)

        # 底部作者信息
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(0, 4, 0, 0)
        author_label = QLabel("作者: 加权平均数")
        author_label.setStyleSheet("color: #666; font-size: 9pt;")
        self.email_label = QLabel("📧 Findme@xiaoding.club")
        self.email_label.setStyleSheet("color: #666; font-size: 9pt; text-decoration: underline;")
        self.email_label.setCursor(Qt.PointingHandCursor)
        self.email_label.mousePressEvent = lambda e: self._copy_email()
        btn_copy_email = QPushButton("📋 复制邮箱")
        btn_copy_email.setCursor(Qt.PointingHandCursor)
        btn_copy_email.setStyleSheet("background-color: transparent; color: #666; border: none; font-size: 9pt; padding: 0;")
        btn_copy_email.clicked.connect(self._copy_email)
        footer_layout.addWidget(author_label)
        footer_layout.addSpacing(12)
        footer_layout.addWidget(self.email_label)
        footer_layout.addWidget(btn_copy_email)
        footer_layout.addStretch()
        main_layout.addLayout(footer_layout)

        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪 - 拖入文件夹或点击选择")

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QMainWindow { background-color: #2b2b2b; }
            QWidget { background-color: #2b2b2b; color: #dcdcdc; font-family: "Microsoft YaHei", "PingFang SC", sans-serif; }
            QLabel { color: #a0a0a0; font-size: 10pt; }
            QPushButton { background-color: #3c3c3c; color: #e0e0e0; border: 1px solid #555; border-radius: 6px; padding: 6px 14px; font-size: 10pt; }
            QPushButton:hover { background-color: #505050; border: 1px solid #666; }
            QPushButton:pressed { background-color: #404040; }
            QPushButton:disabled { background-color: #2a2a2a; color: #666; border: 1px solid #444; }
            QLineEdit { background-color: #1e1e1e; color: #dcdcdc; border: 1px solid #444; border-radius: 6px; padding: 6px 10px; font-size: 10pt; }
            QTextEdit { background-color: #1e1e1e; color: #dcdcdc; border: 1px solid #444; border-radius: 6px; padding: 10px; font-family: "Consolas", "Cascadia Code", "Courier New", monospace; font-size: 10pt; selection-background-color: #264f78; }
            QStatusBar { color: #a0a0a0; font-size: 9pt; background-color: #2b2b2b; }
        """)

    # ============================================================
    # 拖拽事件
    # ============================================================

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            if hasattr(self, '_hide_timer'):
                self._hide_timer.stop()
            self._drag_overlay.show_overlay()
            self.status_bar.showMessage("松开鼠标以生成目录")
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:
        # 延迟隐藏，避免拖动过程中频繁触发
        if not hasattr(self, '_hide_timer'):
            self._hide_timer = QTimer(self)
            self._hide_timer.setSingleShot(True)
            self._hide_timer.timeout.connect(self._drag_overlay.hide_overlay)
        self._hide_timer.start(100)
        self.status_bar.showMessage("就绪")

    def dropEvent(self, event: QDropEvent) -> None:
        if hasattr(self, '_hide_timer'):
            self._hide_timer.stop()
        self._drag_overlay.hide_overlay()
        urls = event.mimeData().urls()
        if not urls:
            return
        path = urls[0].toLocalFile()
        if not path or not os.path.isdir(path):
            self.status_bar.showMessage("错误：拖入的不是有效文件夹")
            QMessageBox.warning(self, "提示", "请拖入有效的文件夹。")
            app_logger.log_operation(
                operation="DROP_INVALID",
                target_path=path or "",
                result="FAILED",
                error="拖入的不是有效文件夹",
            )
            return
        self._process(path)

    # ============================================================
    # 按钮事件
    # ============================================================

    def _on_open_folder(self) -> None:
        start_time = time.time()
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        duration = (time.time() - start_time) * 1000
        if folder:
            app_logger.log_operation(
                operation="FOLDER_SELECT",
                target_path=folder,
                result="SUCCESS",
                duration_ms=duration,
            )
            self._process(folder)
        else:
            app_logger.log_operation(
                operation="FOLDER_SELECT",
                result="CANCELLED",
                duration_ms=duration,
            )

    def _on_copy(self) -> None:
        if not self.current_markdown:
            self.status_bar.showMessage("没有可复制的内容")
            QMessageBox.information(self, "提示", "请先生成目录树。")
            return
        # 根据勾选状态决定是否包含屏蔽信息
        if self.chk_copy_block_info.isChecked() and self.blocked_folders:
            block_note = self.scan_worker._build_block_note(
                self.current_source_path, self.blocked_folders
            ) if self.scan_worker else ""
            content = self.current_markdown + block_note
        else:
            content = self.current_markdown
        clipboard = QApplication.clipboard()
        clipboard.setText(content)
        self.status_bar.showMessage("已复制到剪贴板")
        app_logger.log_operation(
            operation="COPY_CLIPBOARD",
            result="SUCCESS",
            details={
                "content_length": len(content),
                "with_block_info": self.chk_copy_block_info.isChecked(),
            },
        )

    def _on_save(self) -> None:
        if not self.current_markdown:
            self.status_bar.showMessage("没有可保存的内容")
            QMessageBox.information(self, "提示", "请先生成目录树。")
            return

        default_name = "directory_tree.md"
        if self.current_source_path:
            folder_name = os.path.basename(os.path.normpath(self.current_source_path))
            safe_name = sanitize_filename(folder_name)
            default_name = f"{safe_name}-tree.md"

        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存文件", default_name,
            "Markdown 文件 (*.md);;文本文件 (*.txt);;所有文件 (*.*)",
        )
        if not file_path:
            app_logger.log_operation(operation="SAVE_FILE", result="CANCELLED")
            return

        start_time = time.time()
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(self.current_markdown)
            duration = (time.time() - start_time) * 1000
            self.status_bar.showMessage(f"已保存: {file_path}")
            app_logger.log_operation(
                operation="SAVE_FILE",
                target_path=file_path,
                result="SUCCESS",
                duration_ms=duration,
                details={"file_size": len(self.current_markdown)},
            )
            folder = os.path.dirname(file_path)
            if open_folder_in_explorer(folder):
                self.status_bar.showMessage(f"已保存并打开文件夹")
        except OSError as e:
            self.status_bar.showMessage("保存失败")
            app_logger.log_operation(
                operation="SAVE_FILE",
                target_path=file_path,
                result="FAILED",
                error=str(e),
            )
            QMessageBox.critical(self, "错误", f"无法保存文件:\n{e}")

    def _on_manage_block_list(self) -> None:
        dialog = BlockListDialog(self.current_source_path, list(self.blocked_folders), self)
        if dialog.exec_() == QDialog.Accepted:
            old_blocked = self.blocked_folders.copy()
            self.blocked_folders = set(dialog.get_blocked_folders())
            self.config["blocked_folders"] = list(self.blocked_folders)
            save_config(self.config)
            self.status_bar.showMessage(f"屏蔽列表已更新，当前共 {len(self.blocked_folders)} 项")
            app_logger.log_operation(
                operation="BLOCK_LIST_UPDATE",
                result="SUCCESS",
                details={
                    "old_count": len(old_blocked),
                    "new_count": len(self.blocked_folders),
                    "blocked_folders": list(self.blocked_folders),
                },
            )
            if self.current_source_path:
                self._process(self.current_source_path)

    def _on_refresh(self) -> None:
        if self.current_source_path:
            app_logger.log_operation(
                operation="REFRESH",
                target_path=self.current_source_path,
            )
            self._process(self.current_source_path)

    def _set_window_icon(self) -> None:
        """设置窗口图标，支持开发环境和PyInstaller打包环境"""
        icon_path = self._get_resource_path("images", "logo", "logo.png")
        if icon_path and os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

    def _get_resource_path(self, *relative_paths: str) -> str:
        """
        获取资源文件的绝对路径
        支持开发环境和PyInstaller打包后的环境
        """
        if getattr(sys, "frozen", False):
            # PyInstaller打包后的环境：资源在_MEIPASS临时目录
            base_path = sys._MEIPASS
        else:
            # 开发环境：资源在脚本所在目录
            base_path = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_path, *relative_paths)

    def _on_copy_option_changed(self, state: int) -> None:
        """复制选项变化时更新预览"""
        if not self.current_markdown:
            return
        # 更新预览显示
        if self.chk_copy_block_info.isChecked() and self.blocked_folders:
            block_note = self.scan_worker._build_block_note(
                self.current_source_path, self.blocked_folders
            ) if self.scan_worker else ""
            preview = self.current_markdown + block_note
        else:
            preview = self.current_markdown
        self.text_edit.setPlainText(preview)

    def _copy_email(self) -> None:
        """复制邮箱到剪贴板"""
        clipboard = QApplication.clipboard()
        clipboard.setText("Findme@xiaoding.club")
        self.status_bar.showMessage("邮箱已复制到剪贴板")

    def _on_toggle_logging(self) -> None:
        """切换日志开关"""
        new_state = not app_logger.is_enabled()
        app_logger.set_enabled(new_state)
        self.config["logging_enabled"] = new_state
        save_config(self.config)

        self.btn_log_toggle.setText("📝 日志: 开" if new_state else "📝 日志: 关")
        status = "已启用" if new_state else "已禁用"
        self.status_bar.showMessage(f"日志记录{status}")

        # 记录开关操作本身
        if new_state:
            app_logger.log_operation(
                operation="LOGGING_ENABLED",
                result="SUCCESS",
                details={"logs_dir": app_logger._get_logs_dir()},
            )

    def closeEvent(self, event) -> None:
        """窗口关闭时记录日志"""
        app_logger.log_operation(
            operation="APP_EXIT",
            result="SUCCESS",
            details={"source_path": self.current_source_path or ""},
        )
        event.accept()

    # ============================================================
    # 窗口事件
    # ============================================================

    def resizeEvent(self, event):
        """窗口大小变化时同步覆盖层大小"""
        super().resizeEvent(event)
        if hasattr(self, '_drag_overlay') and self._drag_overlay._visible:
            self._drag_overlay.setGeometry(0, 0, self.width(), self.height())

    # ============================================================
    # 核心处理逻辑（使用后台线程）
    # ============================================================

    def _process(self, path: str) -> None:
        """处理指定路径：启动后台线程扫描"""
        self.current_source_path = path
        self.path_display.setText(path)
        self.btn_refresh.setEnabled(True)
        self.status_bar.showMessage("正在扫描...")

        # 安全停止之前的扫描线程
        if self.scan_worker and self.scan_worker.isRunning():
            app_logger.log_operation(
                operation="SCAN_INTERRUPT",
                target_path=self.scan_worker.root_path,
            )
            # 断开旧信号连接，避免旧线程回调干扰
            try:
                self.scan_worker.finished_signal.disconnect(self._on_scan_finished)
                self.scan_worker.error_signal.disconnect(self._on_scan_error)
            except Exception:
                pass
            self.scan_worker.cancel()
            self.scan_worker.wait(2000)

        # 启动新的后台扫描线程
        self.scan_worker = ScanWorker(path, self.blocked_folders)
        self.scan_worker.finished_signal.connect(self._on_scan_finished)
        self.scan_worker.error_signal.connect(self._on_scan_error)
        self.scan_worker.start()

    def _on_scan_finished(self, markdown: str, tree_data: list) -> None:
        """扫描完成回调"""
        self.current_markdown = markdown
        self.current_tree_data = tree_data
        self.text_edit.setPlainText(markdown)

        # 加载文件树面板
        if self.current_source_path:
            self.file_tree.load_directory(self.current_source_path, self.blocked_folders)

        folder_name = os.path.basename(os.path.normpath(self.current_source_path))
        blocked_info = f" (已屏蔽 {len(self.blocked_folders)} 项)" if self.blocked_folders else ""
        self.status_bar.showMessage(f"已生成: {folder_name}{blocked_info}")

    def _on_scan_error(self, error_msg: str) -> None:
        """扫描错误回调"""
        self.status_bar.showMessage("生成失败")
        QMessageBox.critical(self, "错误", f"生成目录树时出错:\n{error_msg}")


# ============================================================
# 程序入口
# ============================================================

def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
