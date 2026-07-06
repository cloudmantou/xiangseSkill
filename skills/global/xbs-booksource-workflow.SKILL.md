---
name: xbs-booksource-workflow
description: Build, debug, and maintain 香色闺阁/香色书源 JSON and XBS files. Use when users ask to create or fix book sources, convert between xbs and json, debug empty parsed fields, validate XPath and JS parser rules, or produce import-ready XBS outputs for the app.
---

# XBS Booksource Workflow

## Website → Booksource Entry

When the user gives a **website URL** and wants a new/fix book source, load first:

- `skills/local/website-to-booksource.SKILL.md`（七步流水线：侦察 → 规则 → schema → simulate → XBS → Mac 导入）

One-command pipeline after JSON is ready:

```bash
python3 tools/scripts/pipeline_new_source.py run -i <source.json> --fixtures <samples_dir> --live --import-mac --report-dir tools/verification/out
```

## IPA Reverse Baseline (StandarReader 2.56.1)

Ground truth comes from the bundled app package in this repo:

- Bundle: `Tg@TrollstoreKios.app/` (`香色闺阁Plus`, version `2.56.1`)
- Binary: `Tg@TrollstoreKios.app/Tg@TrollstoreKios`
- Editor field enums: `Tg@TrollstoreKios.app/lpnet_modelInfo` (XBS)
- Evidence docs: `docs/REVERSE_BASELINE_2561.md`, `docs/REVERSE_WEBVIEW_BASELINE_2561.md`

Decode bundled editor metadata when Go `xbsrebuild` is unavailable:

```bash
python3 tools/scripts/decode_xbs.py Tg@TrollstoreKios.app/lpnet_modelInfo
```

Confirmed client contract (static strings + decoded `lpnet_modelInfo`):

| Area | Truth |
|---|---|
| Top-level shape | `{ "<alias>": { sourceName, sourceUrl, sourceType, enable, weight, ... } }` |
| Core actions | `searchBook`, `bookDetail`, `chapterList`, `chapterContent` |
| Required per action | `actionID`, `parserID`, `requestInfo`, `responseFormatType` |
| `parserID` | `DOM` (TFHpple/DomModelParser) or `JS` |
| `responseFormatType` | `""`, `base64str`, `html`, `xml`, `json`, `data` |
| `responseDecryptType` | `""`, `encryptType1` |
| Placeholders | `%@result`, `%@keyWord`, `%@pageIndex`, `%@offset`, `%@filter` |
| `@js` context | `config`, `params`, `result` (never `java.getParams()`) |
| `requestInfo` object keys | `url`, `POST`, `httpParams`, `httpHeaders`, `forbidCookie`, `forbidCache`, `cacheTime`, `webView*` |
| WebView keys | `webView`, `webViewJs`, `webViewJsDelay`, `webViewSkipUrls`, `webViewSkipUrlsUnless`, `webViewSniff` |
| WebView helper | built-in `wkwebview_post(path, charset, params)` for form POST inside WKWebView |
| List child XPath | prefer `//...`; avoid `./` and `.//` under `list` |
| Import crash guards | `weight` as string; `bookWorld` as category map (no `categories` array) |

Routing classes (for debugging mindset, not for writing ObjC):

- `BookQueryManager.queryByActionID:...` — action dispatch
- `DomModelParser.getRequestInfoForConfig:parserParams:error:` — request build
- `DomModelParser.valueForNode:config:rule:ruleKey:userInfo:removeHtml:` — field parse
- `LPNetWork2.startWithUrl:requestInfo:config:userInfo:` — HTTP/WebView fetch

## Overview

Implement or fix text book sources for 香色闺阁（StandarReader 2.56.1 only）with a deterministic workflow: analyze target pages, generate rule JSON, convert to XBS, and validate with real HTML samples.

## Workflow

