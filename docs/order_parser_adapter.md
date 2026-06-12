# 订单解析器适配层

本文档记录 `services/order_parser.py` 与 `OrderService.create_order()` 之间的适配边界。

## 解析器公开入口

| 函数 | 说明 |
| --- | --- |
| `parse_order(text: str) -> ParseResult` | 解析单行订单 |
| `parse_lines(text: str) -> list[ParseResult]` | 按行解析，忽略空行 |
| `format_result(result: ParseResult) -> str` | 格式化单条结果（UI 展示用） |
| `format_results(results: list[ParseResult]) -> str` | 格式化多条结果 |

本适配层只调用 `parse_order` / `parse_lines`，不修改解析器实现。

## ParseResult 字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `success` | `bool` | 是否解析成功 |
| `category` | `str` | 解析器内部类别名，如 `单号投注`、`红波`、`多生肖`、`连肖` |
| `numbers` | `tuple[int, ...]` | 展开后的号码（01-49） |
| `amount` | `float` | **每号金额**（各数语义） |
| `total` | `float` | **该行总金额** = `amount × 号码数量` |
| `error` | `str` | 失败原因 |
| `region` | `str` | 文本前缀地区：`澳门` / `香港` / 空 |
| `zodiac_groups` | `list[tuple[str, tuple[int, ...]]]` | 多生肖时每组 `(标准生肖名, 号码元组)` |

## 金额语义

- `amount` 始终是「每个展开号码」的投注金额。
- `total` 已由解析器按 `amount × len(numbers)` 计算。
- 斜杠简写 `01/10`：`amount=10`，`total=10`（单号）。
- 类别投注如 `红波各10`：`amount=10`，`total=10×红波号码个数`。
- 适配层保存时不得再次乘倍；若明细合计与 `total` 不一致则拒绝保存。

## 地区处理

优先级：

1. 文本前缀（`澳门` / `香港`）
2. 调用方显式传入 `region`
3. 默认 `澳门`

文本地区与参数地区冲突时返回错误，不自动选择。

多行文本若解析出不同地区，整单拒绝保存。

## 投注类型映射

| 解析器 category | 保存 bet_type | 保存 selection | 预览 normalized（结算层） |
| --- | --- | --- | --- |
| 单号投注 / 纯数字 | 特码（按号展开） | 01… | special_number |
| 单生肖名（如 `兔`） | 特码（按号展开） | 01… | special_zodiac（按类别预览） |
| 红波 / 蓝波 / 绿波 | 特码波色 | 红波等 | special_color |
| 红单…绿双 | 包半波 | 红单等 | special_half_wave |
| 大 / 小 / 单 / 双 | 特码两面 | 大 / 小 / 单 / 双 | special_size / special_parity |
| 尾N / N头 / 合单合双 / 五行 | 特码（按号展开） | 01… | 按类别预览 |
| 多生肖 / X肖 | 连肖 | 兔,龙,蛇 | 暂不支持结算预览 |
| 全包 | — | — | 标记错误，不可保存 |

复杂玩法（连肖、多生肖）不自动拆成单生肖，不静默丢弃。

## 适配服务接口

`services/order_intake_service.py`：

- `preview_raw_text(...)` → `OrderIntakePreview`（不写库）
- `convert_parsed_result(parsed_result, metadata)` → `OrderIntakePreview`
- `save_preview(preview)` → `OrderIntakeSaveResult`（调用 `OrderService.create_order`）
- `parse_and_save(...)` → 完整流程

命令行预览：`python scripts/preview_order_intake.py --text "01/10" --region 澳门`

## 录单窗口当前行为（只读参考）

`RecordOrderWindow._on_add_result` 将成功解析结果按 **每个号码一行** 写入表格，`投注类型=特码`，金额为 `r.amount`。

适配层对号码类与属性展开类玩法采用相同展开策略；对波色 / 两面 / 半波 / 连肖采用单笔明细保存。

## 可能由朋友后续调整的字段

- `ParseResult.category` 命名（如连肖后缀 `连肖` / `拖肖`）
- `zodiac_groups` 结构
- 地域前缀识别规则
- 新增玩法类别

适配层应通过映射表扩展，不直接修改解析器。
