# Changelog

## 2026-07-05
- 基于仓库内置 `Tg@TrollstoreKios.app`（StandarReader 2.56.1）复扫 IPA，完善 skill 逆向基线。
- 新增 `tools/scripts/decode_xbs.py`（Go 不可用时的 XBS 解包回退）。
- 逆向文档与 skill 补全：`webViewSkipUrlsUnless`、`webViewSniff`、`wkwebview_post`、LCJSTool 能力清单。

## 2026-03-12
- WebView 模拟增强（静态逆向驱动）：
  - `tools/validator` 新增 WebView 执行层：
    - 新增 `services/webviewService.js`
    - 支持 `webView/webViewJs/webViewJsDelay/webViewSkipUrls/webViewSkipUrlsUnless`
    - `engine=auto` 命中 WebView 键自动切换执行引擎
  - `xbs_tool.py simulate-live/simulate-fixture` 新增参数：
    - `--engine auto|http|webview`
    - `--webview-timeout <seconds>`
  - 模拟报告新增 WebView 机读字段：
    - `steps.*.runtime_engine`
    - `steps.*.webview_applied_keys`
    - `steps.*.webview_trace`
  - 保持 blocked 归因独立：
    - `403/429/challenge` 继续输出 `blocked`，不与 parser fail 混淆
- 新增静态逆向基线文档：
  - `docs/REVERSE_WEBVIEW_BASELINE_2561.md`
  - 固化字段证据矩阵与“逆向结论 -> 模拟器规则”映射
- 流程/文档/skill 同步：
  - `README`、`MAINTENANCE_WORKFLOW`、`TARE_USAGE_PLAYBOOK`
  - `skills/global/xbs-booksource-workflow.SKILL.md`
  - `skills/local/xiangse-booksource.SKILL.md`
- 新增“真实模拟测试”能力（导入前自动验收闭环）：
  - 新增 `tools/validator` Node 引擎（CLI 模式）：
    - 保留核心能力：`requestBuilder/stepExecutor/validationService/httpService/jsSandbox`
    - 四步强制：`searchBook -> bookDetail -> chapterList -> chapterContent`
  - 新增 `xbs_tool.py` 子命令：
    - `simulate-live`（真实网络请求）
    - `simulate-fixture`（本地样本回放）
  - 新命令自动串联流程：
    - `import-fix -> schema_check -> editor_check -> simulate`
  - 新增风控归因：
    - 命中 `403/429` 与 Cloudflare/challenge 特征时输出 `blocked`
    - 与 parser 失败分开标记，报告提供 `blocked_reason`
  - 新增机读报告字段：
    - `schema_check`、`editor_check`、`simulation_verdict`、`overall_verdict`
    - 四步请求/响应摘要、失败原因、阻断原因
- 文档与 skill 同步：
  - `README` 增加 Node 依赖与 `simulate-live/simulate-fixture` 用法
  - global/local skill 增加“导入前四步模拟”硬门槛
  - `MAINTENANCE_WORKFLOW` 增加模拟测试发布前检查
  - `TARE_USAGE_PLAYBOOK` 固定输出新增 `simulation_verdict/blocked_reason`

## 2026-03-11
- 香色闺阁规则提取能力收敛（Xiangse-only）：
  - 目标客户端明确为 StandarReader 2.56.1，不再以安卓阅读/跨客户端兼容为目标
  - `check_xiangse_schema.py` 强化硬约束：
    - `sourceType` 必须为 `"text"`（非 text 直接 FAIL）
    - `requestInfo` 必须为字符串（非字符串直接 FAIL）
  - `xbs_tool.py` 新增 `import-fix`：
    - 支持 `.xbs/.json` 输入
    - 自动补齐缺失 `requestInfo/responseFormatType`，归一化 `sourceType/enable/weight`
    - 归一化 `bookWorld.moreKeys.requestFilters` 为字符串
    - 可选输出修复后 XBS 与修复报告
  - Skill/README/TARE/维护流程同步到“先 import-fix 再校验转换”的固定链路
- Windows 开箱即用转换能力落地（无需 Go）：
  - 新增内置二进制：`tools/bin/windows/xbsrebuild.exe`（amd64）
  - 新增元数据：`tools/bin/windows/xbsrebuild.metadata.json`（`source_commit` + `sha256`）
  - `xbs_tool.py` runner 优先级更新：
    1) `XBSREBUILD_BIN`
    2) 内置 `tools/bin/windows/xbsrebuild.exe`
    3) PATH
    4) `XBSREBUILD_ROOT` + `go run`
  - `doctor` 新增内置二进制探测与命中来源输出
  - Windows 入口补齐：`.cmd` 增强 + 新增 `.ps1`（json2xbs/xbs2json/roundtrip）
