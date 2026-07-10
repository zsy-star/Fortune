# Fortune V1.0 小范围单机试用说明

Fortune 是本地单机记账和统计工具，用来录入订单、核对开奖、查看结算快照、导出对账表和保留操作记录。

它不做客户余额，不做真实付款，不做真实兑奖入账，也不做云同步。中奖金额、返水金额和统计结算金额只用于记账统计和对账参考，不代表已经付款、收款或入账。

## 第一版主要功能

- 录单。
- 订单查询。
- 开奖管理。
- 结算预览 / 正式结算。
- 结算历史。
- 调单记录。
- 备份恢复。
- Excel 导出。
- 操作日志。

## 每日使用建议

1. 每天开始前先备份数据库。
2. 每批订单录入后，先在订单详情中核对订单号、地区、玩法、号码和金额。
3. 开奖修正必须填写原因，避免事后无法追溯。
4. 正式结算前先看结算预览，确认期号、地区和结果。
5. 每天结束后导出操作日志和需要的对账表，再备份数据库。

## 出问题时请保留这些信息

- 订单号。
- 期号。
- 地区。
- 问题截图。
- 操作日志导出文件。
- 对应时间点的备份文件。

## 使用边界

- 第一版不保证支持所有玩法正式结算。
- 暂不支持正式结算的玩法可以用于记账或人工核对，但正式结算会阻断或提示。
- 高风险维护入口必须谨慎使用，包括清空订单、批量删除订单、清空日志和重置开奖记录。
- 高风险维护入口第一阶段可以受保护执行，但必须经过自动备份、二次确认、原因填写、确认短语和操作日志。
- 小范围试用时，如确需使用高风险维护入口，请先手工确认备份，再按界面提示操作。
- 当前不是完整权限系统，仍依赖本机管理和操作规范。

## 试用包构建口径

V1.0 小范围试用包推荐使用 clean venv 构建，不建议直接使用 Anaconda 等包含大量开发依赖的环境。构建负责人应使用：

```powershell
python -m venv .venv_release
.venv_release\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
python -m pytest -q
python scripts/pre_release_check.py --project-root .
python scripts/build_test_release.py --project-root . --dry-run
python scripts/build_test_release.py --project-root . --build
python scripts/check_test_release.py --release-dir dist\Fortune
```

发布前必须确认 `dist\Fortune` 中没有真实 `fortune.db`、备份库、测试导出表、Git 目录或测试缓存。`.venv_release/`、`build/`、`dist/`、`data/fortune.db`、`data/backups/`、`exports/`、`*.xlsx`、`*.db` 都不得提交。

V1.0 试用版 release 环境应使用 `requirements.txt` / `requirements-dev.txt` 中锁定版本构建，不建议临时升级 PySide6 等核心 GUI 依赖；如需升级，必须重新跑全量 pytest 和发布包启动验证。
