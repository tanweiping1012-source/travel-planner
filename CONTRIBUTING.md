# 参与开发

面向维护者和贡献者。只想使用这个 Skill 的话，看 [`README.md`](README.md) 就够了。

## 开发环境

```bash
git clone https://github.com/tanweiping1012-source/travel-planner.git
cd travel-planner
```

不需要虚拟环境，也没有运行时依赖——所有代码只用 Python 标准库。CI 覆盖
Python 3.9 到 3.14，所以新代码必须兼容 3.9（不要用 `match`、`X | Y` 运行时
注解等更高版本语法）。

## 运行测试

```bash
python3 scripts/validate_skill.py .
python3 -m unittest discover -s tests -v
```

再跑一遍 CI 里的示例校验：

```bash
python3 scripts/travel_planner.py validate-request --input examples/trip_request.json
python3 scripts/travel_planner.py evaluate --input examples/itinerary.json
python3 scripts/travel_planner.py normalize-rail --input examples/rail_query.json \
  --select --seat-class second_class
python3 scripts/travel_planner.py validate-flights --input examples/final_plan.json \
  --skip-freshness
python3 scripts/travel_planner.py validate-lodging --input examples/final_plan.json \
  --skip-freshness
python3 scripts/travel_planner.py validate-plan --input examples/final_plan.json
```

本机通常只装了一个 Python 版本，本地全绿**不等于**没问题。有些缺陷只在部分
解释器上显现——例如 argparse 从 3.11 起才拒绝重复的子命令，3.9 和 3.10 是
静默覆盖。推送后务必看一眼 CI 的多版本矩阵。

测试当前覆盖：

- 需求校验：完整需求直接放行、缺失字段一次性汇总、冲突识别
- 高德地点与路线标准化，且密钥不出现在任何错误信息中
- 新旧 macOS 钥匙串服务名兼容
- `doctor` 识别本地能力，区分 Claude Code 与 Codex 的注册状态，且报告中
  不回显客户端配置里的无关账号信息
- 可行性检查：时间、换乘、预算、营业时间
- 时区换算：同一时刻用 `Z` 与 `+08:00` 书写结论一致；未声明时区的 UTC
  时间戳跳过营业时间检查并告警，而非误报冲突
- 跨天分隔不被误判为缺少通勤数据，但显式跨天的夜班车照常校验
- 评分分档：硬冲突方案不会高于软风险方案
- 12306 余票词表（`有` / `无` / 数字）归一化与排序
- 车次映射为活动而非路段，且不编造 `query-tickets` 未返回的票价
- 内容完整性：纯交通方案拒绝、缺少景点间路线拒绝
- 机票记录：落地早于起飞判硬冲突；标注时长与起降时刻不符告警；价格过期仅在
  传入时钟时判定，校验存档行程不会因时间流逝而失败；未保证价必须标注
- 机票映射为活动并携带值机余量（国内 120 / 国际 180 分钟）
- CLI 结构：没有子命令被注册两次。断言的是 `add_parser` 的调用记录，而非
  解析器的结果——结果存在 dict 里，无法表达重复键，覆盖从外部不可见
- CLI 接线：解析器接受的每个选项，其 handler 必须真的读取 `args.<dest>`。
  匹配的是 `args.now` 而不是裸的 `now`，否则 `datetime.now` 会让断言平凡成立
- 时间守卫：`evaluate` 与 `validate-flights` 收到不带时区的 `now` 时报出
  可执行的 `ValueError`，而不是从减法内部抛出的 `TypeError`；`Z` 后缀在
  3.9 上也能解析（`fromisoformat` 到 3.11 才原生支持）

- 地理匹配：查询词不在返回地址里、或城市查询落到村庄级别，均判为低置信并
  拒绝返回坐标；场所查询在村庄级别是正常的，不受影响

- 来源受阻：声明了 `unavailable_sources` 时，「完全没有景点」降级为
  `INCOMPLETE_EVIDENCE`（退出码 3）；空壳景点、缺路线等一律不赦免；声明本身
  必须带 provider，空数组和纯字符串都不算