- 内置迁移 `xbsrebuild` 源码快照（vendor）：
  - 新增目录：`tools/vendor/xbsrebuild/`（整仓源码快照，不含 `.git`）
  - 新增来源追溯：`tools/vendor/xbsrebuild/UPSTREAM_SOURCE.md`
  - 记录上游仓库：`https://github.com/ne1llee/xbsrebuild`
  - 当前同步 commit：`5cd1249`
  - `xbs_tool.py` runner 探测顺序扩展为：
    1) `XBSREBUILD_BIN`
    2) 内置 `tools/bin/windows/xbsrebuild.exe`
    3) PATH
    4) `XBSREBUILD_ROOT`
    5) 同级 `../xbsrebuild`
    6) 内置 vendored `tools/vendor/xbsrebuild`
  - `doctor` 新增 `sibling_xbsrebuild_root*` 与 `vendored_xbsrebuild_root*` 诊断输出
- 新增导入闪退根因沉淀（StandarReader 2.56.1 / Mac Catalyst）：
  - 崩溃指纹：`NSInvalidArgumentException` + `-[__NSArrayI allKeys]`
  - 根因：`bookWorld.categories` 使用数组形态，客户端按字典读取导致崩溃
  - 规则修订：香色导入产物禁用 `bookWorld.categories` 数组，统一改为 `bookWorld.{分类名}` map 结构
- `XBS_JSON_CODING_RULES` 同步更新：
  - 1.1 增加导入闪退补充说明
  - 4.5 增加 `bookWorld` 结构硬约束
  - 4.12 增加 `-[__NSArrayI allKeys]` 快速排障项

## 2026-03-10
- 并入 StandarReader 2.56.1 逆向基线（文档 + 校验器 + 转换入口）：
  - 新增 `docs/REVERSE_BASELINE_2561.md`（SDK/tools、Hook 点、可疑 URL、规则对照矩阵、证据编号）
  - `XBS_JSON_CODING_RULES` 补齐真值枚举：
    - `responseFormatType`: `""/base64str/html/xml/json/data`
    - `responseDecryptType`: `""/encryptType1`
  - `weight/enable` 从硬拒绝调整为“归一化建议 + 风险提示”语义
- `check_xiangse_schema.py` 引入分级校验：
  - 继续报错：缺失核心字段、禁用顶层字段、`java.getParams()`
  - 默认警告：`method:/data:/headers:`、`weight` 非字符串、`enable` 非整型
  - 新增枚举报错：`responseFormatType`、`responseDecryptType` 不在白名单
  - 新增 `--strict-requestinfo` 开关（将 `method/data/headers` 升级为错误）
  - 输出末尾新增 `ERROR_COUNT/WARNING_COUNT/SOURCE_COUNT`
- `xbs_tool.py` 透传 strict 策略：
  - `json2xbs` / `roundtrip` 新增 `--strict-requestinfo`
  - `_run_schema_check` 支持 strict 透传，默认行为保持兼容
- 修复 2.56.1 保存闪退高风险字段：
  - `weight` 统一改为整数字符串（默认 `"9999"`）
  - `check-editor` 新增高风险规则：`WEIGHT_NON_STRING`
- `xbs_tool.py` 新增批量迁移命令：
  - `normalize-2561`（递归识别书源、无损转换 `weight`、可选自动重建同名 `.xbs`、输出报告）
  - 识别逻辑已收敛为“强匹配书源结构”，避免误改普通 JSON
- 已执行一次全工作区迁移与重建：
  - 扫描 `826` 个 JSON，修复 `118` 个、重建 `118` 个 XBS、失败 `0`
  - 发现并回滚误命中非书源 JSON `10` 个（最终二次迁移 `CHANGED=0 / FAILED=0`）
- 实机回归（80zw）：
  - `weight(number) -> weight(string)` 后，导入与编辑保存恢复正常（不改保存可通过）。
- 新增 StandarReader 2.56.1 编辑保存兼容工具链：
  - `tools/scripts/check_editor_compat.py`（编辑保存风险检查）
  - `tools/scripts/build_editor_ab_variants.py`（A0/A1/A2/A3 对照包生成）
  - `tools/scripts/editor_compat.py`（editor-safe 变换与风险规则）
- `xbs_tool.py` 新增子命令：
  - `check-editor`：执行编辑兼容检查
  - `profile --profile editor_safe`：生成编辑器兼容书源（可选直接导出 XBS）
  - `build-ab`：一键生成 A/B JSON 与 XBS
