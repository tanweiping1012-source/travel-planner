# Travel Planner MVP

[![CI](https://github.com/tanweiping1012-source/travel-planner/actions/workflows/ci.yml/badge.svg)](https://github.com/tanweiping1012-source/travel-planner/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%20--%203.14-blue.svg)](.github/workflows/ci.yml)

**让 AI 用真实数据规划旅行，而不是靠搜索来的二手攻略。**

行程里的每一个数字——距离、通勤时长、余票、票价——都来自工具调用，并带来源和
时间戳。模型只负责取舍和解释，不生成任何数字。

生成的行程会先过一遍确定性可行性检查（时间窗、换乘余量、营业时间、预算），
排不通的方案不会送到你面前。

这是一个 Agent Skill，可以装进 Claude Code、OpenAI Codex、TRAE 或其他支持
Skill、Shell 和 MCP 的客户端。

## 它解决什么问题

规划一次旅行，真正花时间的不是决策，是**信息采集**。

为了不多花冤枉钱，你得自己去搜路线怎么走、机票和高铁多少钱、哪些景点值得去。
小红书翻半天、携程比价再半天，才拼出一个大致框架。然后开始比酒店，结果发现
住宿位置又反过来推翻了前面排的行程，回头再改一遍。

现在的 AI 工具帮不上这个忙。它们大多靠 web search 拼凑答案，看着像那么回事，
但**落地时几乎每一条都要重新核对**——车程是编的、票价是旧的、营业时间是错的，
最后还是得自己重查一遍，等于白做。

这个 Skill 换了个做法：**用真实数据还原一个能直接执行的方案**。

- 机票查携程等 OTA 的实际航班与可见价格
- 高铁查 12306 的真实车次、余票和票价
- 路线和车程查高德，不是估算
- 每个数字都带来源和查询时间，模型不生成任何数字
- 排完先过一遍可行性检查，时间对不上的方案不会送到你面前

**当你已经确定了目的地和日期**，它能把这堆散落的信息整合成一份真正可执行的
方案，并告诉你哪些地方还需要你自己确认。

## 它不解决什么问题

**① 它不擅长「不知道去哪、也没定日期」的场景。**

现在的能力是围绕「目的地和时间已定」设计的：数据源要有明确的出发地、目的地
和日期才能查。如果你想问的是"国庆前后从上海出发，哪里比较划算"——这种在
多个目的地、多个日期之间横向比较的需求，它还做不好。

**② 它是只读的。** 装上之后它**不能**：

- 购买、预订、支付、候补、改签、退票——它没有下单能力
- 输入你的密码、短信验证码、身份证件或支付信息——登录和验证码永远交还给你
- 导出你的 Cookie、Token 或浏览器会话
- 点赞、收藏、关注、评论、发布，或以任何方式改动你的账号
- 绕过验证码、登录墙或平台风控
- 批量抓取小红书笔记、评论、图片或视频

它只看，不动。需要登录时它会停下来把控制权交给你。

**③ 酒店比价还没有接入。** 上面说的「住宿反过来推翻行程」那一环，目前需要
你自己完成，再把结果告诉它重新排。

## 五分钟上手

### Claude Code

```bash
git clone https://github.com/tanweiping1012-source/travel-planner.git
ln -s "$(pwd)/travel-planner" ~/.claude/skills/travel-planner-mvp
bash ~/.claude/skills/travel-planner-mvp/scripts/setup_amap_key.sh
bash ~/.claude/skills/travel-planner-mvp/scripts/setup_rail_mcp.sh
```

用软链接而非拷贝，仓库始终是唯一事实源，`git pull` 后立即生效。

然后把 12306 加进 `~/.claude.json` 的 `mcpServers`（见[配置 12306](#配置-12306-mcp)），
重启客户端，再运行：

```bash
python3 ~/.claude/skills/travel-planner-mvp/scripts/travel_planner.py doctor --live
```

`doctor` 会自动识别当前客户端，无需手动指定。

### OpenAI Codex

```text
使用 $skill-installer 安装 GitHub 仓库
https://github.com/tanweiping1012-source/travel-planner
根目录中的 Skill，名称为 travel-planner-mvp。
```

记录安装器返回的绝对路径（不同 Codex 版本和 `CODEX_HOME` 会落在不同目录），
然后：

```bash
bash <SKILL_ROOT>/scripts/setup_amap_key.sh
bash <SKILL_ROOT>/scripts/setup_rail_mcp.sh --register-codex
```

重启 Codex 后运行 `doctor --live` 检查。

### 其他客户端

仓库根目录本身就是 Skill 目录。放进客户端的 Skill 发现路径即可：

| 客户端 | 项目级 | 用户级 |
|---|---|---|
| Claude Code | `<workspace>/.claude/skills/` | `~/.claude/skills/` |
| OpenAI Codex | `<workspace>/.agents/skills/` | `~/.agents/skills/` |
| TRAE | `<workspace>/.trae/skills/` | — |

客户端不支持 Skill 结构时，可以把 `SKILL.md` 当作项目规则加载，允许 Agent 读取
`references/` 并执行 `scripts/travel_planner.py`，再单独配置 12306 MCP 和 Browser Use。

每位用户配置自己的高德 Key；Key 存入本机钥匙串，不随仓库或 Skill 分发。

## 能力概览

| 能力 | 数据来源 | 作用 |
|---|---|---|
| 攻略与路线研究 | Browser Use | 从小红书读取景点、玩法、路线走法、包车与门票行情、排队与体感、季节性信息 |
| 机票查询 | Browser Use | 从携程等 OTA 网页读取指定日期的航班、时刻与可见价格 |
| 地点与市内路线 | 高德 Web API | 校验 POI、坐标，计算步行、公交和驾车真实耗时 |
| 高铁查询 | 社区 12306 MCP | 车次、余票、票价、经停站和中转方案；余票词表经归一化后可比较排序 |
| 可行性检查 | 本地 Python | 时间冲突、换乘缓冲、营业时间、预算和体力负荷 |
| 内容完整性检查 | 本地 Python | 拒绝只有交通、缺少景点特色与游玩说明的方案 |

> **Browser Use** 在本文中指任何满足[浏览器契约](references/browser-use.md)的
> 浏览器自动化能力——客户端内置浏览器、Playwright MCP 或其他适配器均可，
> 不绑定特定实现。

## 怎么用

直接用自然语言说清楚就行。信息完整时，Agent 会校验后直接开始研究；有缺失或
冲突时，会一次性汇总询问，不会来回追问。

```text
使用 $travel-planner-mvp。2027 年 4 月 10 日至 13 日，广州出发去桂林和阳朔，
2 人，人均预算 3500 元，节奏均衡。龙脊梯田为 CORE，不可因省钱或松弛被移除；
接受中等强度步行，核心景观受天气影响可以接受。冲突时优先保证核心地点，其次
省钱、节奏、舒适。小红书允许我手动登录，OTA 仅匿名只读。不购买或预订。
```

（示例为虚构，仅演示输入结构。）

这段输入已经完整，Agent 不会再问人数、预算、体力、龙脊梯田优先级或 Browser Use 授权。
完整的 JSON 与纯文本需求模板见
[`references/intake-template.md`](references/intake-template.md)。

标 `CORE` 的地点不可被删除，除非安全、法规、闭园、天气、海拔或体力上确实去不了。

## 你会得到什么

1. 需求假设与限制条件
2. 省钱、均衡、松弛三类方案——三者没有实质差别时不强行凑数
3. 每日时间线、交通方式和换乘缓冲
4. 每个主要景点的：景点特色、推荐理由、建议时长、推荐时段、体力负荷、避坑信息
5. 参考费用、价格渠道和查询时间
6. 可行性状态、硬冲突、风险和调整建议
7. 来源链接，以及出发前必须自己再确认一遍的事项

已核实的事实和规划建议会分开呈现，不会混在一起。

## 它是怎么工作的

一句话：**把「查事实」和「做判断」拆开，让模型只做后者。**

普通 AI 攻略的问题在于两件事混在一起——模型一边回忆训练数据里的景点，一边
顺手编出"车程大约 40 分钟""门票 80 元左右"。这些数字听上去合理，但没有任何
东西为它们负责。

这个 Skill 把流程切成三层，每层职责不同：

```text
┌─ 第一层 · 事实层 ─────────────────────────────────────────┐
│  Browser Use → 小红书：玩法、路线走法、行情、排队、体感      │
│  Browser Use → 携程等 OTA：指定日期的航班与可见价格          │
│  高德 Web API   ：坐标、真实车程、公交方案                   │
│  12306 社区 MCP ：车次、余票、票价                           │
│  产出：每条数据都带来源、渠道、登录状态、查询时间             │
└───────────────────────────┬───────────────────────────────┘
                            ↓
┌─ 第二层 · 校验层（纯 Python，不含模型）──────────────────┐
│  归一化   ：把各源的杂乱格式统一成可比较的结构              │
│  可行性   ：时间窗、换乘余量、营业时间、预算、体力          │
│  完整性   ：方案是否只有交通而没讲清楚每个景点              │
│  产出：FEASIBLE / FEASIBLE_WITH_RISK / INFEASIBLE + 冲突清单 │
└───────────────────────────┬───────────────────────────────┘
                            ↓
┌─ 第三层 · 叙事层（模型）──────────────────────────────────┐
│  取舍：预算不够时砍哪个、时间冲突时挪哪个                    │
│  解释：为什么推荐这条线、这个景点值得在什么时候去            │
│  约束：只能引用第一层的数字，不能自己生成任何数字            │
└───────────────────────────────────────────────────────────┘
```

### 小红书负责线索，高德和 12306 负责核实

小红书上有大量别处拿不到的信息：某条路线怎么串、包车一天什么价、哪个入口
人少、索道排多久、"看着近其实要爬四十分钟"、枫叶几号红。这些直接决定路线
怎么排，规划全程都要用。

但它们进入方案的方式是**假设，不是结论**：

每条信息按类别决定它能走多远：

| 小红书说 | 归类 | 怎么处理 |
|---|---|---|
| "这三个点一天能串完" | 路线假设 | 当作候选顺序 → 高德算真实车程 → 可行性检查裁定 |
| "打车过去 20 分钟" | 时长线索 | 高德重新计算 → 冲突时以高德为准 |
| "包车 200 一天" | 行情信号 | 标注来源与时间，明确未核实；不会直接变成方案里的费用 |
| "北门进人少" | 体验 | 直接采纳为建议 → 无需核实，但标明出处 |
| "枫叶十一月中旬红" | 季节性 | 用于时段建议；行程贴近临界期时额外提示 |

营业时间、票价、车次、余票这四类硬事实**永远不从笔记里取**，一律以官方或
高德 / 12306 为准，笔记怎么写都一样。

这套分级不是为了丢弃社区信息，恰恰是为了能全部用上——一条记为「假设」的
信息可以参与排路线，而不会以「事实」的面目出现在你面前。

### 机票为什么必须走 OTA 网页

四类数据源里，只有机票**没有可用的接口**：地图有官方 API，铁路有社区 MCP，
唯独机票没有任何能查到指定日期真实价格的公开途径。

所以携程等 OTA 的网页是唯一的路。Browser Use 打开对应日期的航班列表，读取
页面上可见的航班号、时刻和价格，附上渠道与查询时间，再进入校验层。

这条路有两个必须知道的限制：

- **网页可见价不是最终支付价。** App 价、会员价、优惠券价可能都不同，方案里
  的机票价格只是决策参考，以你在实际渠道看到的支付页面为准。
- **机票价格变化很快。** 铁路票价基本不浮动，机票几小时就可能变。每条机票
  记录都带 `checked_at`，方案呈现前会由 `validate-flights` 检查是否超过
  2 小时；超时的价格会被标为需要重新查询，而不是默默呈现给你。

同一个检查还会核对起降时刻与标注时长是否自洽——页面读数出错时，"80 分钟"
的航班可能实际跨了 3 小时。落地早于起飞会直接判为硬冲突。

机票和高铁一样映射为**活动**而非路段：航班本身占据一段时间，去机场是另一段
由高德计算的路程，国内航班预留 120 分钟、国际 180 分钟的值机与安检余量，
一并进入可行性检查。

### 完整流程

```text
需求校验 ─→ 能力预检
   ↓
Browser Use：小红书研究（单独运行，读完即关）
   ↓
景点卡片：特色 / 理由 / 时长 / 时段 / 体力 / 避坑
   ↓
高德：校验地点坐标、聚类每日区域、计算市内真实路线
   ↓
生成省钱 / 均衡 / 松弛三类路线骨架
   ↓
12306 查高铁  ──┐
                ├─→ 归一化 ─→ 可行性检查
Browser Use 查机票 ┘              ↓
                          有硬冲突？→ 修复后重新评估（至多三轮）
                                     ↓
                              内容完整性检查
                                     ↓
                       出发前刷新入选的车次与航班
                                     ↓
                                 输出方案
```

小红书和 OTA **严格串行**——不会同时开两个 Browser Use 阶段。并行会在标签页焦点、
登录接管、失效的元素句柄和页面计时器上互相干扰。

### 所以你拿到的方案

每个数字都能追到来源和查询时间；排不通的方案在到你面前之前就被拦下并修过；
已核实的事实和模型的建议分开呈现，你能一眼看出哪些是查到的、哪些是推荐的。

## 配置高德

1. 打开[高德开放平台](https://console.amap.com/dev/key/app)，创建应用
2. 添加 **Web服务 API** 类型的 Key（类型选错是最常见的失败原因）
3. macOS 用户执行（任意目录均可）：

```bash
bash <SKILL_ROOT>/scripts/setup_amap_key.sh
```

Key 存入本机钥匙串（`service: travel-planner-mvp`，`account: amap-api-key`），
不会写入任何项目文件。旧的 `trae-travel-planner` 条目仍可读取。

检查：

```bash
python3 <SKILL_ROOT>/scripts/travel_planner.py credential-status
python3 <SKILL_ROOT>/scripts/travel_planner.py preflight
```

Linux 和 Windows 用户需自行使用系统密钥管理器，或仅在当前终端设置
`AMAP_API_KEY`。**不要把 Key 写进仓库。**

## 配置 12306 MCP

先装 `uv`：

```bash
brew install uv
```

安装运行时：

```bash
bash <SKILL_ROOT>/scripts/setup_rail_mcp.sh
```

脚本会下载固定 commit 的 `drfccv/mcp-server-12306`、应用 TLS 与日志安全补丁、
创建隔离 Python 环境，并打印标准 stdio MCP 配置。运行时装在用户数据目录，
不在 Skill 目录内，Skill 更新不会覆盖它。

默认位置：

```text
macOS: ~/Library/Application Support/travel-planner-mvp/
Linux: ${XDG_DATA_HOME:-~/.local/share}/travel-planner-mvp/
```

可用 `TRAVEL_PLANNER_DATA_DIR` 指定其他绝对路径。

### 注册到 Claude Code

把脚本输出的 `command` 与 `args` 填进 `~/.claude.json` 的 `mcpServers`：

```json
{
  "mcpServers": {
    "12306": {
      "type": "stdio",
      "command": "/opt/homebrew/bin/uv",
      "args": ["--directory", "<CHECKOUT_DIR>", "run", "mcp-server-12306"]
    }
  }
}
```

`command` 要填 `which uv` 的完整路径，不要只写 `uv`——客户端启动时的 PATH
可能不含 Homebrew 目录。保存后重启 Claude Code。

### 注册到 Codex

安装时加 `--register-codex` 即可，或在
`设置 → MCP servers → Add server → STDIO` 中手动填入脚本输出的 `command`
和 `args`。之后用 `codex mcp list` 确认并重启。

### 确认成功

看到 `query-tickets`、`query-ticket-price`、`search-stations` 等工具即为成功。

这个 MCP 直接查询 12306 网站使用的公开接口，**不是官方开发者 API**，也不登录
你的账户、不执行购票。它可能受接口变更、查询窗口和平台限制影响。

## 环境检查

```bash
python3 <SKILL_ROOT>/scripts/travel_planner.py doctor --live
```

`doctor` 检查 Python、高德、12306 运行环境、MCP 注册和 Browser Use 状态，并通过
`actions` 返回还缺哪几步。客户端默认自动识别，也可用 `--client` 显式指定
`auto`、`codex`、`claude-code` 或 `generic`。

缺少可选能力时会安全降级：没有 12306 就不给出实时铁路声明；没有 Browser Use 就需要
你提供标准化 JSON，或标记该数据源不可用；没有高德则不宣称任何已核实的地点。

## Browser Use 授权

启动 Browser Use 之前，Agent 会明确说明要访问哪些域名，并请求一次只读授权。

**小红书**：优先匿名访问；搜索页要求登录时由你亲自扫码或完成验证，Agent 不输入
密码和验证码；只读取少量相关笔记的页面可见内容。

**OTA**：在小红书研究和路线骨架完成后才启动；默认查询匿名网页公开价；只有你明确
需要会员价时才请求手动登录。

网页匿名价、App 价、会员价和优惠券价可能都不一样，**最终以你在实际渠道看到的
支付页面为准**。

## 命令参考

大多数时候你不需要手敲命令——Agent 会自己调用。你可能用到的只有这几个：

```bash
python3 <SKILL_ROOT>/scripts/travel_planner.py <command>
```

| 命令 | 作用 |
|---|---|
| `doctor` | 汇总检查 Python、高德、12306 MCP 与 Browser Use 能力 |
| `credential-status` | 检查高德 Key 是否已配置 |
| `preflight` | 发送一次真实高德预检请求 |
| `search-places` | 查询并标准化高德 POI |

以下由 Agent 在规划过程中自动调用，一般不需要你手动执行：
`validate-request`、`amap-snapshot`、`normalize-rail`、`compile-research`、
`evaluate`、`validate-plan`。

所有命令都返回结构化 JSON。完整说明见
[`references/script-tools.md`](references/script-tools.md)。

## 数据与隐私

仓库里不保存也不应提交：

- 高德 API Key
- 小红书或 OTA 的密码、验证码与 Cookie
- 浏览器 Profile 或 Storage State
- 身份证件和支付信息

旅行日期、预算、出发地、无障碍需求和浏览记录同样可能构成个人隐私。真实运行产物
应写入被忽略的临时目录。

## 故障处理

**高德返回鉴权失败** — 确认 Key 类型是 `Web服务 API`（不是其他类型）、Key 未删除
或过期、IP 白名单与数字签名配置正确。

**12306 查不了远期日期** — 12306 只开放有限的预售窗口，远期日期拿不到实时余票，
必须临近出发再刷新。

**小红书要求登录** — 由你手动登录。持续出现验证码时应停止该数据源，降级到公开
信息，而不是反复重试。

**OTA 价格与 App 不一致** — 属正常现象，见上文「机票为什么必须走 OTA 网页」。

**Browser Use 超时** — 确认小红书和 OTA 是串行执行。某个阶段连续两次没有新数据
时应停止并返回部分结果，而不是无限等待。

## 第三方与许可

- 本 Skill 源码采用 MIT License
- 社区 12306 MCP 由安装脚本在你本地获取，不包含在发布包中
- 高德、12306、小红书、OTA 和各 Agent 客户端分别受其平台条款约束
- MIT License **不覆盖**第三方数据权利、账号规则、隐私要求或商业使用限制

详见 [`SECURITY.md`](SECURITY.md) 与
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。

深入了解：[工作流](references/workflow.md) ·
[数据契约](references/data-contracts.md) ·
[客户端兼容性](references/client-compatibility.md) ·
[12306 MCP](references/rail-mcp.md) ·
[Browser Use 契约](references/browser-use.md)

想参与开发或自己发版，见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。
