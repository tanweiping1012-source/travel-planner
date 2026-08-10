# Travel Planner MVP

一个采用 `SKILL.md + references + scripts` 结构的只读旅行规划
Agent Skill。它先从公开旅行内容中发现目的地与玩法，再使用地图和交通数据
验证路线，最后生成经过确定性可行性检查的旅行方案。

该 Skill 最初在 TRAE 中开发并完成端到端测试，但核心脚本、数据契约和
12306 stdio MCP 不依赖 TRAE。Claude Code、OpenAI Codex 以及其他支持
Agent Skills、Shell 和 MCP 的客户端也可以使用；浏览器研究需要另行配置
满足本文契约的浏览器自动化工具。

本 Skill 只提供信息查询与规划参考，不执行购票、预订、支付、候补、改签、退票、点赞、收藏、关注、评论或发布。

## 能力概览

| 能力 | 数据来源 | 作用 |
|---|---|---|
| 目的地与玩法发现 | 交互式浏览器自动化 | 从小红书页面提取景点、特色、建议时段、公共交通和避坑信息 |
| 地点与市内路线 | 高德 Web API | 校验 POI、坐标、步行、公交和驾车路线 |
| 高铁查询 | 社区 12306 MCP | 查询车次、余票、票价、经停站和中转方案 |
| 机票查询 | 交互式浏览器自动化 | 查询指定日期的 OTA 网页可见航班、时间与参考价格 |
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

可以。建议在调用 Skill 时直接填写下面的完整表单。Agent 会先运行
`validate-request`：

- 表单完整且无冲突：直接开始研究，不再重复提问。
- 有缺失或冲突：一次性汇总询问，不拆成多轮。

### 完整需求表单

```json
{
  "origin": "广州",
  "destination": "桂林与阳朔",
  "start_date": "2027-04-10",
  "end_date": "2027-04-13",
  "travelers": 2,
  "budget_cny": 3500,
  "budget_scope": "PER_PERSON",
  "style": "balanced",
  "must_visit": [
    {
      "name": "龙脊梯田",
      "priority": "CORE"
    }
  ],
  "excluded_places": [],
  "mobility": {
    "level": "MODERATE",
    "max_walking_km_per_day": 8,
    "accepts_high_altitude": true,
    "accessibility_needs": []
  },
  "tradeoff_priority": [
    "CORE_PLACES",
    "COST",
    "PACE",
    "COMFORT"
  ],
  "risk_tolerance": {
    "accepts_weather_dependent_core": true
  },
  "browser_approval": {
    "xiaohongshu": "ALLOW_MANUAL_LOGIN",
    "ota": "ANONYMOUS_ONLY"
  },
  "transport_preferences": {
    "accepts_early_departure": true,
    "accepts_overnight_transport": false,
    "accepts_transfers": true
  },
  "latest_return_time": null
}
```

字段取值：

| 字段 | 可选值 | 含义 |
|---|---|---|
| `budget_scope` | `PER_PERSON` / `PARTY_TOTAL` | 人均预算或全体总预算 |
| `must_visit[].priority` | `CORE` / `IMPORTANT` / `OPTIONAL` | 核心点不可被普通路线优化移除 |
| `mobility.level` | `LOW` / `MODERATE` / `HIGH` | 低、中、高体力强度 |
| `tradeoff_priority` | `CORE_PLACES`、`COST`、`PACE`、`COMFORT` | 从高到低排列冲突时的取舍顺序 |
| `browser_approval.*` | `ANONYMOUS_ONLY` / `ALLOW_MANUAL_LOGIN` / `DENY` | 匿名只读、允许用户手动登录、禁止访问 |

`CORE` 不代表可以突破安全或法律边界。若核心地点关闭、未开放、超出
体力上限或无法合法抵达，Agent 仍会暂停并说明冲突。

### 纯文本模板

不想填写 JSON 时，可直接粘贴并填写：