1. Inspect source format and goal.
2. Build or repair JSON rules.
3. Validate selectors with real HTML.
4. Convert JSON to XBS.
5. Verify roundtrip and provide checksum.

## Step 1: Inspect Input and Site

- Confirm whether input is `.json` or `.xbs`.
- Legacy source import-first rule:
  - if input is `.xbs`, run `python tools/scripts/xbs_tool.py import-fix -i <input.xbs> -o <fixed.json> --to-xbs <fixed.xbs> --report <fix_report.json>`
  - continue all checks/conversion with `<fixed.json>` / `<fixed.xbs>`
- For new source rules, fetch and inspect:
  - search page
  - detail page
  - chapter list page
  - chapter content page
- Hard gate before conversion (must pass):
  - `python tools/scripts/check_xiangse_schema.py <source.json>`
  - If this fails, do NOT convert to XBS first; fix schema first.
- StandarReader 2.56.1 编辑兼容门槛（新增）：
  - `python tools/scripts/xbs_tool.py check-editor -i <source.json>`
  - 若触发高风险项（如新 schema wrapper、`requestFilters` 非字符串），先产出 `editor_safe` 再测：
    - `python tools/scripts/xbs_tool.py profile -i <input.json> -o <editor_safe.json> --profile editor_safe`
  - 需要批量修复历史书源时：
    - `python tools/scripts/xbs_tool.py normalize-2561 -i <json_or_dir> --rebuild-xbs --report <report.json>`

## Step 2: Build or Repair JSON Rules

Minimum required actions:

- `searchBook`
- `bookDetail`
- `chapterList`
- `chapterContent`

Required action fields:

- `actionID`
- `parserID`
- `responseFormatType`
- `requestInfo`

香色 schema 强约束（防跑偏，必须满足）:

- Top-level must be: `{ \"<sourceAlias>\": { ... } }` (source config nested under alias key).
- Source config must use:
  - `sourceName/sourceUrl/sourceType/enable/weight`
- `sourceType` must be exactly `"text"` (Xiangse 2.56.1 hard constraint).
- Forbidden legacy top-level keys:
  - `bookSourceName/bookSourceUrl/bookSourceGroup/httpUserAgent`
- `requestInfo @js` runtime must use `config/params/result`.
- Forbidden runtime/transport patterns in `requestInfo`:
  - `java.getParams()`
  - `method:` (use `POST`)
  - `data:` (use `httpParams`)
  - `headers:` (use `httpHeaders`)

Prefer:

- `parserID: DOM`
- `requestInfo: @js:` (avoid legacy JS callback fields unless required)
- `weight` must be integer-like string in `\"1\"..\"9999\"` (default `\"9999\"`)
- Priority semantics: larger `weight` means higher source priority
- If using template `requestInfo`, support placeholders: `%@result`, `%@keyWord`, `%@pageIndex`, `%@offset`, `%@filter`
- For chapter pagination requests, prioritize:
  - `params.lastResponse.nextPageUrl`
  - then `result`
  - then `params.queryInfo.url`
- When next-page URLs are relative, resolve with `params.responseUrl` first, then `config.host`
- Use `moreKeys` when needed:
  - `requestFilters` for category/sort filters
  - `removeHtmlKeys` for html/script cleanup
  - `skipCount` for list head trimming
  - `pageSize` or `maxPage` for pagination control
- For paged `chapterContent`, set `maxPage` in both:
  - `chapterContent.validConfig`
  - `chapterContent.moreKeys`
- WebView request keys (from IPA static baseline):
  - `webView`, `webViewJs`, `webViewJsDelay`
  - `webViewSkipUrls` (blocklist), `webViewSkipUrlsUnless` (allowlist override)
  - `webViewSniff` only when sniffing is truly required; prefer API/HTTP first
  - `wkwebview_post(path, charset, params)` for challenge/login form POST inside WebView

实战补充（2026-07，cuoceng / 错层小说网）:

