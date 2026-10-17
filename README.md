# 期货消息聚合推送 Agent

把分散的期货市场消息源（财联社电报、华尔街见闻等）自动采集、去重、用 LLM 筛选提炼，
把重要的推送到飞书。

## 工作流

```
                         ┌─ 命中加急规则 ─→ 🚨 立即单独推送（绕过 LLM）
采集器(各来源) → 去重 ─┤
                         └─ 其余 → 缓冲累积 → 规则预筛 → 聚类 → LLM提炼 → 📊 汇总推送
```

**两个节奏解耦**（试运行期都可在 `config.yaml` 的 `schedule` 段调）：
- **加急快循环**：默认每 **60 秒**抓一次，命中「行情突变 / 交易所通知」立刻 🚨 单独推，不耗 LLM。
- **常规汇总**：把非加急消息攒着，活跃时段（默认工作日 8:30–23:00）**每 15 分钟**、
  夜间/周末**每 4 小时**走一次 LLM 提炼后 📊 汇总推。这是耗额度的部分，按时段控频。

- **采集层**：每个来源一个采集器，目前内置 `财联社电报`、`华尔街见闻`。
  - **华尔街见闻**支持游标翻页：每轮从上次见过的最新条目往前**增量取全**，长间隔也不漏。
  - **财联社**接口不支持游标、单次最多 50 条，只能取最新一批靠去重兜底
    （故 `off_interval` 别设太大，否则隔夜高峰可能漏中间的）。
- **去重**：SQLite 记录已处理条目，重启不重复推送；按 `uid` 主键查，表再大也是亚毫秒级。
  默认每 30 天滚动清理旧行（`storage.retention_days`），只控磁盘体积、不影响去重。
- **规则预筛**：先用关键词/来源重要标记缩小候选，**省 LLM 额度**（关键，因为快讯量大）。
- **加急直通道**：两类突发消息**绕过预筛和 LLM、当轮立即单独推**（飞书 🚨 一条）：
  ① 行情突变（品种 + 急涨跌/拉升/跳空/暴涨跌/涨跌停，自动排除股票/外汇/加密类降噪）；
  ② 交易所通知（六大交易所/品种名 + 保证金/涨跌停板/手续费/限仓等动作词）。
  词表全在 **`keywords.yaml`**，可随时增删。
- **行情优先级**：纯规则识别「某品种涨跌幅/拉升暴跌/涨停跌停/创新高低」类消息，标 🔥
  高优先级——强制推送、飞书里置顶。
- **相似聚类**：同一事件的多条快讯（常见 4-5 条讲一件事）合成一组，**只把代表喂给 LLM**，
  进一步省调用；飞书里显示「+N条同类」。阈值由 `prefilter.similarity_threshold` 调。
- **LLM 提炼**：支持两个并列提供方，通过 `llm.provider` 一行切换：
  - `codex`：调用本机 `codex exec`，复用 **ChatGPT/Codex 订阅**额度；
  - `claude`：保留原来的 `claude -p` 实现，继续复用 **Claude 订阅**额度。
- **Codex 隐私隔离**：每批资讯强制用 `--ephemeral` 临时会话，关闭记忆读取和生成，
  从 stdin 传入资讯并在一次性空目录中只读运行，不产生可恢复的本地 Codex 历史会话。
- **推送**：飞书自定义机器人 webhook。每轮把判定为重要的多条**汇总成一条消息**发出（单条则直接发）。

## 准备

1. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
2. 安装 **Codex CLI**，并用 ChatGPT 账户登录：
   ```bash
   npm install -g @openai/codex
   codex login
   codex login status
   ```
   如果 Windows PowerShell 提示禁止运行 `codex.ps1`，请改用
   `codex.cmd login` 和 `codex.cmd login status`；程序本身会优先查找 `.cmd`。
   `config.yaml` 默认选择 `provider: codex`。程序只使用保存的登录凭据，不需要 API key。
   Windows 下若 `codex` 不在 PATH，程序会自动查找 VS Code / VS Code Insiders 的
   OpenAI 扩展内置版本；也可把 `llm.codex.command` 改成 `codex.cmd` 或 `codex.exe` 的绝对路径。
3. 在飞书群里添加「自定义机器人」，拿到 webhook 地址。
4. 复制配置并填写：
   ```bash
   cp config.example.yaml config.yaml
   ```
   把 `feishu.webhook_url`（和可选的 `secret`）填进去。