```text
使用 travel-planner-mvp：
出发地：
核心目的地区域：
开始日期：
结束日期：
人数：
预算：人均 / 总计，人民币
旅行风格：
核心必去（不可删除）：
重要但可调整：
明确不去：
体力等级：低 / 中 / 高
每日最多步行：
是否接受 4000 米以上高海拔：
无障碍、老人、儿童或健康限制：
冲突时优先级：核心地点 / 省钱 / 松弛 / 舒适
是否接受核心景观受天气影响：
是否接受早班、夜班和中转：
每天最晚返回时间：
小红书授权：匿名只读 / 允许我手动登录 / 禁止
OTA 授权：匿名只读 / 允许我手动登录 / 禁止
其他住宿、行李或饮食偏好：
```

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
  `python scripts/travel_planner.py --help`。

详见
[`references/client-compatibility.md`](references/client-compatibility.md)。

## 安装 Skill

仓库根目录本身就是 Skill 目录。克隆后，将其复制或软链接到客户端的
Skill 搜索路径。

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

项目级：

```text
<workspace>/.agents/skills/travel-planner-mvp/
```

用户级：

```text
~/.agents/skills/travel-planner-mvp/
```

参考：[OpenAI Codex Agent Skills 官方文档](https://developers.openai.com/codex/skills)。

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
4. macOS 用户在 Skill 目录执行：

```bash
./scripts/setup_amap_key.sh
```

脚本会把 Key 存入：

```text
service: trae-travel-planner
account: amap-api-key
```

Key 不会写入项目文件。随后检查：

```bash
python scripts/travel_planner.py credential-status
python scripts/travel_planner.py preflight
```

## 配置 12306 MCP

安装 `uv`：

```bash
brew install uv
```

运行：

```bash
./scripts/setup_rail_mcp.sh
```

该脚本会：

- 下载固定 commit 的 `drfccv/mcp-server-12306`
- 安装到本地 `vendor/`
- 应用 TLS 与日志安全补丁
- 创建隔离 Python 环境
- 输出 TRAE MCP JSON 配置

将脚本输出的标准 stdio MCP 配置导入客户端。TRAE 中粘贴到：

```text
TRAE 设置 → MCP → 手动添加
```

看到 `query-tickets`、`query-ticket-price`、`search-stations` 等工具并显示绿色连接状态，即表示成功。

这个 MCP 直接查询 12306 网站使用的公开接口，不登录用户账户，也不执行购票。它不是官方开发者 API，可能受接口变更、查询窗口和平台限制影响。

Claude Code、Codex 和其他 MCP 客户端使用各自的 MCP 配置入口，但应保留
相同的 `command` 与 `args`。

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
使用 travel-planner-mvp。2027 年 4 月 10 日至 13 日，广州出发去桂林和
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
python scripts/travel_planner.py <command>
```

| 命令 | 作用 |
|---|---|
| `validate-request` | 校验需求完整性、字段格式和显式冲突 |
| `credential-status` | 检查高德 Key 是否已配置 |
| `preflight` | 发送一次真实高德预检请求 |
| `search-places` | 查询并标准化高德 POI |
| `amap-snapshot` | 获取地点、路线和周边 POI 快照 |
| `compile-research` | 将结构化小红书研究合并为景点卡片 |
| `evaluate` | 运行时间、换乘、预算、营业时间等可行性检查 |
| `validate-plan` | 检查最终方案是否包含完整景点内容与来源 |

示例：

```bash
python scripts/travel_planner.py \
  validate-request \
  --input examples/trip_request.json

python scripts/travel_planner.py \
  compile-research \
  --input examples/social_research.json \
  --output /tmp/destination_brief.json

python scripts/travel_planner.py \
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
./scripts/prepare_release.sh
```

输出目录：

```text
dist/travel-planner-mvp/
```

发布包只包含明确允许公开的源码、文档、测试、示例和补丁。发布前运行：

```bash
cd dist/travel-planner-mvp
./scripts/audit_release.sh .
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

## 测试

```bash
python -m unittest discover -s tests -v
```

当前测试覆盖：

- 完整需求直接进入研究、缺失字段一次性汇总、需求冲突识别
- 高德地点与路线标准化
- 密钥不出现在错误信息中
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
