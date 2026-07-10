# 打包前自检清单

本文档供开发或发布负责人在执行 PyInstaller 打包、交付测试包之前逐项核对。目标是避免私人数据泄露、依赖缺失、测试残留进入安装包。

---

## 一、禁止打入安装包的内容

### 1. 不要打包 `data/fortune.db` 的真实业务数据

- [ ] 确认打包脚本或 spec 未包含 `data/fortune.db`
- [ ] 若需附带空库，应使用专门生成的空模板，而非开发/试用真实库
- [ ] 检查 `dist/`、`build/` 输出目录中是否误复制了真实数据库

**风险**：泄露客户订单、金额、操作记录。

### 2. 不要打包 `data/backups/` 私人备份

- [ ] 确认 `data/backups/*.db` 不在打包文件列表中
- [ ] 发布目录中仅保留空 `backups` 目录或首次运行自动创建

**风险**：备份文件含完整历史数据，泄露范围更大。

### 3. 不要打包 `.pytest_tmp_cursor*` 测试目录

- [ ] 项目根目录下无 `.pytest_tmp_cursor*` 被打入包内（允许工作区存在，但不得 copy 进 dist）
- [ ] `.gitignore` 已忽略 `.pytest_tmp/`；打包前运行 `python scripts/pre_release_check.py` 查看警告

**风险**：无直接业务风险，但增大体积、暴露开发路径与测试结构。

### 4. 不要打包 `exports/` 测试导出文件

- [ ] `exports/` 下测试生成的 `.xlsx` 不进入安装包
- [ ] 打包 spec 仅创建空 `exports` 或在首次运行时创建

**风险**：导出文件可能含订单与日志明细。

### 5. 不要打包项目根目录或 `exports/` 下的 `.xlsx` 测试文件

- [ ] 根目录无遗留 `*.xlsx`
- [ ] `exports/` 无遗留测试导出

**风险**：同第 4 项。

---

## 二、依赖与环境

### 6. 确认 `requirements.txt` 依赖完整

- [ ] `requirements.txt` 存在且包含：PySide6、SQLAlchemy、matplotlib、alembic、pytest、httpx、openpyxl
- [ ] 打包所用虚拟环境与 `requirements.txt` 一致
- [ ] 无遗漏隐式依赖（如 sqlite3 为标准库，无需列出）

### 7. 确认 openpyxl 可用

- [ ] `python -c "import openpyxl; print(openpyxl.__version__)"` 成功
- [ ] 在界面中试导出一份表格无报错

### 8. 确认 PySide6 可用

- [ ] `python -c "from PySide6.QtWidgets import QApplication; print('ok')"` 成功
- [ ] 离线环境（`QT_QPA_PLATFORM=offscreen`）下测试可启动（CI/自动化用）

### 9. 确认 SQLAlchemy 可用

- [ ] `python -c "import sqlalchemy; print(sqlalchemy.__version__)"` 成功
- [ ] 应用启动时能连接/创建 SQLite 库

---

## 三、质量门禁

### 10. 确认 pytest 全量通过

- [ ] 执行：`python -m pytest --basetemp=".pytest_tmp_cursor20"`
- [ ] 全部通过，无 skip 以外的失败
- [ ] 测试数量符合当前基线（> 402）

### 11. 确认启动脚本路径正确

- [ ] `python main.py` 可从项目根启动
- [ ] 若使用 `启动Fortune.bat`，路径指向正确 Python 与 `main.py`（bat 本身通常不提交仓库）
- [ ] 打包后 exe 工作目录下 `data/`、`exports/` 相对路径正确

### 12. 确认首次运行会创建必要目录

- [ ] 删除本地 `data/`、`exports/`（仅测试机）后启动，程序自动创建目录
- [ ] `data/backups/` 在首次备份或恢复流程中可用
- [ ] 空库或迁移可正常执行（Alembic upgrade head）

---

## 四、发布策略

### 13. 确认备份 / 恢复 / 导出目录策略

- [ ] 备份固定写入 `data/backups/`
- [ ] 导出默认目录为 `exports/`，用户可在对话框另选
- [ ] 文档中已说明不要手动删除正在使用的 `fortune.db`

### 14. 确认异常不会导致程序崩溃

- [ ] 录单解析失败、结算缺少开奖、备份失败等均有 UI 提示
- [ ] 未捕获异常不应导致静默退出（可在测试环境故意触发常见错误）

### 15. 确认当前版本只暴露可用功能

- [ ] 对照 `docs/commercial_test_scope.md`，高风险维护入口已受保护，仍未开放入口已隐藏/禁用/标注
- [ ] README 与界面文案无「尚未接入数据库」等过期描述
- [ ] 连码/连肖调单、拆单助手等第一阶段功能不越界写业务库；批量删除如执行必须走高风险保护流程

---

## 五、发布前自动化自检

执行只读脚本（不修改任何文件）：

```powershell
python scripts/pre_release_check.py --project-root .
```

- [ ] 无 **失败** 项（脚本退出码为 0，或仅有警告）
- [ ] 对 **警告** 项（`.pytest_tmp_cursor*`、遗留 `.xlsx`）逐项处理或确认可忽略

---

## 六、打包后抽查

- [ ] 在干净目录解压/安装，首次启动成功
- [ ] 安装目录内无 `fortune.db` 真实数据、无 `backups/*.db`、无测试 xlsx
- [ ] 版本号或构建标识可识别（便于试用反馈）
- [ ] 附带 `docs/manual_test_script.md` 或精简版试用说明

---

## 签字确认

| 检查项 | 负责人 | 日期 | 结果 |
|--------|--------|------|------|
| 数据与隐私 | | | |
| 依赖与环境 | | | |
| pytest | | | |
| 只读自检脚本 | | | |
| 打包产物抽查 | | | |