## 运行

```bash
python run.py            # 持续轮询
python run.py --once     # 只跑一轮，方便测试
```

### Windows 一键启动

直接双击项目根目录下的 `start_message_agent.bat`。脚本会自动切换到项目目录，
依次查找项目虚拟环境、Anaconda/Miniconda 和系统 Python，并在缺少依赖时按
`requirements.txt` 安装，然后启动持续轮询。

也可以在命令提示符中使用：

```bat
start_message_agent.bat --check   rem 只检查环境，不采集或推送
start_message_agent.bat --once    rem 只运行一轮
```

持续运行时按 `Ctrl+C` 停止。程序异常退出后窗口会保留，便于查看错误信息。

## 轮询节奏（试运行期随意调，改完重启生效）

全在 `config.yaml` 的 `schedule` 段，纯数字：

| 项 | 默认 | 含义 |
| --- | --- | --- |
| `urgent_interval` | 60 | 加急抓取间隔（秒），全天候。想更快/更慢改这里 |
| `active_start`/`active_end` | 08:30 / 23:00 | 活跃时段（工作日） |
| `active_digest_interval` | 900 | 活跃时段汇总间隔（秒）= 15 分钟 |
| `off_digest_interval` | 14400 | 夜间(23:00-8:30)/周末汇总间隔（秒）= 4 小时 |

觉得消息太密 → 调大 `active_digest_interval`（如 1800=30 分钟）；想加急更快 →
`urgent_interval` 调到 30。改完重启 `python run.py` 即可。

## 关键词词库（keywords.yaml，可随时编辑）

筛选/加急用到的全部词都在 `keywords.yaml`，分五段，想到就加、不要就删，改完重启生效：

- `prefilter`：常规汇总的预筛关键词（命中才交给 LLM）。
- `urgent_names`：交易所名 + 六大交易所品种名（加急的前提，必须先命中名字）。
- `urgent_actions`：交易所公告动作词（保证金/涨跌停板/手续费…）。
- `urgent_moves`：行情突变词（急涨跌/拉升/跳空/暴涨跌/涨跌停）。
- `urgent_excludes`：行情加急的排除词（个股/A股/美股/外汇/比特币…，只看期货品种）。

（`config.yaml` 里 `prefilter.keywords` 留空就用 `keywords.yaml`；`urgent.extra_*` 可临时追加而不动词库。）

## 配置要点（config.yaml）

- `sources.*.enabled`：开关各来源。
- `sources.cls.rn`：财联社单次条数，上限 50。
- `sources.wallstreetcn.limit` / `max_pages`：每页条数（上限 100）/ 单轮最多翻几页。
- `storage.retention_days`：DB 旧行保留天数（默认 30，设 0 永不清理）。
- `prefilter.similarity_threshold`：相似聚类阈值（默认 0.45）。建议 0.4~0.5。
- `llm.provider`：`codex` 使用 ChatGPT/Codex 订阅；`claude` 使用保留的 Claude 订阅实现。
- `llm.codex.command` / `llm.claude.command`：对应 CLI 命令或绝对路径。
- `llm.codex.model` / `llm.claude.model`：留空使用对应 CLI 的默认模型。
- `llm.batch_size`：单次调用塞多少条候选，控制额度消耗。

切回 Claude 只需修改：

```yaml
llm:
  provider: claude
```

并确保本机的 `claude -p` 可以正常运行。原有 `llm.command` / `llm.model` 顶层写法仍兼容旧配置。

## 额度提醒

财联社/华尔街见闻是 24 小时滚动快讯，量很大。加急只走规则不耗 LLM；耗额度的是「常规汇总」，
靠 `prefilter` 粗筛 + 聚类 + 按时段控频（`*_digest_interval`）来压。若对应订阅额度触顶，
可调大 `active_digest_interval`、精简 `keywords.yaml` 的预筛词，或 `sources.cls.only_important: true`。

## 后续可扩展（按难度递增）

- 小红书当日热点品种（反爬强、需登录态）
- 微信群（个人号挂机器人，有封号风险）

新增来源：在 `src/sources/` 下实现一个 `Source` 子类的 `fetch()`，再在 `src/main.py` 的
`build_sources()` 里登记即可。