- **App 真值**：`Tg@TrollstoreKios.app`（StandarReader 2.56.1）；`SourceRead.app` 是 Legado，不能验 XBS。
- **同名书源叠版**是「simulate PASS、App 无目录」首要根因：多个 alias 共用 `sourceName` 且都 `enable=1` 时，`queryCatalogByBook:sourceName:` 会命中旧规则。导入后必须 `mac_xiangse_app.py prune-sources --remove-prefix "<prefix>-"`，沙盒只留最新 alias。
- **导入是合并**：`open -a 香色闺阁 file.xbs` 不删旧版；App 运行中导入可能覆盖 prune 结果。先 quit App 再写沙盒。
- **TFHpple vs JSDOM**：`list=//dd/a` + `//text()` + `//@href` 在 App 正确，在 fixture 校验器 `sample_item` 可能是全页垃圾；信 `list_length` + 真机，不信 `sample_item.title/url`。
- **目录字段**：二进制无 `chapterListUrl`；目录 URL 只能在 `chapterList.requestInfo` 从 `queryInfo.url/detailUrl` 归一化（如 `/book/{id}.html` → `/book/chapter/{id}.html`）。
- **requestInfo 反模式**：禁 `Object.assign({}, config.httpHeaders)`；禁虚构 `chapterListUrl`；优先 `return {url, httpHeaders: config.httpHeaders}`。
- **搜索降级**：Cloudflare 拦站内搜 → 分类页 + `requestFilters.category` + 关键词过滤。
- **可用模板（v0713）**：
  - `chapterList.list`: `//div[@id='allchapter']//dd/a`
  - `chapterList.title/url/detailUrl`: `//text()` / `//@href` / `//@href`
  - `searchBook.url` 与 `detailUrl` 同写
- 参考：`tools/verification/cuoceng_source.json`

实战补充（2026-03，deqixs）:

- Search 中文关键词优先 `GET + encodeURIComponent(params.keyWord)`；部分客户端 `POST` 中文参数会有编码不一致问题。
- Search 需要兼容“双形态响应”：
  - 模糊词返回列表页；
  - 精确词可能直接返回详情页（无 list）。
- 当 `searchBook.list` 已命中单条书籍节点时，`detailUrl` 优先使用 list 上下文相对字段，不要先用页面级 canonical/meta 覆盖。
- 为兼容“直达详情页”场景，可额外增加 `url` 兜底字段（canonical/meta），供后续 `bookDetail/chapterList/chapterContent.requestInfo` 回退取值。
- `bookWorld` 分类页默认按 `pageIndex` 单页请求；不要默认启用 `nextPageUrl + 超大 maxPage` 自动连翻，否则容易超时或卡住。
- `requestInfo` 里 URL 清洗避免易错正则写法 `replace(/\\//g,'/')`；推荐 `String(u).split('\\\\/').join('/')`。
- 正文链路先判定是否“接口二跳”：
  - 若站点是 `chapter.js.php -> ajax2.php` 这类 token 换正文接口，优先走接口，不默认上 `webView`。
  - 仅在接口链路不可行时，才使用 `webView + webViewJs` 回填。
- deqixs 类接口务必在第二跳请求头里显式注入：
  - `X-Requested-With: XMLHttpRequest`
  - `Referer: 当前章节 URL`
  否则常见返回：`仅支持网页端访问` / `不支持该客户端访问`。
- `chapterContent.content` 禁止“检测到 chapterToken 就直接 return ''”：
  - 混合响应（token脚本 + JSON）会被误杀，导致 `status=1` 但正文空。
  - 必须先尝试 JSON 解析，再做正则兜底提取 `content`。

实战补充（2026-03，66shuba）:

