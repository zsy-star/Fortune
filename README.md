# Fortune

Fortune 是一个本地桌面版六合彩记账本 / 订单账本 / 结算账本。当前目标是小范围商用测试，重点是数据准确、账目可追溯、防误操作、备份恢复安全、可导出对账。

## 技术栈

- Python
- PySide6 / Qt Widgets
- SQLite
- SQLAlchemy 2.0
- Alembic
- matplotlib
- openpyxl
- pytest

## 启动

```bash
python main.py
```

默认数据库位置：

```text
data/fortune.db
```

测试使用临时 SQLite 数据库，不应直接写入 `data/fortune.db`。

## 当前测试版已完成

- 录单弹窗解析、预览、保存订单
- 订单查询、订单详情、订单作废
- 开奖记录查询与开奖记录采集
- 结算预览、正式确认结算
- 结算历史 / 账目流水只读查询
- 操作日志查询
- 数据总览、订单分析真实数据库统计
- 数据库备份 / 恢复后端与 UI
- 订单、结算流水、操作日志 Excel 导出
- 号码大全静态参考表
- 计算器工具

## 当前测试版暂未开放

- 连码调单、连肖调单持久化；页面保留入口，但按钮禁用，不参与正式记账、结算、导出
- 拆单助手；窗口保留入口，但拆分、样式调整、保存文件均禁用并显示测试版提示
- 订单导入、批量删除、清空订单；后续需要权限、审计和数据恢复策略支持
- 清空操作日志；当前操作日志用于审计追溯，不提供清空入口
- 正式兑奖、赔率、赔付金额、盈亏金额、客户余额；当前只做命中判定和结算记录
- 手工新增/修正开奖记录；后续需要权限、校验和操作日志策略支持
- 权限系统、云同步、在线账号
- PyInstaller 安装包

## 验收与打包

- [商用测试前验收清单](docs/commercial_acceptance_checklist.md)
- [打包前自检清单](docs/pre_packaging_checklist.md)
- [人工验收脚本](docs/manual_test_script.md)
- [PyInstaller 打包测试版说明](docs/pyinstaller_test_build.md)
- [测试版发布目录结构说明](docs/test_release_structure.md)
- 打包前只读自检：`python scripts/pre_release_check.py --project-root .`
- 测试版构建 dry-run：`python scripts/build_test_release.py --project-root . --dry-run`
- 测试版发布目录检查：`python scripts/check_test_release.py --release-dir dist/Fortune-Test`

## 后续规划

- 首次 PyInstaller 本机打包试运行
- 按实际业务优先级补充赔率 / 盈亏、导入、调单等能力

## 迁移与测试

创建迁移：

```bash
alembic revision --autogenerate -m "message"
```

执行迁移：

```bash
alembic upgrade head
```

运行测试：

```bash
python -m pytest
```
