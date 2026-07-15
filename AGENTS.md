# FORTUNE Codex Rules

- 当前开发分支：integration/order-intake-plus-parser
- 不得 reset、restore、checkout、clean
- 默认不 commit、不 push、不构建 dist
- 不修改 data/fortune.db
- 不修改数据库或 migration，除非任务明确要求
- 每次只处理一个玩法
- 不顺带修改其它玩法
- 规则正确性优先于功能数量
- 缺赔率必须阻止正式结算，不能按 0 元结算
- V2 使用新规则；V1 和未知版本禁止正式结算
- 开发时先跑聚焦测试，最终只跑一次全量 pytest
- 最终报告控制在 12 项以内