- API-first 站点优先全链路走 JSON 接口，不要优先依赖详情/阅读页 DOM。
- 常用链路：
  - search: `/api/novel/search`
  - detail: `/api/novel/detail/{bookId}`
  - catalog: `/api/novel/catalog/{bookId}`
  - chapter: `/api/novel/chapter/{bookId}/{chapterId}`（VIP 用 `vip-chapter`）
- `searchBook.list` 若是卡片嵌套结构（`CardList -> Body -> ItemData`），在 `list || @js` 中扁平化并过滤 `ItemType===0`。
- `chapterList.list` 必须过滤哨兵章节（如 `C=-10000`），通用规则：仅保留正整型章节 id。
- `chapterContent` 请求建议从 read URL 反解 `bookId/chapterId` 再组 API URL，减少上下游 URL 形态差异影响。
- 验证正文时增加“占位正文识别”：
  - 若返回 `code=0` 但 `content` 为“网络开小差了，请稍后再试”等提示语，判定为上游异常，不是规则成功。

实战补充（2026-03，sudugu）:

- 章节页常见“上一章/目录/下一页(或下一章)”共用同一 `prenext` 结构：
  - 不要仅靠文字匹配 `contains(text(),'下一页')`；
  - 优先取“右侧固定位”链接（如 `span[2]/a/@href`），再做 JS 守卫判定。
- 正文分页守卫推荐通用规则：
  - 解析当前 URL 和候选 URL 为 `/{bookId}/{chapterId}(-{page})?.html`
  - 仅当 `bookId` 相同、`chapterId` 相同、`nextPage > currentPage` 时继续翻页
  - 其它情况（下一章、目录、回详情）一律返回空，禁止误翻。
- 目录分页与分类分页不要猜 URL 形态：
  - 目录页可能是 `p-2.html#dir`
  - 分类页可能是 `/xuanhuan/2.html`（而不是 `/xuanhuan/p-2.html`）
  - 必须基于真实下一页链接或已验证模板构造。

实战补充（2026-03，shuhaoxs）:

- 站内搜索入口可能被外部站接管（如首页直接跳 `rrssk`）：
  - 先验证本域 `index.php?action=*` 是否存在可用搜索接口；
  - 若大多为 `404`，判定“无稳定站内搜索接口”。
- 外部搜索若为“关键词加密 + 结果链接加密 + 前端解密跳转”链路（`toUrl/openUrl`），默认不要直接作为主搜索方案：
  - 尤其是解密依赖 `CryptoJS + UA + 动态页面变量` 时，客户端运行时不一定可复现。
- 外部链路不稳定时，优先提供可用降级：
  - `searchBook` 改为“分类页遍历 + 关键词字段过滤”；
  - 明确这是 fallback 搜索，并在交付说明中标注精度限制。
- `bookDetail` 优先使用页面 `og:*` 元数据（`book_name/author/category/status/update_time/latest_chapter_name/url/image`），再回退 DOM 字段。
- `chapterList` 若走 `index.php?action=loadChapterPage&id={aid}&page={n}`：
  - 需处理“越界页重复最后一页”与“短书重复第 1 页”现象；
  - 不要仅凭 `data.length > 0` 继续翻页；
  - 建议按 `chapterorder` 校验当前页范围（每页 100：`1-100/101-200/...`）并据此决定 `list` 与 `nextPageUrl`。
- `chapterContent.nextPageUrl` 继续使用同章分页守卫：
  - 仅允许 `/book/{aid}-{cid}-{p}.html` 且 `aid/cid` 相同、`p` 递增；
  - 命中“下一章/目录/回详情”一律返回空。

实战补充（2026-03，bxwx）:

- 搜索接口存在站点级限流：`POST /search.html` 连续请求会返回“搜索间隔为30秒，请稍后在试！”页面。
  - 这属于上游限流，不是解析失败；
  - 调试与验证需加节流/重试（至少间隔 30 秒）或使用本地 fixture。
- 搜索表单字段需精确匹配：
  - `searchtype=all`
  - `369koolearn=<keyword>`
