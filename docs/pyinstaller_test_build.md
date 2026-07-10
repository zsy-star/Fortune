# PyInstaller 发布包说明

本文档说明如何在 Windows 打包机上准备并构建 Fortune 发布包。目标是产出可交付使用的 `dist/Fortune/` 目录。

## 打包前准备

1. 使用独立打包机或 clean venv，**不要**在含真实业务数据的开发目录直接发包。
2. 确认当前分支与提交已通过 CI / 本地测试（411+ pytest）。
3. 阅读 [打包前自检清单](pre_packaging_checklist.md) 与 [发布目录结构](test_release_structure.md)。
4. 确认 `data/fortune.db`、`data/backups/`、`exports/`、`.xlsx`、`.pytest_tmp_cursor*` 不会进入 spec 的 `datas`。
5. 不建议直接使用 Anaconda 环境打包；Anaconda 往往会收集 IPython、jedi、sphinx、black、MKL 等无关依赖，显著增大发布包。

## 推荐 Python 版本

- Python **3.10+**（与开发环境一致，当前测试环境 3.13 亦可）
- 64 位 Windows

## 推荐 clean venv 流程

在项目根目录执行：

```powershell
python -m venv .venv_release
.venv_release\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

`requirements.txt` 只保留运行依赖；`requirements-dev.txt` 额外包含测试和打包依赖，如 pytest、pyinstaller、requests。

## 打包前测试

```powershell
python -m pytest -q
```

## 打包前只读自检

```powershell
python scripts/pre_release_check.py --project-root .
```

- **失败项 > 0**：不得继续 build
- **警告项**：如 `.pytest_tmp_cursor*`、遗留 xlsx，确认不会被打进包内后可继续

## Dry-run（不实际打包）

```powershell
python scripts/build_test_release.py --project-root . --dry-run
```

输出将执行的步骤、spec 路径、预期 dist 目录；不调用 PyInstaller。

## 正式 build

```powershell
python scripts/build_test_release.py --project-root . --build
```

流程：

1. 自动运行 `pre_release_check`
2. 检查 `packaging/fortune_test.spec`
3. 调用 PyInstaller（若未安装会友好提示并退出）
4. 输出到 `dist/Fortune/`

也可手动调用：

```powershell
pyinstaller --noconfirm --distpath dist --workpath build/fortune_test packaging/fortune_test.spec
```

## 打包产物位置

```text
dist/Fortune/
  Fortune.exe
  docs/              # build 后同步自 _internal/docs/
  _internal/         # PyInstaller 依赖（onedir 模式）
```

首次运行 exe 时，会在 **exe 同级目录** 自动创建：

```text
data/
data/backups/
exports/
```

## 打包后自检

```powershell
python scripts/check_test_release.py --release-dir dist/Fortune
```

检查 exe、docs 是否存在，以及是否误带 `fortune.db`、backups、xlsx、pytest 临时目录。

## 不要打包哪些文件

| 路径 | 原因 |
|------|------|
| `.venv_release/` | 本机打包环境 |
| `build/` | PyInstaller 构建缓存 |
| `dist/` | 发布产物，不进入源码提交 |
| `data/fortune.db` | 真实业务库 |
| `data/backups/*.db` | 私人备份 |
| `exports/*.xlsx` | 测试导出 |
| 根目录 `*.xlsx` | 测试导出 |
| 根目录 `*.db` | 测试或业务数据库 |
| `.pytest_tmp*` | 测试临时目录 |

## 如何处理 data/fortune.db

- **开发机**：保留本地库，不要加入 spec
- **发布包**：首次运行由 SQLite + `init_db()` 在 `data/fortune.db` 创建空表结构
- **切勿**把开发环境的 `fortune.db` 复制进 dist 再 zip

## 如何处理 data/backups/

- 打包时不包含任何 `.db` 备份
- 首次备份时程序写入 exe 同级的 `data/backups/`

## 如何处理 exports/

- 打包时不包含测试 xlsx
- 首次导出时创建 `exports/` 或由用户选择其他目录

## 如何交付发布包

1. 对整个 `dist/Fortune/` 文件夹打 zip（不要只发 exe）
2. 附带 [人工验收脚本](manual_test_script.md) 链接或打印版
3. 说明：发布包名称 `Fortune`，解压即用
4. 提醒使用**空目录或测试机**，不要用生产账套直接试

## 首次运行步骤

1. 解压到本地路径（路径尽量无中文空格问题）
2. 双击 `Fortune.exe`
3. 确认同级出现 `data/`、`exports/`（及首次备份后的 `data/backups/`）
4. 按 [商用测试前验收清单](commercial_acceptance_checklist.md) 逐项验收

## 常见失败原因

| 现象 | 处理 |
|------|------|
| `pre_release_check` 失败 | 补全文档或依赖，见失败项列表 |
| PyInstaller 未安装 | `pip install pyinstaller` |
| build 后缺 DLL | 在干净 Windows 虚拟机试跑；检查 PySide6 是否完整打包 |
| exe 启动后找不到 data | 确认从 `Fortune.exe` 所在目录运行；查看 `scripts/runtime_init.py` |
| 中文乱码 | Windows 字体正常即可；matplotlib 配置在启动时加载 |
| dist 中含 fortune.db | 检查 spec datas，重新 build，运行 `check_test_release.py` |

## 相关文档

- [发布目录结构](test_release_structure.md)
- [打包前自检清单](pre_packaging_checklist.md)
- [小范围商用验收清单](commercial_acceptance_checklist.md)