- 住宿记录：卡片价按晚数与房间数换算成总价，`TOTAL_STAY` 口径不被重复相乘；
  未记录登录态、或登录态是匿名，一律判硬冲突；不同登录态或会员等级的报价混在
  一起会告警不可比较；`validate-plan` 内部会跑 `validate-lodging`，坏的住宿
  记录即使方案里没别的问题也会让整份方案判 `INVALID`

### 先试一次，再说做不到

这个 Skill 里几乎每一个真实缺陷都是**实跑**发现的，不是 review 出来的：

| 发现方式 | 缺陷 |
|---|---|
| 实跑上海→杭州 | 同城不同站价差 1.8 倍，最快的是金山北不是虹桥 |
| 实跑摩尔曼斯克 | 高德把「东京」解析成广西的村庄，坐标看起来完全正常 |
| 实跑摩尔曼斯克 | 所有内容源被挡时 `validate-plan` 直接死锁 |
| 登录后重跑小红书 | 评论区信息量远超正文 |
| 真的截了一次图 | 费用表全在轮播图里，正文一个数字都没有 |
| 实跑携程酒店（新疆规划） | 匿名访问不展示任何价格，且第一次判断"匿名能看到价格"是错的——那次其实已经带着登录态 |

写测试测不出这些。构造的样例数据只会验证你已经想到的情况。

反过来，**「做不到」这个判断本身也必须实测**。开发过程中有三次把「没试过」
说成了「不支持」：小红书匿名访问、笔记配图读取、以及把已经存在的
`research.py` 说成没实现。每一次都白白丢掉一个真实能力。

不确定就跑一次。跑不了就说「没试」，不要说「不行」。

### 携程酒店和小红书一样，先停下来要登录

第一次测携程酒店时，看到 `hotels.ctrip.com` 能显示价格，就得出了"匿名也能查酒店"
的结论——**这个结论是错的**，只是没意识到那次浏览器早已带着登录态（页面右上角
写着「尊敬的钻石贵宾」，证据当时就在眼前）。真正的匿名请求会跳转到
`passport.ctrip.com`，一个价格都不显示。

机票和酒店在同一个域名下，行为却完全不同：Ctrip 机票匿名可查，Ctrip 酒店匿名
查不到。这正是「先试一次，再说做不到」那条原则要防的错——但这次踩的是它的
反面：**观察到了一次「能查到」，却没检查那次观察的登录态是否被污染**，等于用
一次不受控的实验去否定另一次实验。

所以酒店查询现在和小红书走同一套流程：**先停，用工具阻塞式地请用户扫码登录，
再继续**，不试图先匿名探一次。`references/workflow.md` 的 Lodging branch 与
`references/browser-use.md` 的 Hotels 小节都写明了这一步。

### 小红书只读文字等于没读

平台是图片优先的。行程图、逐项花费表、打包清单通常画在轮播图里，正文只留
一段引言——笔记本身就写着「行程图和花费放最后了」。实测一条 8 天俄罗斯笔记，
第 18 张图是完整预算表（机票、签证、住宿、流量卡、现金分项），**正文里一个
数字都没有**。

所以留作证据的笔记必须看图：记下 `1/18` 这个计数，点最后一个分页点直接跳到
末尾，截图逐张读。图里读出的数字标 `"extraction": "image"`，并保留笔记 URL
和图片序号。

写在表格里会让它显得权威，但它仍然只是某个人某一次旅行的账单，依然是
`PRICE_SIGNAL`。

OTA 不需要这么做——机票价格在 DOM 里，截图纯属浪费时间。

### 受阻的来源只能为「没有」开脱，不能为「空的」开脱

目的地在高德覆盖外、小红书又需要登录时，没有任何来源能提供景点内容。此前
`validate-plan` 直接判 `INVALID: Plan has no attraction activities`——听起来
像方案写得差，实际是无源可查，于是这个 Skill 对这类目的地产不出任何合法结果。