- `bookDetail` 常见 `og:novel:read_url` 直接给目录页（`/dir/{aid}/{bid}.htm`），不是阅读入口：
  - `chapterList.requestInfo` 需同时兼容 `/b/{aid}/{bid}/` 与 `/dir/{aid}/{bid}.htm` 两种输入。
- 分类页真实路径为 `/bsort{n}/`（如 `/bsort1/`），不要套用其他站点的 `/xuanhuan/2.html` 模板。
  - `bookWorld` 默认按单页处理（`maxPage=1`），避免盲翻到空页/错误页。
- 分类列表节点可直接使用 `#newscontent .l ul li`：
  - 书名：`span.s2 a`
  - 作者：`span.s4`
  - 分类：`span.s1`（需去 `[]`）
  - 更新时间：`span.s5`
- 正文分页继续使用“同章守卫”：
  - `#pager_next` 在末页常直接跳下一章（非下一页）；
  - 仅允许 `/b/{bookId}/{chapterId}(_{page})?.html` 且页码递增。
- 正文需清洗分页提示与推广尾巴（常见文案）：
  - “这章没有结束…下一页继续阅读…”
  - “小主子…下一页继续阅读…”
  - “喜欢…请大家收藏…更新速度全网最快”

实战补充（2026-03，libahao）:

- 香色闺阁里 `list` 子字段 XPath 统一用 `//` 开头，禁用 `./...` 与 `.//...`。
  - 错误高发写法：`./td[2]/a/text()`、`./td[3]/a/text()`、`./td[2]/a/@href`
  - 推荐：`//td[2]/a/text()`、`//td[3]/a/text()`、`//td[2]/a/@href`
- 能直接取目标字段时，不写“复杂拼接式 JS”：
  - 例如 `detailUrl/url` 直接用 `//td[2]/a/@href`，避免多余绝对化逻辑引入噪声。
- 列表字段禁止抓整行文本再拆分：
  - 不要把 `status/desc/wordCount` 绑定到整段 `tr` 文本；
  - 采用“列到字段”的窄 XPath，一列一个字段。
- 所有文本字段默认做空白归一：
  - `String(result || '').replace(/\\s+/g, ' ').trim()`
  - 分类名额外去方括号：`.replace(/[\\[\\]]/g, '')`
- 分类页无 `<img>` 时，允许由 `detailUrl` 反推封面：
  - `/book/{aid}_{bid}/` -> `/data/image/{bid}.jpg`
  - 该策略用于 `bookWorld.cover`，可显著减少“分类封面为空”。

实战补充（2026-03，17k）:

- 导入稳定性（防闪退）优先于“强行接入复杂链路”：
  - 禁止把超长混淆 WAF JS 直接塞进 `requestInfo/content` 作为主链路。
  - 遇到 WAF/风控页面，优先 API 或可稳定复现的请求链路；不稳定链路降级为可用方案。
- 加密正文必须做解密成功校验：
  - 若章节响应含 `content[].encrypt=1`，仅拿到 `title` 不算成功。
  - 交付前必须确认 `chapterContent.content` 为非空明文（不是密文串、不是空串）。
- 分类功能是交付必检项：
  - 不允许遗漏 `bookWorld` 与分类筛选（`requestFilters`）设计；
  - 若站点不支持完整分类，需在交付备注明确“缺失原因 + 降级策略”。
- 公众号信息写在交付备注，不写在 `sourceName`：
  - `sourceName` 仅保留“站点名 + 版本”语义。
  - `delivery_notes` 必须包含：`公众号:好用的软件站`。

实战补充（2026-03，StandarReader 2.56.1 编辑保存闪退）:

- 若崩溃日志出现 `-[__NSCFNumber length]`，先检查 `weight` 类型：
  - 必须是整数字符串（如 `"9999"`），不能是数字类型。
