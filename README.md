# Fortune

Fortune 是一个基于 Python 的本地桌面应用，当前围绕订单录入、号码规则、开奖数据和订单分析功能逐步建设。

## 技术栈

- Python
- PySide6 / Qt Widgets
- SQLite
- SQLAlchemy 2.0
- Alembic
- matplotlib
- pytest

## 环境要求

建议使用 Python 3.11 或更高版本。当前开发环境曾使用 Python 3.13。

## 安装依赖

```bash
pip install -r requirements.txt
```

## 启动应用

```bash
python main.py
```

Windows 下也可以使用本地启动脚本 `启动Fortune.bat`，其内容等价于 `python main.py`。

## 数据库

默认数据库位置：

```text
data/fortune.db
```

当前 `data/fortune.db` 已被 Git 跟踪。如果后续决定停止跟踪，需要由维护者手动执行相应 Git 操作。

## 数据库迁移

创建迁移：

```bash
alembic revision --autogenerate -m "message"
```

执行迁移：

```bash
alembic upgrade head
```

临时数据库迁移测试示例：

```bash
$env:FORTUNE_DATABASE_URL="sqlite:///tmp/fortune_migration_test.db"
alembic upgrade head
```

## 运行测试

```bash
pytest
```

测试使用临时 SQLite 数据库，不应直接访问 `data/fortune.db`。

## 当前已完成功能

- PySide6 主窗口与顶部导航。
- 订单文本解析服务。
- “我要录单”独立窗口的基础交互。
- 号码大全页面和搜索。
- 计算器工具。
- 数据总览、订单分析、开奖、订单详情、操作日志等页面原型。
- 数据基础层：领域规则、DTO、ORM 模型、仓储、服务、Alembic 迁移和基础测试。

## 尚未完成功能

- 录单窗口尚未接入数据库。
- 订单详情、数据总览、订单分析仍未读取真实订单数据。
- 开奖数据抓取、导入导出、兑奖、拆单助手、调单业务尚未实现。
- 用户权限、在线账号、赔率版本等复杂模型尚未设计。

## 录单模块与数据库模块协作方式

录单和订单解析模块负责把文本转换为结构化数据，不直接访问 SQLite，也不直接创建 SQLAlchemy `Session`。

数据库模块通过 `schemas.order_schema.OrderCreate` 和 `services.order_service.OrderService.create_order()` 保存订单。详细协议见：

```text
docs/order_data_contract.md
```
