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

## 它不会做什么

这个 Skill 是**只读**的。装上之后它**不能**：

- 购买、预订、支付、候补、改签、退票——它没有下单能力
- 输入你的密码、短信验证码、身份证件或支付信息——登录和验证码永远交还给你
- 导出你的 Cookie、Token 或浏览器会话
- 点赞、收藏、关注、评论、发布，或以任何方式改动你的账号
- 绕过验证码、登录墙或平台风控
- 批量抓取小红书笔记、评论、图片或视频

它只看，不动。需要登录时它会停下来把控制权交给你。

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
`references/` 并执行 `scripts/travel_planner.py`，再单独配置 12306 MCP 和浏览器。

每位用户配置自己的高德 Key；Key 存入本机钥匙串，不随仓库或 Skill 分发。

## 能力概览

| 能力 | 数据来源 | 作用 |
|---|---|---|
| 目的地与玩法发现 | 浏览器 | 从小红书页面提取景点、特色、建议时段、公共交通和避坑信息 |
| 地点与市内路线 | 高德 Web API | 校验 POI、坐标、步行、公交和驾车路线 |
| 高铁查询 | 社区 12306 MCP | 车次、余票、票价、经停站和中转方案；余票词表经归一化后可比较排序 |
| 机票查询 | 浏览器 | 查询指定日期的 OTA 网页可见航班、时间与参考价格 |
| 可行性检查 | 本地 Python | 时间冲突、换乘缓冲、营业时间、预算和体力负荷 |
| 内容完整性检查 | 本地 Python | 拒绝只有交通、缺少景点特色与游玩说明的方案 |

数据源分工是有意为之：**小红书只用于发现和体验，不作为路线、营业时间或票价的
权威来源**；这些一律由高德和 12306 校验。

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

这段输入已经完整，Agent 不会再问人数、预算、体力、龙脊梯田优先级或浏览器授权。
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

## 规划流程

```text
需求校验 → 能力预检 → 小红书研究（单独运行）→ 景点卡片
    → 高德校验地点与市内路线 → 生成三类路线骨架
    → 查询高铁与机票 → 可行性检查与冲突修复
    → 内容完整性检查 → 出发前刷新动态交通信息 → 输出方案
```

小红书和 OTA 严格串行访问，一个阶段结束后才开始下一个。

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

`doctor` 检查 Python、高德、12306 运行环境、MCP 注册和浏览器状态，并通过
`actions` 返回还缺哪几步。客户端默认自动识别，也可用 `--client` 显式指定
`auto`、`codex`、`claude-code` 或 `generic`。

缺少可选能力时会安全降级：没有 12306 就不给出实时铁路声明；没有浏览器就需要
你提供标准化 JSON，或标记该数据源不可用；没有高德则不宣称任何已核实的地点。

## 浏览器授权

规划开始前，Agent 会明确说明要访问哪些域名，并请求一次只读授权。

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
| `doctor` | 汇总检查 Python、高德、12306 MCP 与浏览器能力 |
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

**OTA 价格与 App 不一致** — 属正常现象，见上文「浏览器授权」。

**浏览器自动化超时** — 确认小红书和 OTA 是串行执行。某个阶段连续两次没有新数据
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
[浏览器契约](references/browser-use.md)

想参与开发或自己发版，见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。