- 导入可用不等于可编辑可保存，必须单独做“保存回归”：
  - 进入编辑页后“不改直接保存”
  - 修改 1 个字符后保存
  - 修改 1 个规则字段后保存
- 若保存闪退，按 A/B 变体定位字段簇（A0/A1/A2/A3）：
  - `python tools/scripts/xbs_tool.py build-ab -i <input.json> -d <out_dir> --prefix <name> --to-xbs`
- `editor_safe` profile 目标：
  - 保留 `bookWorld` 分类能力
  - 将 `requestFilters` 统一为字符串
  - 降级高风险结构（如 `validConfig` JSON 字符串、顶层复杂对象字段）

实战补充（2026-03，StandarReader 2.56.1 导入即闪退）:

- 若崩溃日志出现：
  - `NSInvalidArgumentException`
  - `-[__NSArrayI allKeys]`
  说明客户端把数组按字典读取。
- 已确认高风险触发点：`bookWorld.categories` 数组形态。
- 导入产物硬约束：
  - `bookWorld` 使用分类 map（`bookWorld.{分类名}`），禁用 `bookWorld.categories` 数组。
  - `enable` 统一输出 `1/0`。
  - `responseFormatType` 统一小写（`html/json/xml/text`）。
  - `requestInfo` 对象转为字符串模板或 `@js:return {...};`。

## Step 3: Selector Validation (Critical)

Validate selectors against saved HTML (e.g., `xmllint --html --xpath ...`).

香色闺阁兼容重点:

- If `listLengthOnlyDebug > 0` but fields are empty, change child selectors from `.//...` to `//...`.
- This parser may not reliably honor relative XPath context under `list`.
- In 香色 runtime, avoid `./...` in list child fields as well; prefer `//...` for stability.
- If runtime context is unclear, use JS debug return shape:
  - `return {"config": config, "params": params, "result": result};`
- Remember `result` changes by stage:
  - in `requestInfo`: upstream URL or `nextPageUrl`
  - in parse stage: previous-layer parsed value
- If chapter body is rendered by JS (`document.writeln(base64...)`), decode in `content || @js:` and add guarded `nextPageUrl` for same-chapter pagination.
- Guarded next-page rule is mandatory:
  - parse current URL + candidate next URL as `/baidu/{aid}/{cid}(_{page})?.html`
  - continue only if `aid` same, `cid` same, and `nextPage > currentPage`
  - never guess `_1/_2` blindly when no hard evidence exists
- If old client fails with `content || @js:` (script stripped in DOM), switch to legacy-compatible parsing:
  - `chapterContent.parserID = JS`
  - `chapterContent.responseFormatType = ''` (plain string)
  - decode body in `responseJavascript(config, params, resStr)` from raw response text.
- Use old-engine-safe JS for compatibility:
  - prefer `var` + `function`
  - avoid `new URL()`, optional chaining, nullish coalescing

See detailed pitfalls and IPA evidence:

- `docs/XBS_JSON_CODING_RULES.md`
- `docs/REVERSE_BASELINE_2561.md`
- `docs/REVERSE_WEBVIEW_BASELINE_2561.md`
- bundled sample: `Tg@TrollstoreKios.app/`

## Step 4: Convert Between JSON and XBS

Preferred (cross-platform, including Windows/Termux):