- 生成 `gudaibook1` 保存闪退定位包：
  - `gudaibook1_editor_ab_v0308_A0~A3.(json/xbs)`
  - `gudaibook1_editor_safe_v0308.(json/xbs)`
- 更新规范与流程：
  - `xbs-booksource-workflow.SKILL`：新增“保存回归门槛”与 editor-safe/A-B 命令
  - `xiangse-booksource.SKILL`：新增 editor-safe 兼容例外与保存回归要求
  - `XBS_JSON_CODING_RULES`：新增 2.56.1 编辑器兼容约束
  - `MAINTENANCE_WORKFLOW`：发布前新增“不改保存/改名保存/改字段保存”硬门槛

## 2026-03-08
- 新增 `17k` 实战规范沉淀（skill + 文档）：
  - 闪退防护：禁止把超长混淆 WAF JS 直接作为主链路。
  - 加密正文验收：`content[].encrypt=1` 时必须验证“解密后正文非空且非密文”。
  - 分类完整性：`bookWorld` 与 `requestFilters` 纳入交付必检。
  - 备注规范：`公众号:好用的软件站` 统一写入交付备注（`delivery_notes`），不再写入 `sourceName`。
- 更新 `xbs-booksource-workflow.SKILL` 与 `xiangse-booksource.SKILL`：
  - 增加 17K 专项规则段；
  - 移除旧的 `sourceName` 宣传后缀约束。
- 更新文档：
  - `XBS_JSON_CODING_RULES`：新增交付备注规范与 17K 验收规则。
  - `香色书源开发指南与工作流程`：新增 17K 复盘条目。
  - `MAINTENANCE_WORKFLOW`：新增发布前四项检查（导入稳定性/解密/分类/备注）。
  - `TARE_USAGE_PLAYBOOK`：固定输出新增 `delivery_notes` 必填字段。

## 2026-03-06
- 新增香色 schema 防跑偏机制（针对弱模型输出偏移）：
  - 新增 `tools/scripts/check_xiangse_schema.py`
  - 转换前强制 schema 体检：拦截 `bookSourceName/*`、`java.getParams()`、`method/data/headers` 等非香色写法
  - `xbs_tool.py` 的 `json2xbs/roundtrip` 默认自动执行 schema 体检（失败即中断）
  - `xbs-booksource-workflow.SKILL`、`xiangse-booksource.SKILL`、`TARE_USAGE_PLAYBOOK`、`README` 同步加入硬门槛
- 新增 `Tare` 弱模型专用执行手册：
  - `docs/TARE_USAGE_PLAYBOOK.md`
  - 固定输入包模板、固定提问模板、固定输出 JSON
  - 增加“禁止项 + 失败兜底模板”，降低弱模型跑偏概率
- `README` 与 local skill 同步增加 Tare 交付模式入口
- 新增跨平台转换入口，兼容 Windows / Termux / macOS / Linux：
  - 新增 `tools/scripts/xbs_tool.py`（`json2xbs/xbs2json/roundtrip/doctor`）
  - `.sh` 脚本改为调用 `xbs_tool.py`，统一执行链路
  - 新增 Windows `.cmd` 封装：`json2xbs.cmd`、`xbs2json.cmd`、`roundtrip_check.cmd`
  - README 和 skill 补充“普通用户可复制命令”与环境探测顺序
- 新增 `libahao` 实战规则沉淀（搜索/分类字段污染修复）：
  - 明确香色运行时 `list` 子字段 XPath 统一 `//` 开头，禁用 `./...` 写法
  - 修复“整行文本污染”问题（空白与 `\n` 统一清洗）
  - 分类封面新增 URL 反推策略：`/book/{aid}_{bid}/ -> /data/image/{bid}.jpg`
  - 文档同步更新：`RETROSPECT_LOG`、`MAINTENANCE_WORKFLOW`、`XBS_JSON_CODING_RULES`、`xbs-booksource-workflow.SKILL`
- 新增 `bxwx` 成品书源（DOM + 目录归一化 + 同章分页守卫）：
  - 搜索：`POST /search.html`（`searchtype=all` + `369koolearn`）
  - 详情：`og:*` 优先，兼容 `og:novel:read_url` 指向目录页
  - 目录：`/dir/{aid}/{bid}.htm` 与 `/b/{aid}/{bid}/` 双输入兼容
  - 正文分页：`/b/{bookId}/{chapterId}(_{page}).html` 同章递增守卫
  - 分类：新增 `bookWorld`，路径 `/bsort{n}/`，默认单页稳定模式
- 文档/skill 补充 `bxwx` 经验沉淀：
  - 搜索限流提示页识别（“搜索间隔为30秒，请稍后在试！”）
  - 分类路径实测优先（禁止套用他站分类模板）
  - `read_url` 目录型 URL 归一化策略
  - 正文尾巴提示清洗规则

