# 订单数据协作协议

本文档约定订单解析模块与订单保存模块之间的边界。当前阶段不要求录单窗口直接接入数据库。

## DTO

### OrderCreate

- `customer_name`: 可选字符串，客户名。
- `channel`: 可选字符串，来源渠道，例如个人微信、现金。
- `region`: 必填，`澳门` 或 `香港`。
- `raw_text`: 必填，原始订单文本。
- `source`: 必填，订单来源，例如 `manual`、`clipboard`、`import`。
- `items`: 必填，`OrderItemCreate` 列表，至少一条。

### OrderItemCreate

- `bet_type`: 必填，投注类型，例如 `特码`、`平特一肖`、`连肖`。
- `selection`: 必填，投注内容，例如 `01`、`龙`、`01,02,03`。
- `amount`: 必填，金额。进入服务层后统一转换为 `Decimal`。
- `odds`: 可选赔率。进入服务层后统一转换为 `Decimal`。
- `note`: 可选备注。

## 订单解析模块职责

- 将原始文本解析成结构化数据。
- 返回创建 `OrderCreate` 所需字段。
- 不直接访问 SQLite。
- 不直接创建 SQLAlchemy `Session`。
- 不负责生成订单号。
- 不负责开启数据库事务。

## 订单服务职责

- 校验结构化数据。
- 标准化号码和投注类型。
- 使用 `Decimal` 处理金额。
- 重新计算订单总金额，不相信外部传入总额。
- 生成唯一订单号。
- 开启数据库事务。
- 保存订单和订单明细。
- 保存失败时整体回滚。
- 保存成功时写入操作日志。

## 调用示例

```python
from schemas.order_schema import OrderCreate, OrderItemCreate
from services.order_service import OrderService

payload = OrderCreate(
    customer_name="张三",
    channel="个人微信",
    region="澳门",
    raw_text="1各10\n2各20",
    source="manual",
    items=[
        OrderItemCreate(bet_type="特码", selection="1", amount="10"),
        OrderItemCreate(bet_type="特码", selection="2", amount="20"),
    ],
)

result = OrderService().create_order(payload)
print(result.order_no, result.total_amount)
```

## 给录单模块的建议

录单模块完成解析后，只需要组装 `OrderCreate`。在本阶段不要在录单窗口里创建数据库连接，也不要直接操作 ORM 模型。后续接入时建议通过单独的应用服务或信号回调调用 `OrderService.create_order()`。