- `python tools/scripts/xbs_tool.py json2xbs -i <input.json> -o <output.xbs>`
- `python tools/scripts/xbs_tool.py xbs2json -i <input.xbs> -o <output.json>`
- `python tools/scripts/xbs_tool.py roundtrip -i <input.json> -p <output_prefix>`
- `python tools/scripts/xbs_tool.py import-fix -i <input.xbs|input.json> -o <fixed.json> [--to-xbs <fixed.xbs>] [--report <fix_report.json>]`
- `python tools/scripts/xbs_tool.py check-editor -i <input.json>`
- `python tools/scripts/xbs_tool.py simulate-live -i <input.xbs|input.json> --engine auto --webview-timeout 25 --keyword 都市 --book-index 0 --chapter-index 0 --report <simulate_report.json>`
- `python tools/scripts/xbs_tool.py simulate-fixture -i <input.xbs|input.json> --engine auto --webview-timeout 25 --fixtures <fixtures_dir_or_map> --report <simulate_fixture_report.json>`
- `python tools/scripts/xbs_tool.py profile -i <input.json> -o <editor_safe.json> --profile editor_safe`
- `python tools/scripts/xbs_tool.py build-ab -i <input.json> -d <out_dir> --prefix <name> --to-xbs`
- `python tools/scripts/xbs_tool.py normalize-2561 -i <json_or_dir> --rebuild-xbs --report <report.json>`
- Note: `json2xbs/roundtrip` auto-run schema guard; conversion aborts on schema mismatch.
- `simulate-live/simulate-fixture` auto-run `import-fix -> schema_check -> editor_check -> 4-step simulation`:
  - steps: `searchBook/bookDetail/chapterList/chapterContent`
  - engine: `auto|http|webview`（默认 `auto`）
  - pass gate: four steps all pass
  - anti-bot (`403/429/challenge`) returns `blocked` (not parser fail)
- If absolutely needed, bypass with `--skip-schema-check` (not recommended for delivery artifacts).
- Windows 开箱即用约束（新增）：
  - 默认 runner 优先级：
    1) `XBSREBUILD_BIN`
    2) 内置 `tools/bin/windows/xbsrebuild.exe`
    3) PATH
    4) `XBSREBUILD_ROOT` + `go run`
    5) 同级 `../xbsrebuild` + `go run`
    6) 内置 `tools/vendor/xbsrebuild` + `go run`
  - Windows 默认无需 Go（内置 EXE 可直接转换）
  - 默认不依赖外部同级仓；即使没有 `../xbsrebuild`，也可回退到仓内 vendored 源码。
  - 可选入口：
    - CMD：`json2xbs.cmd / xbs2json.cmd / roundtrip_check.cmd`
    - PowerShell：`json2xbs.ps1 / xbs2json.ps1 / roundtrip_check.ps1`
  - 首次排障先跑：`python tools/scripts/xbs_tool.py doctor`

Fallback:

- `xbsrebuild xbs2json/json2xbs`
- Python fallback implementing XXTEA + appended plain-length tail

XXTEA details are documented in [references/xbs-xxtea-format.md](references/xbs-xxtea-format.md).

## Step 5: Output Contract

When delivering results, always provide:

- absolute path to JSON
- absolute path to XBS
- SHA256 of XBS
- simulate report path and verdict (`pass/fail/blocked`)
- runtime engine evidence (`steps.*.runtime_engine`)
- for WebView sources: include `steps.*.webview_trace` summary (navigation/injection/filter/failure)
- 保存回归结论（不改保存 / 改名保存 / 改字段保存）
- brief debug note if any compatibility workaround was applied
- schema check result (`PASS/FAIL`) and command used.

## Do/Don't

Do:

- Keep `enable` as numeric `1/0`.
- Keep `weight` as string integer (recommend `\"9999\"` for highest priority).
- Set `lastModifyTime` as Unix seconds string (not date text), e.g. `"1772463417"`.
- Keep rules minimal and testable.
- Verify with at least one real query and one real chapter.
- For chapter pagination, verify at least two chapter samples:
  - one truly paged chapter (should continue to `_1`, etc.)
  - one non-paged chapter (must stop, no fake `_1`)
- For media links in chapter content, return object with dynamic headers when required:
  - `{"url": result, "httpHeaders": {...}}`

Don't:

- Keep legacy callback fields by default (`requestJavascript`, `responseJavascript`, `requestFunction`, `responseFunction`), unless required for old-client compatibility.
- Assume `.//` behaves correctly in app runtime.
