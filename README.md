# Travel Planner MVP

[![CI](https://github.com/tanweiping1012-source/travel-planner/actions/workflows/ci.yml/badge.svg)](https://github.com/tanweiping1012-source/travel-planner/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%20--%203.14-blue.svg)](pyproject.toml)

**让 AI 用真实数据规划旅行，而不是靠搜索来的二手攻略。**

行程里的每一个数字——距离、通勤时长、余票、票价——都来自工具调用并带来源和时间戳。
模型只负责取舍和解释，不生成任何数字。生成的行程会先过一遍确定性可行性检查
（时间窗、换乘余量、营业时间、预算），排不通的方案不会送到你面前。

一个采用 `SKILL.md + references + scripts` 结构的旅行规划
Agent Skill。它先从公开旅行内容中发现目的地与玩法，再使用地图和交通数据
验证路线，最后生成经过确定性可行性检查的旅行方案。

该 Skill 最初在 TRAE 中开发并完成端到端测试，但核心脚本、数据契约和
12306 stdio MCP 不依赖 TRAE。Claude Code、OpenAI Codex 以及其他支持
Agent Skills、Shell 和 MCP 的客户端也可以使用；浏览器研究需要另行配置
满足本文契约的浏览器自动化工具。

本 Skill 只提供信息查询与规划参考，不执行购票、预订、支付、候补、改签、退票、点赞、收藏、关注、评论或发布。

## 五分钟上手

### Claude Code

```bash
git clone https://github.com/tanweiping1012-source/travel-planner.git
ln -s "$(pwd)/travel-planner" ~/.claude/skills/travel-planner-mvp
bash ~/.claude/skills/travel-planner-mvp/scripts/setup_amap_key.sh
bash ~/.claude/skills/travel-planner-mvp/scripts/setup_rail_mcp.sh
```

用软链接而非拷贝，仓库始终是唯一事实源。然后把 12306 加进 `~/.claude.json`
的 `mcpServers`（setup 脚本会打印所需路径），重启客户端，再运行：

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

记录安装器返回的绝对路径，然后：

```bash
bash <SKILL_ROOT>/scripts/setup_amap_key.sh
bash <SKILL_ROOT>/scripts/setup_rail_mcp.sh --register-codex
```

重启 Codex 后运行 `doctor --live` 检查。

每位用户配置自己的高德 Key；Key 存入本机钥匙串，不随仓库或 Skill 分发。

## 能力概览

| 能力 | 数据来源 | 作用 |
|---|---|---|
| 目的地与玩法发现 | Browser Use | 从小红书页面提取景点、特色、建议时段、公共交通和避坑信息 |
| 地点与市内路线 | 高德 Web API | 校验 POI、坐标、步行、公交和驾车路线 |
| 高铁查询 | 社区 12306 MCP | 查询车次、余票、票价、经停站和中转方案 |
| 机票查询 | Browser Use | 查询指定日期的 OTA 网页可见航班、时间与参考价格 |
| 可行性检查 | 本地 Python 规则引擎 | 检查时间冲突、换乘缓冲、营业时间、预算和体力负荷 |
| 内容完整性检查 | 本地 Python 规则引擎 | 拒绝只有交通、缺少景点特色与游玩说明的方案 |

## 工作原则

- 小红书与 OTA 严格串行浏览，避免标签页、焦点、登录态和超时相互影响。
- 小红书只用于旅行体验和目的地发现，不作为路线、营业时间或票价的权威来源。
- 高德用于校验地点与地面交通。
- 12306 MCP 是社区只读连接器，不是铁路官方开放 API。
- OTA 查询结果来自网页版，不保证与原生 App、会员价或最终支付价一致。
- 所有动态信息必须保留来源、渠道、登录状态和查询时间。

## 工作流

```text
收集旅行需求
  ↓
校验完整需求表单
  ↓
仅在缺失字段或硬冲突存在时一次性澄清
  ↓
预检高德与 12306 MCP
  ↓
请求浏览器只读授权
  ↓
小红书研究（单独运行）
  ↓
生成景点卡片与 DestinationBrief
  ↓
高德校验景点、聚类每日区域、计算市内路线
  ↓
形成省钱 / 均衡 / 松弛路线骨架
  ↓
查询高铁与机票，筛除无法衔接的便宜方案
  ↓
运行可行性检查并修复冲突
  ↓
运行内容完整性检查
  ↓
刷新入选的动态交通信息
  ↓
输出最终旅行方案
```

## 开始前填写

直接用自然语言描述即可。信息完整时，Agent 会运行 `validate-request` 后
直接研究；有缺失或冲突时，会一次性汇总询问。

最短示例：

```text
使用 $travel-planner-mvp。2027 年 4 月 10 日至 13 日，广州出发去桂林和
阳朔，2 人，人均预算 3500 元，节奏均衡。龙脊梯田为 CORE；接受中等
强度步行。小红书允许我手动登录，OTA 仅匿名只读。不购买或预订。
```

完整 JSON 与纯文本需求模板见
[`references/intake-template.md`](references/intake-template.md)。

## 输出

最终输出至少包含：

1. 需求假设与限制条件。
2. 省钱、均衡、松弛三类方案；方案相同时不强行凑数。
3. 每日时间线、交通方式和换乘缓冲。
4. 每个主要景点的：
   - 景点特色
   - 推荐理由
   - 建议游玩时长
   - 推荐时段
   - 体力或海拔负荷
   - 交通、排队和避坑信息
5. 参考费用、价格渠道和查询时间。
6. 可行性状态、硬冲突、风险和调整建议。
7. 来源链接及出发前必须再次确认的事项。

## 环境要求

### 核心能力

- Python 3.9+
- 网络连接
- 能读取 `SKILL.md` 并执行 Shell/Python 的 Agent 客户端；也可只使用 CLI

### 高德能力

- 高德开放平台账号
- `Web服务 API` 类型 Key
- macOS 钥匙串，或受控环境中的 `AMAP_API_KEY`

### 高铁能力

- `uv`
- Python 3.10+；`uv` 可自动创建隔离运行时
- 支持本地 stdio MCP 的 Agent 客户端

### 完整浏览能力

- 可操作真实网页的浏览器工具或 Playwright 类 MCP
- 支持观察页面、标签页管理、点击、输入、滚动、等待和结构化提取
- 需要登录或验证码时，能够暂停并把控制权交给用户

### 平台说明

随附的安全存储脚本默认使用 macOS 钥匙串。Linux 和 Windows 用户需要自行使用系统密钥管理器，或者仅在当前终端设置 `AMAP_API_KEY`，禁止将 Key 写入仓库。

## 客户端兼容性

| 客户端 | Skill 发现 | Python 脚本 | 12306 MCP | 浏览器研究 | 当前状态 |
|---|---:|---:|---:|---:|---|
| TRAE | `.trae/skills/` | 支持 | 支持 | 内置 Browser Use | 完整实测 |
| Claude Code | `.claude/skills/` | 支持 | 支持 | 需配置浏览器工具/MCP | 结构兼容，未做端到端实测 |
| OpenAI Codex | `.agents/skills/` | 支持 | 支持 | 需配置浏览器工具/MCP | 结构兼容，未做端到端实测 |
| 其他 Agent | 取决于客户端 | 需要 Shell | 需要 stdio MCP | 需要浏览器适配器 | 按能力降级 |

兼容性分为三档：

- **完整模式**：Skill + Shell + stdio MCP + 交互式浏览器 + 用户登录接管。
- **无浏览器模式**：保留需求校验、高德、高铁、可行性和方案校验；
  小红书研究和机票需要用户提供标准化 JSON，或标记为不可用。
- **纯脚本模式**：不使用任何 Agent，直接运行
  `python3 scripts/travel_planner.py --help`。

详见
[`references/client-compatibility.md`](references/client-compatibility.md)。

## 安装 Skill

仓库根目录本身就是 Skill 目录。优先使用客户端的 Skill 安装器；手动
复制或软链接只作为备选。

### TRAE

将仓库放入项目：

```text
<workspace>/.trae/skills/travel-planner-mvp/
```

重启或重新打开 TRAE 项目，使 Skill 被发现。

### Claude Code

项目级：

```text
<workspace>/.claude/skills/travel-planner-mvp/
```

用户级：

```text
~/.claude/skills/travel-planner-mvp/
```

参考：[Claude Code Skills 官方文档](https://code.claude.com/docs/en/skills)。

### OpenAI Codex

推荐直接在 Codex 中输入：

```text
使用 $skill-installer 安装 GitHub 仓库
https://github.com/tanweiping1012-source/travel-planner
根目录中的 Skill，名称为 travel-planner-mvp。
```

安装器可能根据当前 Codex 版本和 `CODEX_HOME` 使用不同目录，因此后续
命令以安装器返回的绝对路径为准。手动安装时，官方发现路径包括：

项目级：

```text
<workspace>/.agents/skills/travel-planner-mvp/
```

用户级：

```text
~/.agents/skills/travel-planner-mvp/
```

安装后若未出现，重启 Codex。参考：
[OpenAI Codex Agent Skills 官方文档](https://learn.chatgpt.com/docs/build-skills)。

### 其他客户端

如果客户端支持开放 `SKILL.md` 结构，使用其官方 Skill 目录。否则可以：

1. 将 `SKILL.md` 加载为项目规则或复用提示词。
2. 允许 Agent 读取 `references/`。
3. 允许 Agent 执行 `scripts/travel_planner.py`。
4. 单独配置 12306 stdio MCP 和浏览器适配器。

## 配置高德

1. 打开[高德开放平台](https://console.amap.com/dev/key/app)。
2. 创建应用。
3. 添加 `Web服务 API` 类型 Key。
4. macOS 用户执行（可在任意目录运行）：

```bash
bash <SKILL_ROOT>/scripts/setup_amap_key.sh
```

脚本会把 Key 存入：

```text
service: travel-planner-mvp
account: amap-api-key
```

旧版 `trae-travel-planner` 钥匙串条目仍可读取，但新配置会写入中性服务名。
Key 不会写入项目文件。随后检查：

```bash
python3 <SKILL_ROOT>/scripts/travel_planner.py credential-status
python3 <SKILL_ROOT>/scripts/travel_planner.py preflight
```

新用户在自己的电脑上安装 Skill 时，不会获得仓库作者或其他用户的 Key。
程序只在运行高德请求时从当前操作系统用户的钥匙串或当前进程环境读取 Key；
`credential-status` 和 `doctor` 只返回是否配置及来源类型，不返回 Key 内容。
同一台 Mac、同一系统登录账户下，获准访问该钥匙串条目的进程仍可能使用它，
这是 macOS 钥匙串的本机权限边界。

## 配置 12306 MCP

安装 `uv`：

```bash
brew install uv
```

安装并自动注册到 Codex：

```bash
bash <SKILL_ROOT>/scripts/setup_rail_mcp.sh --register-codex
```

该脚本会：

- 下载固定 commit 的 `drfccv/mcp-server-12306`
- 安装到用户数据目录，而不是 Skill 目录
- 应用 TLS 与日志安全补丁
- 创建隔离 Python 环境
- 输出标准 stdio MCP 配置
- 在使用 `--register-codex` 时调用 `codex mcp add`

默认数据目录：

```text
macOS: ~/Library/Application Support/travel-planner-mvp/
Linux: ${XDG_DATA_HOME:-~/.local/share}/travel-planner-mvp/
```

可通过 `TRAVEL_PLANNER_DATA_DIR` 指定其他绝对路径。Skill 更新或重装不会
覆盖该运行环境。

Codex 注册后检查并重启：

```bash
codex mcp list
```

也可以在 `Codex 设置 → MCP servers → Add server → STDIO` 中使用脚本
输出的 `command` 和 `args` 手动添加。

其他客户端可导入脚本输出的标准 stdio MCP 配置。TRAE 中粘贴到：

```text
TRAE 设置 → MCP → 手动添加
```

看到 `query-tickets`、`query-ticket-price`、`search-stations` 等工具并显示绿色连接状态，即表示成功。

这个 MCP 直接查询 12306 网站使用的公开接口，不登录用户账户，也不执行购票。它不是官方开发者 API，可能受接口变更、查询窗口和平台限制影响。

Claude Code、Codex 和其他 MCP 客户端使用各自的 MCP 配置入口，但应保留
相同的 `command` 与 `args`。

## 统一环境检查

```bash
python3 <SKILL_ROOT>/scripts/travel_planner.py doctor \
  --live --client codex --browser-status unknown
```

`doctor` 检查 Python、高德、12306 运行环境、Codex MCP 注册和浏览器状态，
并通过 `actions` 返回缺失步骤。CLI 无法自行发现 Agent 浏览器工具，因此
手工执行时使用 `unknown`；Agent 调用时应传入实际的 `available` 或
`unavailable`。

## 浏览器自动化授权

规划过程中，Agent 会明确说明需要访问的域名并请求一次只读授权。

### 小红书

- 优先匿名访问。
- 搜索页要求登录时，由用户亲自扫码或完成验证。
- Agent 不输入密码和短信验证码。
- 只读取少量相关笔记的页面可见内容。
- 不点赞、收藏、关注、评论或发布。

### OTA

- 在小红书研究与路线骨架完成后才启动。
- 默认查询匿名网页公开价。
- 只有用户明确需要会员价时才请求手动登录。
- 不点击购买或提交订单。

## 使用示例

以下内容是虚构示例，仅用于演示输入结构，不对应任何真实用户行程。

在 Agent 对话中输入：

```text
使用 $travel-planner-mvp。2027 年 4 月 10 日至 13 日，广州出发去桂林和
阳朔，2 人，人均预算 3500 元。龙脊梯田是 CORE，不可因省钱或松弛被
移除；接受中等强度步行，核心景观受天气影响可以接受。冲突时优先保证
核心地点，其次省钱、节奏、
舒适。小红书允许需要时由我手动登录，OTA 仅匿名只读。不进行购买或预订。
```

该输入完整时，Agent 应直接运行需求校验和数据源预检，不重复询问人数、
预算、体力、龙脊梯田优先级或浏览器授权。

## CLI 工具

统一入口：

```bash
python3 <SKILL_ROOT>/scripts/travel_planner.py <command>
```

| 命令 | 作用 |
|---|---|
| `validate-request` | 校验需求完整性、字段格式和显式冲突 |
| `credential-status` | 检查高德 Key 是否已配置 |
| `preflight` | 发送一次真实高德预检请求 |
| `doctor` | 汇总检查 Python、高德、12306 MCP 与浏览器能力 |
| `search-places` | 查询并标准化高德 POI |
| `amap-snapshot` | 获取地点、路线和周边 POI 快照 |
| `normalize-rail` | 归一化 12306 余票数据（`有`/`无`/数字混用），并筛选候选车次 |
| `compile-research` | 将结构化小红书研究合并为景点卡片 |
| `evaluate` | 运行时间、换乘、预算、营业时间等可行性检查 |
| `validate-plan` | 检查最终方案是否包含完整景点内容与来源 |

示例：

```bash
python3 <SKILL_ROOT>/scripts/travel_planner.py \
  validate-request \
  --input examples/trip_request.json

python3 <SKILL_ROOT>/scripts/travel_planner.py \
  compile-research \
  --input examples/social_research.json \
  --output /tmp/destination_brief.json

python3 <SKILL_ROOT>/scripts/travel_planner.py \
  normalize-rail \
  --input examples/rail_query.json \
  --select --seat-class second_class --limit 5

python3 <SKILL_ROOT>/scripts/travel_planner.py \
  validate-plan \
  --input examples/final_plan.json
```

## 数据与隐私

Skill 不会在仓库中保存：

- 高德 API Key
- 小红书或 OTA 密码、验证码与 Cookie
- 浏览器 Profile 或 Storage State
- 用户身份证件和支付信息

旅行日期、预算、出发地、无障碍需求和浏览记录也可能构成个人隐私。真实运行产物应写入被忽略的临时目录，不得提交 Git。

## 安全发布到 GitHub

不要直接上传本地工作目录。本地目录可能包含 `vendor/`、虚拟环境和运行产物。

生成白名单发布包：

```bash
bash scripts/prepare_release.sh
```

输出目录：

```text
dist/travel-planner-mvp/
```

发布包只包含明确允许公开的源码、文档、测试、示例和补丁。发布前运行：

```bash
cd dist/travel-planner-mvp
bash scripts/audit_release.sh .
git status --ignored
git ls-files
```

审计会拒绝：

- `vendor/`、`.venv/`、嵌套 `.git/`
- `.env`、私钥和证书
- Cookie、Session、HAR 和浏览器状态文件
- 用户绝对路径
- 高置信密钥格式
- 真实样式的小红书笔记 ID

若本机安装了 `gitleaks`，审计脚本还会运行额外的密钥扫描。

仓库还包含 GitHub Actions：在每次 push 和 pull request 时测试 Python
3.9–3.14、校验 `SKILL.md` 与 `agents/openai.yaml`、运行 ShellCheck、生成并
审计发布包，并由 Gitleaks 扫描完整 Git 历史。个人仓库无需额外的
Gitleaks License；组织仓库需按该 Action 的要求配置 License。

## 测试

```bash
python3 scripts/validate_skill.py .
python3 -m unittest discover -s tests -v
```

当前测试覆盖：

- 完整需求直接进入研究、缺失字段一次性汇总、需求冲突识别
- 高德地点与路线标准化
- 密钥不出现在错误信息中
- 新旧 macOS 钥匙串服务名兼容
- `doctor` 能识别缺失和就绪的本地能力
- 时间、换乘、预算和营业时间检查
- 小红书研究合并为景点卡片
- 纯交通方案拒绝
- 缺少景点间路线拒绝

## 安全边界

以下行为明确禁止：

- 购买、预订、支付、候补、改签和退票
- 绕过验证码、登录墙或平台风控
- 导出 Cookie 或浏览器会话
- 批量抓取小红书笔记、评论、图片或视频
- 修改外部账户状态
- 把社区 12306 MCP 描述为官方接口
- 把网页显示价格描述为最终支付价

## 第三方与许可

- 本 Skill 源码采用 MIT License。
- 社区 12306 MCP 由安装脚本在用户本地获取，不包含在发布包中。
- 高德、12306、小红书、OTA 和 TRAE 分别受各自平台条款约束。
- MIT License 不覆盖第三方数据权利、账号规则、隐私要求或商业使用限制。

详见：

- [`SECURITY.md`](SECURITY.md)
- [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)
- [`references/workflow.md`](references/workflow.md)
- [`references/data-contracts.md`](references/data-contracts.md)
- [`references/client-compatibility.md`](references/client-compatibility.md)

## 故障处理

### 高德返回鉴权失败

- 确认 Key 类型为 `Web服务 API`
- 确认 Key 未删除或过期
- 检查 IP 白名单或数字签名配置

### 12306 查询不了远期日期

12306 只开放有限的查询/预售窗口。远期日期不能提供实时余票，必须临近出发时刷新。

### 小红书要求登录

由用户手动登录。若持续出现验证码，停止该数据源并降级到公开信息。

### OTA 价格与 App 不一致

网页匿名价、App 价、会员价和优惠券价可能不同。最终以用户在实际渠道看到的支付页面为准。

### 浏览器自动化超时

确保小红书和 OTA 串行执行。一个阶段连续两次没有新数据时应停止并返回部分结果，而不是无限等待或启动并发恢复任务。
