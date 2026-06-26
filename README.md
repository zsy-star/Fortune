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
- 录单窗口申报人选择、申报人绑定配置方案展示
- 录单高级选项第一阶段：识别地区、智能纠错
- 订单查询、订单详情、订单作废、订单详情查看
- 订单详情页业务后台化布局、申报人筛选、投注类型筛选、中奖情况筛选
- 订单详情页过滤结算结果、综合结算摘要、结算快照摘要展示
- 开奖记录查询、开奖记录采集、手工新增开奖、修正选中开奖
- 结算预览、正式确认结算、结算记录持久化
- 结算历史 / 账目流水只读查询
- 操作日志查询
- 数据总览、订单分析真实数据库统计
- 数据库备份 / 恢复后端与 UI
- 订单、结算流水、操作日志 Excel 导出
- 设置中心：赔率/返水配置方案、申报人配置、导入/导出秘钥本地持久化
- 拆单助手第一阶段：文本整理、拆行、复制结果、保存 txt
- 特码调单第一阶段：只读汇总 + 页面内临时调整，不写数据库
- 连肖调单第一阶段：左侧总表 + 右侧四列表只读汇总，不写数据库
- 全局数据变更自动刷新：订单、日志、结算、开奖、设置、数据库恢复
- 号码大全静态参考表
- 计算器工具

## 当前测试版第一阶段可用 / 只读展示

- 拆单助手仅做文本整理，不识别复杂玩法、不保存订单、不写数据库。
- 特码调单仅做只读汇总和页面内临时调整，不保存真实调整记录。
- 连肖调单仅做只读汇总，不保存真实调整记录，不计算赔付。
- 结算历史 / 结算快照为只读展示，不提供重新结算或修改状态入口。
- 号码大全为静态参考表，不自动随年份更新。

## 当前测试版暂未开放 / 高风险功能暂不开放

- 订单导入、批量删除、清空订单；后续需要权限、审计和数据恢复策略支持
- 清空操作日志；当前操作日志用于审计追溯，不提供清空入口
- 真实调单调整保存、调整记录表、真实打印机调用
- 复杂玩法结算：连肖、多生肖、连尾、胆拖、组选、全包等需要先确认规则
- 正式兑奖、赔率联动、赔付金额、盈亏金额、客户余额流水
- 录单高级选项：特肖模式、抄写法、各->各肖
- 权限系统、云同步、在线账号
- PyInstaller 安装包

## 功能状态与路线图

- [功能状态总览](docs/feature_status.md)
- [后续路线图](docs/roadmap.md)

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

- 同步和维护功能状态文档
- 补充复杂玩法规则文档
- 确认连肖 / 多生肖 / 连尾等玩法结算规则
- 设计调单调整记录表和审计策略
- 设计订单导入流程
- 设计权限系统
- 完成打包发布检查与 PyInstaller 本机试运行

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
