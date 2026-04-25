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

### 前置条件

已安装 PyInstaller：

```bash
pip install pyinstaller
```

### 打包命令

在项目根目录下执行：

```bash
pyinstaller --onefile --windowed --name Folders2MD --clean folders2md.py
```

### 参数说明

| 参数 | 作用 |
|------|------|
| `--onefile` | 打包成单个 exe 文件 |
| `--windowed` | 无控制台窗口（纯 GUI） |
| `--name Folders2MD` | 输出文件名 |
| `--clean` | 清理旧的 build/dist 缓存 |

### 输出位置

```
dist/Folders2MD.exe    # 约 35MB，双击即可运行，无需 Python 环境
```

### 清理打包临时文件

打包完成后可删除以下目录/文件（不影响 exe 运行）：

```
build/          # 构建缓存
Folders2MD.spec # PyInstaller 配置文件
```

## 使用说明

### 基本操作

1. **拖入**：从资源管理器将文件夹直接拖入程序窗口
2. **按钮**：点击「📂 选择文件夹」打开对话框
3. **复制**：点击「📋 复制」将 Markdown 内容复制到剪贴板
4. **保存**：点击「💾 保存」，自动命名为 `文件夹名-tree.md`
5. **屏蔽**：点击「🚫 屏蔽列表」添加不需要扫描的目录名
6. **日志**：点击「📝 日志: 关」切换日志开关

### 屏蔽大目录避免卡死

如果扫描包含大量文件的目录（如 `node_modules`、Python 的 `Lib` 目录等），建议先将其加入屏蔽列表：

1. 点击「🚫 屏蔽列表」
2. 输入要屏蔽的文件夹名称，如：
   - `node_modules`
   - `__pycache__`
   - `.git`
   - `venv`
   - `.env`
3. 点击「✅ 确定」

### 日志诊断卡死

当程序出现卡死时：

1. 启动前点击「📝 日志: 开」启用日志
2. 执行导致卡死的操作
3. 查看 `logs/YYYY-MM-DD.log` 文件
4. 用以下命令定位卡死位置：

```bash
# 查看最后几条日志（卡死前的最后记录）
tail -n 20 logs/2026-04-26.log

# 筛选扫描进度（找到深度最大的目录）
grep "SCAN_PROGRESS" logs/2026-04-26.log
```

## 项目结构

```
├── folders2md.py          # 主程序源码
├── docx/
│   └── 设计文档.md         # 详细设计文档
├── .gitignore             # Git 忽略规则
└── README.md              # 本文件
```

## 技术栈

- **GUI**: PyQt5 (QTreeWidget, QTextEdit, QThread)
- **算法**: 递归目录遍历 + 循环链接检测
- **日志**: logging + RotatingFileHandler + JSON 格式化
- **打包**: PyInstaller (--onefile)
