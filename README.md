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

- 连码调单、连肖调单持久化
- 拆单助手
- 订单导入、批量删除、清空订单
- 清空操作日志
- 正式兑奖、赔率、赔付金额、盈亏金额
- 权限系统、云同步、在线账号
- PyInstaller 安装包

## 验收与打包

- [商用测试前验收清单](docs/commercial_acceptance_checklist.md)
- [打包前自检清单](docs/pre_packaging_checklist.md)
- [人工验收脚本](docs/manual_test_script.md)
- 只读自检：`python scripts/pre_release_check.py --project-root .`

## 后续规划

- PyInstaller 打包测试版准备
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
