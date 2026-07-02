# 账务 / 余额流水模型

本文记录 Fortune 客户账户与余额流水的第一阶段口径。当前版本状态为：商用测试版 / 内部试用版。

## 当前状态

- 客户账户 / 余额流水第一阶段已开放。
- 已支持客户账户创建、余额查询、流水查询。
- 已支持手工加款、手工扣款。
- 余额不能直接覆盖，只能通过余额流水变动。
- 每次余额变动会写 `OperationLog`。
- 当前不自动把正式结算中奖金额入账。
- 当前不开放真实兑奖。
- 当前不做返水 / 佣金。
- 当前不做权限审批。
- 当前不开放清空、重置类账务维护。

## 已新增核心对象

| 对象 | 职责 |
| --- | --- |
| 客户账户 | 保存客户身份、账户状态和当前余额摘要。 |
| 余额流水 | 记录所有余额变动，作为余额变动的唯一事实来源。 |
| 结算记录 | 保存订单结算结果、命中明细和基础中奖金额快照。 |
| 操作日志 | 记录手工加款、手工扣款和后续账务动作的审计摘要。 |

## 表结构口径

### customer_accounts

- `id`
- `customer_name`
- `display_name`
- `balance`
- `status`
- `note`
- `created_at`
- `updated_at`

### account_ledger_entries

- `id`
- `customer_id`
- `customer_name`
- `direction`：`in` / `out`
- `amount`
- `balance_before`
- `balance_after`
- `entry_type`
- `source_type`
- `source_id`
- `order_id`
- `settlement_record_id`
- `adjustment_record_id`
- `reason`
- `operator`
- `created_at`
- `audit_log_id`
- `is_reversed`
- `reversed_by_id`

## 第一阶段已开放流水类型

- 手工加款：`manual_credit`，方向为 `in`。
- 手工扣款：`manual_debit`，方向为 `out`。
- 手工冲正：`manual_reversal`，用于反向冲正已写入流水。

## 账务原则

- 所有金额使用 `Decimal`。
- 禁止 `float`。
- 金额必须大于 0。
- 手工加款 / 扣款必须填写原因。
- 本阶段默认不允许余额扣成负数。
- `balance_before` / `balance_after` 必须由服务层在同一事务内计算。
- 余额字段不能作为人工覆盖入口，只能由流水服务变动。
- 流水写入、余额更新和操作日志写入必须事务化。

## 与现有系统关系

- `SettlementRecord` 目前只保存基础中奖金额快照。
- 正式结算不会自动创建客户账户，也不会自动写余额流水。
- `Order` 当前仍是订单事实来源，本阶段不修改历史订单。
- `AdjustmentRecord` 当前只是调单快照，不影响余额。
- `OperationLog` 会记录手工加款 / 扣款的客户、金额、变动前后余额、原因和操作人。

## 仍未开放

- 真实兑奖。
- 结算中奖金额自动入账。
- 投注自动扣款。
- 返水 / 佣金。
- 权限 / 登录 / 角色 / 审批。
- 清空账务流水。
- 直接覆盖余额。
- 根据历史订单自动推算余额。
## 2026-07-02：真实兑奖 / 结算中奖金额入账第一阶段

- 已开放已正式结算订单的“兑奖入账”入口。
- 入账金额只读取 `SettlementRecord.result_snapshot` 中保存的中奖金额快照，优先读取 `summary.total_payout_amount`，并兼容当前快照的 `settlement.total_payout_amount`。
- 入账不重新计算赔率，不重新读取当前赔率配置。
- 入账会自动按订单 `customer_name` / 申报人创建或读取客户账户。
- 入账流水字段：`direction=in`、`entry_type=settlement_payout`、`source_type=settlement_record`、`source_id=settlement_record.id`、`order_id=order.id`、`settlement_record_id=settlement_record.id`、`reason=结算中奖金额入账`。
- `settlement_records` 增加入账状态字段：`payout_posted_at`、`payout_ledger_entry_id`、`payout_posted_amount`，用于防止同一结算记录重复入账。
- 入账成功会写 `OperationLog`，`module=accounting`、`action=ledger/settlement_payout`。
- 中奖金额为 0、订单缺少客户/申报人、旧快照缺少总中奖金额时不会自动入账。
- 当前仍不做返水 / 佣金，不做权限审批，不做冲正 / 回滚 UI，不开放清空或重置。
