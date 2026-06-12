# 49wz777 开奖数据源调查

调查日期：2026-06-12

目标站点：

```text
https://49wz777.com/
```

## 调查过的页面

- 首页：`https://49wz777.com/`
- 历史开奖路由：`https://49wz777.com/history?lotteryType=2`
- 静态脚本：
  - `/js/app.6d293d72.js`
  - `/js/842.62122c50.js`

首页 HTML 是 Vue/SPA 应用壳，未启用 JavaScript 时只显示提示。真实接口来自 JS bundle。

## 请求封装

`app.6d293d72.js` 中的请求封装会将以 `/` 开头的 API 路径加上前缀：

```text
/site/h5
```

例如：

```text
/index/uniteInfo -> /site/h5/index/uniteInfo
/lottery/search -> /site/h5/lottery/search
```

## 最新开奖数据

调查发现首页接口：

```text
GET https://49wz777.com/site/h5/index/uniteInfo
```

该接口可公开访问，返回 `uniteInfos[].lastLotteryRecord`。但实际响应中最新记录的 `numberList[].number` 在调查时不是稳定的数字格式，出现非数字占位/编码值，因此本阶段不将它作为正式保存来源。

正式“最新开奖”使用历史接口的第一页第一条：

```text
GET https://49wz777.com/site/h5/lottery/search?pageNum=1&pageSize=1&lotteryType=2&year=2026&sort=1
```

## 历史开奖接口

### 年份列表

```text
GET https://49wz777.com/site/h5/lottery/listYear?lotteryType=2
```

响应字段：

```json
{
  "success": true,
  "data": {
    "list": [2026, 2025, 2024, 2023, 2022, 2021, 2020]
  }
}
```

### 分页历史

```text
GET https://49wz777.com/site/h5/lottery/search
```

参数：

- `pageNum`: 页码，从 1 开始。
- `pageSize`: 每页数量。站点页面默认 25。
- `lotteryType`: 彩种类型。
- `year`: 年份。
- `sort`: 排序。站点历史页使用 `1`，代表最新在前。

示例：

```text
GET https://49wz777.com/site/h5/lottery/search?pageNum=1&pageSize=3&lotteryType=2&year=2026&sort=1
```

响应核心字段：

```json
{
  "success": true,
  "data": {
    "pager": {
      "pageNum": 1,
      "pageSize": 3,
      "totalCount": -1,
      "totalPageCount": 1
    },
    "recordList": [
      {
        "lotteryTime": "2026年06月11日",
        "lotteryType": 2,
        "numberList": [
          {"number": "23", "shengXiao": "猴", "wuXing": "木"},
          {"number": "41", "shengXiao": "猴", "wuXing": "金"},
          {"number": "24", "shengXiao": "羊", "wuXing": "木"},
          {"number": "26", "shengXiao": "蛇", "wuXing": "金"},
          {"number": "33", "shengXiao": "狗", "wuXing": "金"},
          {"number": "07", "shengXiao": "鼠", "wuXing": "木"},
          {"number": "32", "shengXiao": "猪", "wuXing": "火"}
        ],
        "period": 2026162,
        "periodStr": "162",
        "year": 2026
      }
    ]
  }
}
```

## 字段映射

映射到 `LotteryDrawCreate`：

- `region`: 由 `lotteryType` 映射。
- `issue_number`: `periodStr`，缺失时可退回 `period`。
- `draw_date`: `lotteryTime`，支持 `YYYY年MM月DD日`。
- `regular_numbers`: `numberList` 前 6 个号码。
- `special_number`: `numberList` 第 7 个号码。
- `source`: 固定为 `49wz777`。
- `status`: 固定为 `confirmed`。

## 彩种与地区

从 JS 和接口调查可见：

- `lotteryType=2`: 澳门
- `lotteryType=1`: 香港
- `lotteryType=3`: 台湾
- `lotteryType=4`: 新加坡
- `lotteryType=7`: 3D

当前 Fortune 项目统一地区只支持 `澳门` 和 `香港`，因此正式同步只开放 `lotteryType=2` 和 `lotteryType=1`。

## 访问限制

- 不需要登录。
- 不需要 Cookie。
- 未发现验证码。
- 未发现 GraphQL。
- 未发现必须使用 WebSocket 才能获取历史开奖。
- 首页最新接口返回内容不适合作为正式保存来源，使用历史接口第一页替代。
- 应避免高频请求；客户端默认每次重试指数退避，历史同步需要显式指定页数。

## 已知限制

- `pager.totalCount` 在样本中为 `-1`，不能依赖它自动抓取全部历史。
- 网站结构或接口前缀变化时，主要修改：
  - `scrapers/wz49_client.py`
  - `scrapers/wz49_parser.py`
- 如果站点后续返回 403、429、验证码或登录要求，应停止同步，不应绕过限制。