## 2026-03-05
- 新增 `shuhaoxs` 成品书源（站内可用优先方案）：
  - 搜索：分类遍历 + 关键词过滤（fallback，可用优先）
  - 详情：`og:*` 元数据优先（书名/作者/分类/状态/更新时间/最新章节/封面）
  - 目录：`index.php?action=loadChapterPage` 分页接口
  - 目录分页去重：按 `chapterorder` 页范围过滤，防越界页重复
  - 正文分页：`/{aid}-{cid}-{page}.html` 同章守卫
- 文档/skill 补充 `shuhaoxs` 经验沉淀：
  - 外部加密搜索链路识别与降级策略
  - `loadChapterPage` 重复页防护（禁止仅靠 `list.length` 翻页）
- 新增 `sudugu` 成品书源（DOM + 分页守卫方案）：
  - 搜索：`/i/sor.aspx?key=...&p=...`（GET + 编码）
  - 目录分页：`p-2.html#dir` 链路
  - 正文分页：`/{bookId}/{chapterId}-N.html` 同章守卫（防误跳下一章）
  - 分类分页：`/{cat}/{page}.html` 路径模板
- 文档/skill 补充 `sudugu` 经验沉淀：
  - `chapterContent.nextPageUrl` 必须做“同章分页守卫”
  - 分类分页 URL 形态必须实测，不允许猜测 `p-2`/`_2`
- 新增 `66shuba` 成品书源（API-first 方案）：
  - `search/detail/catalog/chapter` 全链路 JSON 接口
  - 搜索 `CardList -> Body -> ItemData` 扁平化
  - 目录哨兵章节过滤（`C/chapterId/id <= 0` 丢弃）
  - 正文接口 `chapter/vip-chapter` 自动分流
  - 占位正文识别（`code=0` 但内容为“网络开小差了”）
- 文档补充 `66shuba` 经验沉淀：
  - API-first 站点优先策略
  - 目录有效章节过滤规范
  - 占位正文排障标准
- 补充 `deqixs` 二跳正文接口经验沉淀：
  - `chapter.js.php -> ajax2.php` token 链路识别与实现
  - `ajax2` 动态请求头要求（`X-Requested-With` + 章节页 `Referer`）
  - `status=1` 但正文空的混合响应排障（禁止 `chapterToken` 早退）
- 更新维护流程检查项：
  - 增加“接口二跳正文”识别
  - 增加“仅支持网页端访问/不支持该客户端访问”排障步骤
  - 增加“`status=1` 但正文空”专项校验
- 更新 `xbs-booksource-workflow` skill（项目镜像 + `~/.codex/skills`）：
  - 新增 deqixs 风控请求头与混合响应解析实战规则
  - 调整策略为“优先接口二跳，webView 作为回退”

## 2026-03-04
- 建立 `booksource_project` 正式项目结构。
- 归档稳定成品书源：`shukuge v0304`、`txtdd v0303`、`bcshuku v0304`。
- 归档测试书源、HTML 样本、规则文档与 skill 镜像。
- 新增工具脚本：`json2xbs.sh`、`xbs2json.sh`、`roundtrip_check.sh`、`refresh_git_records.sh`。
- 固化章节列表兼容规则：`//text()` 与 `//@href`。
- 新增 `apps/web-validator`：香色书源 Web 检测平台（React + Vite + Tailwind / Express + TypeScript）。
- 新增 5 个 API：`source/normalize`、`validate/run`、`validate/step`、`source/patch`、`source/export`。
- 新增规则引擎能力：`requestInfo @js`、模板变量替换、DOM XPath 解析、字段 `||@js` 后处理、live/fixture 双模式。
- 新增半自动修复策略：`text() -> //text()`、`@href -> //@href`、`sourceName` 后缀修正、`weight` 归一化。
- 新增 server 单元/集成测试，fixture 模式下完成 `shukuge_source_v0304` 三步链路回归。
- 新增 `deqixs` 实战经验沉淀：
  - 搜索中文参数规范：`GET + encodeURIComponent`
  - 搜索“列表页/直达详情页”双形态 URL 兜底策略
  - `requestInfo` URL 清洗转义兼容规范（`split('\\\\/').join('/')`）
  - `bookWorld` 分类性能策略（禁默认连翻，按 `pageIndex` 单页拉取）
  - 动态正文 `webView + webViewJs` 回填流程
- 同步更新文档：`香色书源开发指南与工作流程.md`、`XBS_JSON_CODING_RULES.md`、`MAINTENANCE_WORKFLOW.md`、`RETROSPECT_LOG.md`。
