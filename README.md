# 基于RFM模型的零售客户分群系统实现

## 在线交互演示

[打开项目网页演示](https://blazyz.github.io/rfm-segmentation/)

可体验销售概览、RFM分群、日期筛选、客户查询、明细及CSV导出。公开网页使用自编示例数据，RFM由项目Python代码离线计算，查询与展示在浏览器中完成；不在线运行Flask或MySQL，不提供上传分析。完整本机系统和研究数据口径见下文。


Windows 本机运行的毕业设计系统，采用 **Python + pandas + Flask + MySQL + ECharts**。已实现数据导入、字段校验、清洗审计、RFM计算、规则评分与八类分群、数据库保存、中文可视化、客户查询、明细追查、CSV/Excel导出。

当前项目：`F:\毕业设计`。旧项目 `F:\2027届毕业论文设计` 的原始数据、练习与研究未修改；当前项目另行复制了需要的材料。代码学习与讲解留待系统开发验证后进行。

## 直接启动（本机已配置）

1. 双击项目中的 **start.bat**。
2. 保持命令窗口打开，在浏览器访问 **http://127.0.0.1:5000**。
3. 页面已有2017年实际分析结果，四个入口分别为“销售概览”“RFM分群”“客户查询”“数据管理”。
4. 关闭网页不会停止服务。命令窗口按 **Ctrl+C** 停止网页服务；后台MySQL保持运行，方便下次启动。

如需完全停止项目MySQL，在项目目录打开PowerShell执行：

```powershell
.\.venv\Scripts\python.exe scripts/stop_mysql.py
```

重新双击start.bat会启动同一数据库，不清空历史结果。当前开发会话若服务已在运行，直接打开网页即可，避免重复占用5000端口。

## 页面操作

1. **数据管理**：默认“项目内置原始交易CSV”，保持2017-01-01至2018-01-01（结束日不含）、基准日2018-01-01，点击“开始导入与分析”。相同文件/日期/规则将复用已成功批次，不重复叠加。
2. 更换数据时选“上传同结构交易文件”，支持.csv/.xlsx、最大300MB。新任务会显示进度，完成后自动切换结果；失败会显示原因，保留上一成功结果。原始文件保留。
3. **销售概览**：查看实际金额、购买事件、客户和明细数；支持窗口内日期筛选、月度趋势、柜组与商品排行。销售筛选不改变RFM分析窗口。
4. **RFM分群**：查看人数、金额贡献、RFM均值、实际评分阈值。点击群体名称进入客户筛选。
5. **客户查询**：按完整/部分客户标识或群体查询、排序与翻页，查看RFM及购买明细。导出CSV或Excel包含当前筛选下的全部结果，不仅当前页。
6. **数据管理**质量报告可下载有效明细、排除记录和质量JSON；历史成功批次可“切换查看”。

## 当前正式数据结果

从195,992,414字节原始CSV实际分析，观察2017年、基准日2018-01-01：

| 指标 | 实际值 |
|---|---:|
| 核查原始商品交易明细 | 1,893,532 |
| 有效商品购买明细 | 356,346 |
| 初步购买事件 | 186,971 |
| 客户标识数 | 47,597 |
| 正向购买金额（je） | 515,985,850.95元 |

这些是保守客户标识与正向购买口径的历史教学案例结果，不等于商场全量顾客或净销售额。F按客户+完整时间+收银机+单据号计数，不能用商品明细数代替。数据来源、完整性限制和清洗细节见[计算口径](docs/计算口径.md)及research中的数据核查原件。

## 换一台Windows电脑初始化

当前电脑已经配置好独立Python3.12虚拟环境、依赖、ECharts本地资源和MySQL8.4.6，无需重复安装。

新电脑需要Python3.12、网络（仅首次下载），以及足够磁盘空间。不要直接复制旧电脑的.venv使用；虚拟环境记录解释器路径。

```powershell
# 在项目目录打开PowerShell；不修改系统执行策略，只对本次运行生效
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
# 完成后启动
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

setup.ps1会创建.venv、按requirements.txt安装依赖、下载项目内MySQL及ECharts资源、创建数据库和独立账户。MySQL工具下载约260MB，解压后还需要额外空间。原始教学CSV不适合未经许可公开分发，新电脑应从已保留的原件复制到`data/raw/cumcm2018c/cumcm2018c2.csv`；来源链见research/国内数据来源与适用性核查.md。

手工创建环境可使用Python3.12的实际路径：

```powershell
# 将第一行替换为自己的Python3.12路径
& 'C:\Python312\python.exe' -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/fetch_assets.py
.\.venv\Scripts\python.exe scripts/setup_mysql.py
.\.venv\Scripts\python.exe app.py
```

## 配置与数据库

配置示例为.env.example，实际连接位于.env。首次初始化随机生成应用密码，不写在源码中。项目内MySQL默认127.0.0.1:3307、数据库retail_rfm、账户rfm_app；不占用常见3306端口，不覆盖已安装的服务。管理员密码保存在runtime/mysql-admin.env。两份文件应保留本机，不公开上传。

表结构在schema.sql。初始化脚本重复执行只补建缺失表，不重置数据；按实例UUID确认连接到本项目数据库，避免误改其他实例。中文目录导致的MySQL Windows参数解析问题已在启动脚本处理。

如果自己已有MySQL，可由管理员先创建库和账户，在目标库执行schema.sql，再把实际连接填入.env，直接执行`python app.py`。start.ps1默认维护项目内实例，因此外部数据库不使用该启动脚本。示例SQL（请替换密码）：

```sql
CREATE DATABASE retail_rfm CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
CREATE USER 'rfm_app'@'127.0.0.1' IDENTIFIED BY '替换为自己的强密码';
GRANT SELECT,INSERT,UPDATE,DELETE ON retail_rfm.* TO 'rfm_app'@'127.0.0.1';
USE retail_rfm;
-- 在此数据库执行schema.sql
```

## 备份与恢复

```powershell
.\.venv\Scripts\python.exe scripts/backup_db.py
```

SQL备份保存至runtime/backups，文件名含实际时间。另行备份data/raw、data/uploads、data/runs、.env和runtime/mysql-admin.env，SQL备份不包含原始文件与清洗文件。

恢复时先初始化一个空的目标数据库（不要直接覆盖重要数据），使用MySQL客户端或Navicat导入SQL。SQL中包含DROP TABLE，应只导入确认用于恢复的库。对应的原文件/批次文件要恢复到原目录，若换了项目路径，需要更新analysis_batches.source_path。验证时已在单独恢复库导入备份并核对，实际结果见docs/备份恢复验证.json。

## 开发验证与材料

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
# 以下需要服务已启动，正式原始数据已分析完成
.\.venv\Scripts\python.exe scripts/verify_system.py
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe scripts/verify_browser.py
.\.venv\Scripts\python.exe scripts/rule_sensitivity.py
```

verify_system会保留明确标注的测试文件/批次，结束时恢复正式原始数据批次。测试中的合成Excel仅验证边界，不作为研究结果。开发过程中早期失败批次如实保留，不表示当前正式批次失败。

- `docs/开发记录.md`：实际进度、排错与下一步。
- `docs/计算口径.md`：清洗、RFM、评分、分群与统计范围。
- `docs/数据库与接口.md`：表关系、索引、接口。
- `docs/系统验证结果.json`：HTTP、数据库、独立复算、导出一致性记录。
- `docs/浏览器验证结果.json`、`docs/系统截图/`：实际Chromium操作验证与截图。
- `docs/验证输出/`：实际结果导出与代表客户核对，包含客户数据，请保留本机。
- `runtime/app.log`、`runtime/mysql-error.log`：排错日志。

## 常见问题

- **打不开网页**：先运行start.bat并保留窗口，查看是否已显示启动地址；不要重复启动多个5000端口服务。
- **数据库不可用**：运行scripts/setup_mysql.py；检查.env端口是否冲突、runtime/mysql-error.log，勿删除mysql-data强行重置。
- **导入失败**：数据管理查看错误；会员信息Excel不含交易12字段，不能用它代替交易表。
- **中文乱码**：网页为UTF-8；CSV导出带BOM，Excel使用“数据→从文本/CSV”并选择UTF-8也可打开。命令窗口乱码不等于文件内容损坏。
- **误关程序**：重新启动，上次未完成任务会记为失败，可重新导入；已成功批次继续保留。

## 仍未完成的非开发事项

学校任务书/论文模板及节点未取得，论文正文、答辩PPT、真实同学试用评价不在此次已完成开发中。未开展真实企业部署、营销效果实验、并发多用户或高可用验证。官方旧附件完整性和商场真实身份仍未核实；不能将教学副本包装为自采企业数据。
