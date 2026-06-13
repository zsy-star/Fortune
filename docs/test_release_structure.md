# 测试版发布目录结构

Fortune 测试版采用 PyInstaller **onedir** 模式，发布物为文件夹 `Fortune-Test/`，不是单一安装程序。

## 标准结构

```text
Fortune-Test/
  Fortune-Test.exe          # 主程序入口
  docs/                     # 打包内置说明（*.md）
  _internal/                # PyInstaller 运行时依赖（自动生成）
  data/                     # 首次运行自动创建
  data/backups/             # 首次运行自动创建
  exports/                  # 首次运行自动创建
```

## 首次运行后

程序在 **exe 同级** 创建运行时目录，不会写入假订单或假开奖数据：

- `data/` — SQLite 数据库 `fortune.db` 在首次 `init_db()` 时创建表结构
- `data/backups/` — 用户点击「立即备份」后写入 `.db` 文件
- `exports/` — 用户导出 Excel 时使用（也可另选目录）

## 必须随包提供

- 整个 `Fortune-Test/` 文件夹（含 `_internal/`）
- 不要只复制 `Fortune-Test.exe`

## 禁止出现在发布包中

| 内容 | 说明 |
|------|------|
| 真实 `data/fortune.db` | 开发/生产业务数据 |
| `data/backups/*.db` | 私人备份 |
| `exports/*.xlsx` | 测试导出 |
| 根目录或任意层级的测试 `.xlsx` | 对账测试文件 |
| `.pytest_tmp*` / `.pytest_tmp_cursor*` | pytest 临时目录 |
| `启动Fortune.bat` | 开发用脚本，非测试版必需 |

## 打包前 vs 打包后检查

| 阶段 | 命令 |
|------|------|
| 打包前 | `python scripts/pre_release_check.py --project-root .` |
| 打包后 | `python scripts/check_test_release.py --release-dir dist/Fortune-Test` |

两个脚本均为**只读**，不删除任何文件。

## 与源码目录的区别

源码开发时使用 `python main.py`，数据默认在项目根 `data/fortune.db`。

测试版 exe 运行时，数据在 **exe 所在目录** 的 `data/fortune.db`（通过 `scripts/runtime_init.py` 处理 frozen 路径）。

## 给测试人员的说明要点

1. 解压到新文件夹，不要用含真实账套的 old 目录覆盖
2. 每日备份 `data/backups/`
3. 整个文件夹可 zip 迁移，迁移的是测试数据而非安装注册信息

## 相关文档

- [PyInstaller 测试版打包说明](pyinstaller_test_build.md)
- [人工验收脚本](manual_test_script.md)