现在可以声明 `unavailable_sources`，缺内容降级为 `INCOMPLETE_EVIDENCE`。

赦免范围**刻意收得很窄，只有「完全没有景点」这一条**。查不到就不该列；列了
却没有特色、没有理由、没有来源的景点，不是来自受阻的查询，是模型编的。

### 地理编码只信得过它证明的部分

高德的地点数据以中国大陆为主，而**它对境外查询不返回空**——返回的是名称
相近的国内地点，坐标格式完全正常。实测：`东京` → 广西平南县一个真名叫
「东京」的村庄；`捷里别尔卡` → 贵州丹寨县的「里别」。

这类结果比报错危险得多：它会一路流进路径计算，让每一个距离和时长都变成
自信的错误，且外观与已核实事实无异。所以 `geocode` 在低置信时**拒绝返回
坐标**，而不是附带一个没人读的警告。

判据在 `travel_planner.geomatch`，两条都只依赖响应本身：查询词是否出现在
返回地址里，以及城市查询是否落到了村庄级别。

### 时间处理集中在一处

任何需要比较时刻的地方都走 `travel_planner.timeutil`：`parse_datetime`
要求字符串带 UTC 偏移，`require_aware` 拦住调用方传进来的裸时钟。

不要在模块里另写一份解析器。`feasibility` 和 `flight` 曾各自复制过一份，
结果是同一个缺陷要修两次，而且只在其中一处被发现。

也不要给缺失的时区**猜**一个默认值。营业时间误报就是这么来的：代码把
UTC 时间戳当成了当地墙上时间。宁可报错说清楚，也不要静默假设。

## 安全发布

**不要直接上传本地工作目录。** 本地目录可能包含 `vendor/`、虚拟环境和运行产物。

生成白名单发布包：

```bash
bash scripts/prepare_release.sh
```

输出在 `dist/travel-planner-mvp/`，只包含明确允许公开的源码、文档、测试、
示例和补丁。发布前审计：

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

本机装了 `gitleaks` 的话，审计脚本还会额外做一轮密钥扫描。

注意 `audit_release.sh` 是**对打包产物跑**，不是对源码树跑——源码树里有
`vendor/` 时它会（正确地）报错。

## 版本与发布

采用语义化版本 `MAJOR.MINOR.PATCH`：

| 位 | 什么时候加 | 例子 |
|---|---|---|
| MAJOR | 破坏性变更，使用者的旧数据或旧调用会失败 | 把 `timezone` 改成必填、删掉某个 CLI 命令 |
| MINOR | 新增功能，向后兼容 | 接入新数据源、新增 CLI 命令 |
| PATCH | 只修 bug 或文档，行为不变 | 修一个误报、补一段安装说明 |

**改动量大不等于 MAJOR。** MAJOR 只跟破坏性挂钩，跟工作量无关。

发布顺序——**打标签一定放最后**：

```bash
# 1. 代码和文档全部改完并推送
git push origin main

# 2. 确认 GitHub Actions 变绿

# 3. 最后才打标签
git tag -a v0.3.0 -m "简短说明"
git push origin v0.3.0

# 4. 在 GitHub 上基于该标签建 Release
```

标签是钉在某个 commit 上的图钉，不会跟着后续提交移动。先打标签再改代码，
Release 页面下载到的就是旧版本。

**永远不要移动已公开的标签。** 别人可能已经下载过，同一个版本号对应两份
不同代码会让问题无法复现。宁可多发一个 PATCH 版本。

## 提交信息

说明改了什么、为什么改，以及不改会出什么问题。相比罗列改动，更重要的是让
读者理解当初为什么需要这次改动。

## CI

每次 push 和 pull request 会：

- 在 Python 3.9–3.14 上跑测试
- 校验 `SKILL.md` 与 `agents/openai.yaml`
- 运行 ShellCheck
- 生成并审计发布包
- 用 Gitleaks 扫描完整 Git 历史

个人仓库无需额外的 Gitleaks License；组织仓库需按该 Action 的要求配置。
