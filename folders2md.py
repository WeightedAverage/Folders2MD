#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Folders2MD - 文件夹结构转 Markdown 工具
基于 PyQt5 实现，支持拖拽，深色主题
"""

import os
import sys
import warnings
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QDragEnterEvent, QDropEvent
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# 忽略 PyQt5 的弃用警告，保持输出整洁
warnings.filterwarnings("ignore", category=DeprecationWarning)


# ============================================================
# 核心算法：树形结构生成
# ============================================================

def generate_tree_lines(root_path: str, prefix: str = "") -> list[str]:
    """
    递归生成目录树的每一行文本

    参数:
        root_path: 当前文件夹路径
        prefix: 缩进前缀，用于控制层级显示

    返回:
        字符串列表，每一行是一个节点
    """
    lines: list[str] = []

    try:
        entries = sorted(os.listdir(root_path))
    except PermissionError:
        # 无权限访问时，返回提示节点，避免程序崩溃
        lines.append(prefix + "<无法访问>")
        return lines
    except OSError:
        lines.append(prefix + "<无法读取>")
        return lines

    # 过滤隐藏文件（以 . 开头），如需保留可注释此行
    entries = [e for e in entries if not e.startswith(".")]

    for index, entry in enumerate(entries):
        path = os.path.join(root_path, entry)
        is_last = index == len(entries) - 1

        # 根据是否为最后一个条目选择符号
        connector = "└── " if is_last else "├── "
        lines.append(prefix + connector + entry)

        # 如果是文件夹，递归处理
        if os.path.isdir(path):
            # 新的前缀：根据当前是否为最后一个条目决定使用空格或竖线
            extension = "    " if is_last else "│   "
            lines.extend(generate_tree_lines(path, prefix + extension))

    return lines


# ============================================================
# Markdown 格式化器
# ============================================================

def format_markdown(root_path: str) -> str:
    """
    将文件夹结构格式化为 Markdown 字符串

    参数:
        root_path: 根文件夹路径

    返回:
        完整 Markdown 字符串
    """
    root_name = os.path.basename(os.path.normpath(root_path))
    tree_lines = generate_tree_lines(root_path)

    # 构建 Markdown 内容
    md_lines: list[str] = []
    md_lines.append(f"# 📁 {root_name}")
    md_lines.append("")
    md_lines.append("```")
    md_lines.append(root_name)
    md_lines.extend(tree_lines)
    md_lines.append("```")
    md_lines.append("")

    return "\n".join(md_lines)


# ============================================================
# 主窗口
# ============================================================

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Folders2MD")
        self.setMinimumSize(700, 600)
        self.resize(700, 600)

        # 启用拖拽
        self.setAcceptDrops(True)

        # 当前生成的 Markdown 内容
        self.current_markdown: str = ""

        self._setup_ui()
        self._apply_styles()

    def _setup_ui(self) -> None:
        """初始化界面组件"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(12)

        # 提示标签
        self.hint_label = QLabel("将文件夹拖入此窗口，或点击按钮选择文件夹")
        self.hint_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.hint_label)

        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        self.btn_open = QPushButton("📂 选择文件夹")
        self.btn_open.setCursor(Qt.PointingHandCursor)
        self.btn_open.clicked.connect(self._on_open_folder)

        self.btn_copy = QPushButton("📋 复制")
        self.btn_copy.setCursor(Qt.PointingHandCursor)
        self.btn_copy.clicked.connect(self._on_copy)

        self.btn_save = QPushButton("💾 保存")
        self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.clicked.connect(self._on_save)

        button_layout.addWidget(self.btn_open)
        button_layout.addWidget(self.btn_copy)
        button_layout.addWidget(self.btn_save)
        main_layout.addLayout(button_layout)

        # 结果显示区（只读文本框）
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setPlaceholderText("生成的 Markdown 目录树将显示在这里...")
        main_layout.addWidget(self.text_edit)

        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")

    def _apply_styles(self) -> None:
        """应用深色主题 QSS 样式"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2b2b2b;
            }
            QWidget {
                background-color: #2b2b2b;
                color: #dcdcdc;
                font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
            }
            QLabel {
                color: #a0a0a0;
                font-size: 11pt;
                padding: 8px;
            }
            QPushButton {
                background-color: #3c3c3c;
                color: #e0e0e0;
                border: 1px solid #555;
                border-radius: 6px;
                padding: 6px 18px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #505050;
                border: 1px solid #666;
            }
            QPushButton:pressed {
                background-color: #404040;
            }
            QTextEdit {
                background-color: #1e1e1e;
                color: #dcdcdc;
                border: 1px solid #444;
                border-radius: 6px;
                padding: 10px;
                font-family: "Consolas", "Cascadia Code", "Courier New", monospace;
                font-size: 10pt;
                selection-background-color: #264f78;
            }
            QStatusBar {
                color: #a0a0a0;
                font-size: 9pt;
                background-color: #2b2b2b;
            }
        """)

    # ============================================================
    # 事件处理：拖拽
    # ============================================================

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """拖拽进入窗口时触发"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.status_bar.showMessage("松开鼠标以生成目录")
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:
        """拖拽离开窗口时触发"""
        self.status_bar.showMessage("就绪")

    def dropEvent(self, event: QDropEvent) -> None:
        """松开鼠标释放拖拽时触发"""
        urls = event.mimeData().urls()
        if not urls:
            return

        # 提取第一个 URL 的本地路径
        path = urls[0].toLocalFile()
        if not path:
            self.status_bar.showMessage("无法识别的路径")
            return

        if not os.path.isdir(path):
            self.status_bar.showMessage("错误：拖入的不是文件夹")
            QMessageBox.warning(self, "提示", "请拖入文件夹，而非文件。")
            return

        self._process(path)

    # ============================================================
    # 按钮事件
    # ============================================================

    def _on_open_folder(self) -> None:
        """点击选择文件夹按钮"""
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            self._process(folder)

    def _on_copy(self) -> None:
        """点击复制按钮"""
        if not self.current_markdown:
            self.status_bar.showMessage("没有可复制的內容")
            QMessageBox.information(self, "提示", "请先生成目录树。")
            return

        clipboard = QApplication.clipboard()
        clipboard.setText(self.current_markdown)
        self.status_bar.showMessage("已复制到剪贴板")

    def _on_save(self) -> None:
        """点击保存按钮"""
        if not self.current_markdown:
            self.status_bar.showMessage("没有可保存的内容")
            QMessageBox.information(self, "提示", "请先生成目录树。")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存文件",
            "directory_tree.md",
            "Markdown 文件 (*.md);;文本文件 (*.txt);;所有文件 (*.*)"
        )
        if not file_path:
            return

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(self.current_markdown)
            self.status_bar.showMessage(f"已保存: {file_path}")
        except OSError as e:
            self.status_bar.showMessage("保存失败")
            QMessageBox.critical(self, "错误", f"无法保存文件:\n{e}")

    # ============================================================
    # 核心处理逻辑
    # ============================================================

    def _process(self, path: str) -> None:
        """
        处理指定路径：生成 Markdown 并更新界面

        参数:
            path: 文件夹路径
        """
        try:
            self.current_markdown = format_markdown(path)
        except Exception as e:
            self.status_bar.showMessage("生成失败")
            QMessageBox.critical(self, "错误", f"生成目录树时出错:\n{e}")
            return

        self.text_edit.setPlainText(self.current_markdown)
        self.status_bar.showMessage(f"已生成: {path}")


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
