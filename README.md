# Folders2MD

文件夹结构转 Markdown 工具 —— 拖入即出图，复制就走。

## 功能

- 拖拽 / 按钮选择文件夹
- 左侧文件树面板（带勾选框，父子联动）
- 右侧 Markdown 实时预览
- 自动命名保存（`文件夹名-tree.md`）
- 保存后自动打开所在文件夹
- 可配置文件夹屏蔽列表（如 `node_modules`、`__pycache__`）
- 日志记录功能（JSON 格式，可一键开关，用于诊断卡死）
- 循环符号链接检测
- 安全线程取消机制
- 深色主题界面

## 截图

<!-- TODO: 添加截图 -->

## 环境要求

- Python 3.8+
- PyQt5

## 安装依赖

```bash
pip install PyQt5 pyinstaller
```

## 运行

```bash
python folders2md.py
```

## 打包为 EXE

```bash
pyinstaller --onefile --windowed --name Folders2MD --clean folders2md.py
```

输出位置：`dist/Folders2MD.exe`（约 35MB，双击即可运行，无需 Python 环境）

## 使用说明

| 操作 | 说明 |
|------|------|
| 拖入 | 从资源管理器将文件夹直接拖入程序窗口 |
| 选择 | 点击「📂 选择文件夹」打开对话框 |
| 复制 | 点击「📋 复制」将 Markdown 内容复制到剪贴板 |
| 保存 | 点击「💾 保存」，自动命名为 `文件夹名-tree.md` |
| 屏蔽 | 点击「🚫 屏蔽列表」添加不需要扫描的目录名 |
| 日志 | 点击「📝 日志: 关」切换日志开关 |

### 屏蔽大目录避免卡死

如果扫描包含大量文件的目录（如 `node_modules`、Python 的 `Lib` 目录等），建议先将其加入屏蔽列表：

1. 点击「🚫 屏蔽列表」
2. 勾选要屏蔽的文件夹，如 `node_modules`、`__pycache__`、`.git`、`venv`
3. 点击「✅ 确定」

### 日志诊断卡死

当程序出现卡死时：

1. 启动前点击「📝 日志: 开」启用日志
2. 执行导致卡死的操作
3. 查看 `logs/YYYY-MM-DD.log` 文件

```bash
# 查看最后几条日志
tail -n 20 logs/2026-04-30.log

# 筛选扫描进度
grep "SCAN_PROGRESS" logs/2026-04-30.log
```

## 项目结构

```
├── folders2md.py          # 主程序源码
├── images/logo/           # 应用图标
├── docx/设计文档.md       # 详细设计文档
├── test_*.py              # 测试脚本
├── Folders2MD.spec        # PyInstaller 配置
├── .gitignore
└── README.md
```

## 技术栈

- **GUI**: PyQt5（QTreeWidget, QTextEdit, QThread）
- **算法**: 递归目录遍历 + 循环链接检测
- **日志**: logging + RotatingFileHandler + JSON 格式化
- **打包**: PyInstaller（--onefile）
