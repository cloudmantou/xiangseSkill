# 香色书源实战 Skill

## IPA 逆向基线（StandarReader 2.56.1）

本 skill 的规则以仓库内置 App 包静态逆向为真值来源：

- 样本：`Tg@TrollstoreKios.app/`（`香色闺阁Plus` / `StandarReader 2.56.1`）
- 主二进制：`Tg@TrollstoreKios.app/Tg@TrollstoreKios`
- 字段枚举真值：`Tg@TrollstoreKios.app/lpnet_modelInfo`（XBS）
- 详细证据：`docs/REVERSE_BASELINE_2561.md`、`docs/REVERSE_WEBVIEW_BASELINE_2561.md`

解包/打包 XBS（Go 工具不可用时的 Python 回退）：

```bash
python3 tools/scripts/decode_xbs.py Tg@TrollstoreKios.app/lpnet_modelInfo
python3 tools/scripts/decode_xbs.py --encode <source.json> <output.xbs>
```

IPA 基线自动核对：

```bash
python3 tools/scripts/verify_ipa_baseline.py
```

Mac 本机已安装 App 时（`/Applications/香色闺阁.app`，StandarReader 2.56.1）优先用本地集成脚本，不依赖 USB：

```bash
python3 tools/scripts/mac_xiangse_app.py status
python3 tools/scripts/mac_xiangse_app.py launch
python3 tools/scripts/mac_xiangse_app.py import <source.xbs>
python3 tools/scripts/mac_xiangse_app.py decode-sources -o /tmp/mac_sourceModelList.json
python3 tools/scripts/mac_xiangse_app.py prune-sources --remove-prefix "错层小说网-"
python3 tools/scripts/mac_xiangse_app.py verify-binary
```

说明：
- 可直接 `open -a 香色闺阁` 启动，并用 `open -a 香色闺阁 <file.xbs>` 触发导入。
- 沙盒书源真值文件：`~/Library/Containers/<id>/Data/Library/appdata/sourceModelList.xbs`（`decode-sources` 会自动定位）。
- **导入是合并，不是替换**：`open -a 香色闺阁 <file.xbs>` 会把新书源追加进 `sourceModelList.xbs`，不会自动删旧版。App 运行时导入还可能把内存里的旧规则写回沙盒。
- **同名书源陷阱**：多个 alias 共用同一 `sourceName` 且都 `enable=1` 时，目录请求走 `queryCatalogByBook:sourceName:`，会随机命中旧规则。迭代书源后必须 **prune 旧 alias**，沙盒里同一站点只留一条最新版。
- **推荐写入顺序**：先 `osascript -e 'tell application "香色闺阁" to quit'`，再 `prune-sources`，再合并写入（或 `import` 后立即 `decode-sources` 验收只剩一条）。
- Mac 版 iOS 兼容进程默认拒绝 Frida 附加（`unable to access process ... from the current user account`）；动态 hook 需另开调试授权或改走 USB 真机。

### App 选型（勿混用）

| App | 用途 |
|---|---|
| `Tg@TrollstoreKios.app` / Mac `香色闺阁.app` | **香色书源唯一真值**（StandarReader 2.56.1） |
| `SourceRead.app`（源阅读） | Legado 分支，`org.jsoup` / `ruleToc`，**不能验证 XBS** |

仓库内 `SourceRead.app/browserSource.json` 是通用浏览器导航源，与香色 `{alias: {searchBook, chapterList...}}` schema 无关。逆向、模拟、导入验收一律以 `Tg@TrollstoreKios.app` 为准。

USB iOS 设备动态 Hook（备选）：

```bash
frida -U -n StandarReader -l tools/scripts/frida_dommodel_trace.js
```

### 客户端骨架（已实锤）

顶层导入格式：`{ "<sourceAlias>": { ... } }`

必填顶层字段：`sourceName` / `sourceUrl` / `sourceType` / `enable` / `weight`

文本书源交付硬约束：`sourceType` 必须为 `"text"`（客户端还支持 `comic`/`video`/`audio`/`image`，本仓不交付这些类型）。

四大核心动作（`BookQueryManager.queryByActionID:` 路由）：

- `searchBook`
- `bookDetail`
- `chapterList`
- `chapterContent`

每个动作硬性字段：`actionID` / `parserID` / `requestInfo` / `responseFormatType`

扩展动作（二进制存在，按需可选）：`bookWorld`、`relatedWord`、`searchShudan`、`shudanDetail`、`shudanList`、`shupingList`、`shupingHome`、`loginUrl`/`loginWebView`

### `lpnet_modelInfo` 枚举（已解包）

- `responseFormatType`：`""` / `base64str` / `html` / `xml` / `json` / `data`
- `responseDecryptType`：`""` / `encryptType1`
- `requestParamsEncode`：`""`(utf-8) / `2147485234`(gbk)
- `responseEncode`：`""`(utf-8) / `2147485232`(gb2312) / `2147485234`(gbk)
- 占位符：`%@result` / `%@keyWord` / `%@pageIndex` / `%@offset` / `%@filter`

### 解析栈与字段语法（已实锤）

- `parserID`：`DOM`（主路径，`DomModelParser` + `TFHpple`）/ `JS`（纯 JS 响应解析）
- JSON 路径：`SMJJSONPath`（`valueForNode:jsonPath:`）
- 字段规则前缀：`@js:`、`@replace:`；链式写法：`字段 || @js:...`
- `list` 子字段 XPath：客户端对相对上下文不稳定，统一用 `//...`（禁用 `./` / `.//`）
- `moreKeys` 常见键：`requestFilters`、`removeHtmlKeys`、`skipCount`、`pageSize`、`maxPage`

### `@js:` 运行时上下文（已实锤）

`requestInfo` 与字段 `@js` 统一使用：`config` / `params` / `result`

阶段语义：

- `requestInfo` 阶段：`result` = 上一级 URL 或 `nextPageUrl`
- 字段解析阶段：`result` = 当前字段上一层解析产物
- 分页推荐顺序：`params.lastResponse.nextPageUrl` → `result` → `params.queryInfo.url`
- 相对路径补全：优先 `params.responseUrl`，再回退 `config.host`

`requestInfo` 返回对象合法键（二进制 + 编辑器元数据）：

- `url`、`POST`、`httpParams`、`httpHeaders`
- `forbidCookie`、`forbidCache`、`cacheTime`
- `webView`、`webViewJs`、`webViewJsDelay`、`webViewSkipUrls`、`webViewSkipUrlsUnless`、`webViewSniff`

WebView 内置辅助：`wkwebview_post(path, charset, params)`（form POST 提交）

### 原生工具（`LCJSTool`，可在 `@js` 中间接使用）

- 编解码：`base64Encode` / `base64Decode`、`md5Encode`、`sha1Encode`
- 加解密：`dataByAesDecryptWithBase64String/Data`
- Cookie：`cookieByKey`、`cookiesByUrl`
- 文件：`readFile`、`writeFile`
- XPath：`searchWithXPathQuery`、`queryWithXPath`

### 目录动作真值（`chapterList`，已实锤）

- 路由：`queryCatalogByBook:sourceName:` → `chapterList` → 内部 `arrCatalog`（`cpTitle` / `cpIndex`）
- 识别字段：`title`、`url`、`detailUrl`、`list`（二进制字符串存在）
- **不存在** `chapterListUrl`：写在 `bookDetail` 的自定义键不会被 `queryInfo` 转发，目录 URL 必须在 `chapterList.requestInfo` 里用 `@js` 从 `params.queryInfo.url/detailUrl` 归一化
- `searchBook` 建议同时写 `url` 与 `detailUrl`（与 80zw 可用源一致），供后续动作回退

### TFHpple vs 校验器（JSDOM）

- **语义相反**：`list` 已到 `<a>` 时，App（TFHpple）要 `//text()` / `//@href`；JSDOM 校验器用同样写法会扫全页，`sample_item` 出现整页垃圾文本，但 `list_length` 仍可能 PASS
- 判定规则：**信 App / TFHpple，不信 fixture `sample_item` 的 title/url 样例**
- 调试「无目录」时：先看沙盒是否多条同名书源，再看 `requestInfo` 是否返回空 URL，最后才改 XPath

### `requestInfo` 反模式（目录空链高发）

- 禁用 `Object.assign({}, config.httpHeaders)` — `LCJSTool` 环境可能不支持，静默失败 → URL 空 → 无目录
- 禁用依赖 `chapterListUrl` 传目录入口 — 客户端不识别
- 优先模板：`return {'url': u, 'httpHeaders': config.httpHeaders}`，URL 从 `params.queryInfo.url || params.queryInfo.detailUrl || result || params.responseUrl` 回退
- 字段 `@js` 过滤 `//@href` 非必要不加；先裸取相对路径，客户端可补全

### 导入/编辑闪退守卫（已实锤）

- `weight` 必须为整数字符串（`-[__NSCFNumber length]`）
- `bookWorld` 必须用分类 map（`bookWorld.{分类名}`），禁止 `bookWorld.categories` 数组（`-[__NSArrayI allKeys]`）
- `enable` 交付目标 `1/0`；`responseFormatType` 小写枚举
- 遗留回调字段（`requestJavascript`/`responseJavascript` 等）默认不写；仅旧客户端兼容时启用

## 写源入口

从网站新建书源时，先加载：`skills/local/website-to-booksource.SKILL.md`（七步流水线 + `pipeline_new_source.py`）。

## 触发场景
- 维护香色闺阁书源（JSON/XBS）
- 章节列表能出标题但抓不到 `url/detailUrl`
- 书源命名与发布规范统一
- 需要把任务交给弱模型（如 Tare）执行
- 当前约束版本：仅香色闺阁（StandarReader）`2.56.1`

## 固定规则
1. `sourceName` 保持站点名与版本号语义，不追加公众号后缀。
   - 公众号信息统一写在交付备注区（`delivery_notes`）：`公众号:好用的软件站`。
2. `chapterList` 里即使 `list` 已经相对定位到章节节点（例如已到 `<a>`），`title/url/detailUrl` 也默认使用双斜杠写法：
   - `title: //text()`
   - `url: //@href`
   - `detailUrl: //@href`
3. 遇到“标题能出、链接为空”时，优先把 `text()` 改 `//text()`，把 `@href` 改 `//@href`。
4. 上述场景不要默认叠加 `//a/@href[1]` 与 `||@js`，除非已确认客户端无法补全相对链接。
5. 先保证“能取到链接”，再考虑“绝对化链接”。
6. `chapterContent.nextPageUrl` 必须做“同章分页守卫”：
   - 先取候选“右侧翻页位”（如 `prenext` 里的第二个 `span/a`）。
   - 仅当候选 URL 与当前 URL 的 `{bookId, chapterId}` 一致，且分页号严格递增时返回；
   - 命中“下一章/目录/详情”一律返回空。
7. 站点搜索若被外部域接管且结果链接加密（如 `toUrl/openUrl`）：
   - 不要默认接入外部加密链路做主搜索；
   - 优先用“分类页遍历 + 关键词过滤”做可用降级。
8. 目录接口若为 `index.php?action=loadChapterPage` 且按页返回章节：
   - 需防“越界页重复最后一页/短书重复第 1 页”；
   - `nextPageUrl` 不能仅按 `list.length > 0` 决定，需叠加 `chapterorder` 页范围校验（如每页 `1-100`、`101-200`）。
9. 17K 类加密正文站点必须做解密验收：
   - 当响应存在 `content[].encrypt=1` 时，禁止把“`title` 有值但 `content` 为空”判定为成功。
   - 需要明确记录“解密前片段/解密后片段”至少各 1 条样例。
10. 转换命令统一优先给跨平台入口：
   - `python tools/scripts/xbs_tool.py json2xbs -i <json> -o <xbs>`
   - `python tools/scripts/xbs_tool.py xbs2json -i <xbs> -o <json>`
   - `python tools/scripts/xbs_tool.py roundtrip -i <json> -p <prefix>`
   - 仅在用户明确是 macOS/Linux/bash 时，再给 `.sh` 版本命令。
   - Windows 默认无需 Go：优先使用仓库内置 `tools/bin/windows/xbsrebuild.exe`。
   - 默认不依赖外部同级 `../xbsrebuild` 仓库；缺失时自动回退到仓内 `tools/vendor/xbsrebuild`。
   - Windows 可选入口：
     - CMD：`json2xbs.cmd / xbs2json.cmd / roundtrip_check.cmd`
     - PowerShell：`json2xbs.ps1 / xbs2json.ps1 / roundtrip_check.ps1`
11. 转换前必须先过 schema 体检（硬门槛）：
   - `python tools/scripts/check_xiangse_schema.py <json>`
   - 若失败，先修 JSON 结构，再做 json2xbs。
   - `xbs_tool.py` 已默认内置此检查；失败会直接中断转换。
12. 严禁混入非香色 schema 字段与运行时：
   - 禁用：`bookSourceName/bookSourceUrl/bookSourceGroup/httpUserAgent`
   - 禁用：`java.getParams()`、`method:`、`data:`、`headers:`
   - 使用：`sourceName/sourceUrl/sourceType` + `config/params/result` + `POST/httpParams/httpHeaders`
13. `sourceType` 必须为 `"text"`（硬约束），不再接受 `0/text` 混用。
14. 遇到旧源导入失败时先走导入修复流水线：
   - `python tools/scripts/xbs_tool.py import-fix -i <input.xbs|input.json> -o <fixed.json> --to-xbs <fixed.xbs> --report <fix_report.json>`
   - 再执行：`check_xiangse_schema.py -> check-editor -> simulate-live -> json2xbs`
15. StandarReader 2.56.1 若出现“编辑保存闪退”，切换 `editor_safe` 兼容模式：
   - `python tools/scripts/xbs_tool.py check-editor -i <json>`
   - `python tools/scripts/xbs_tool.py profile -i <json> -o <editor_safe.json> --profile editor_safe`
   - `python tools/scripts/xbs_tool.py build-ab -i <json> -d <out_dir> --prefix <name> --to-xbs`
   - 若日志出现 `-[__NSCFNumber length]`，先检查 `weight` 是否被写成数字类型。
16. `weight` 必须使用整数字符串（例如 `"9999"`），默认 `"9999"`，禁止数字类型。
17. 需要批量修复历史书源时使用：
   - `python tools/scripts/xbs_tool.py normalize-2561 -i <json_or_dir> --rebuild-xbs --report <report.json>`
18. `editor_safe` 仅做字段降级，不改变香色顶层结构（仍保持 `{alias:{sourceName...}}`）。
19. 交付前必须跑真实模拟四步链路（不导入 App）：
   - `python tools/scripts/xbs_tool.py simulate-live -i <input.xbs|input.json> --engine auto --webview-timeout 25 --keyword 都市 --book-index 0 --chapter-index 0 --report <simulate_report.json>`
   - `simulation_verdict` 必须为 `pass`；若是 `blocked`，按风控阻断处理，不得误判为 parser 成功。
   - 若源使用 `webView/webViewJs/webViewJsDelay/webViewSkipUrls`，报告中必须出现：
     - `steps.*.runtime_engine`
     - `steps.*.webview_trace`（至少给摘要）

## 推荐模板
```json
"chapterList": {
  "list": "//div[@id='chapter-list']/a",
  "title": "//text()",
  "url": "//@href",
  "detailUrl": "//@href"
}
```

## 调试清单
1. **App 仍无目录但 simulate PASS**：`decode-sources` 看是否多条同名 `sourceName`；执行 `prune-sources` 只留最新 alias；删书架书重搜。
2. `listLengthOnlyDebug > 0` 但 `url` 为空：先把 `url/detailUrl` 改成 `//@href`。
3. `title` 正常、`url` 为空：把 `title` 从 `text()` 改为 `//text()` 再测。
4. `title` 正常、`url` 仍为空：检查是否误用全局 XPath（如 `//a/@href[1]`）。
5. `nextPageUrl` 有值但翻页失败：先确认该值是否相对于当前分页页面而非章节页面。
6. `nextPageUrl` 命中“下一章”导致跨章串文：给 `chapterContent.nextPageUrl` 增加“同章分页守卫”。
7. 分类第 2 页抓不到：先确认站点分页是 `/cat/2.html` 还是 `/cat/p-2.html`，不要猜路径。
8. 用了 SourceRead / Legado 规则或在校验器里纠结 `sample_item` 垃圾值：换香色 App + 信 `list_length` 与真机结果。

## 标杆样例：错层小说网（cuoceng，v0713 已验可用）

- 站点：`https://m.cuoceng.org/`
- URL 形态：详情 `/book/{uuid}.html`；全目录 `/book/chapter/{uuid}.html`（`#linkNext` 分页）；正文 `/book/{uuid}/{chapterUuid}.html`
- 搜索：Cloudflare 拦站内搜 → `searchBook` 降级「分类遍历 + `requestFilters.category`」
- 规则文件：`tools/verification/cuoceng_source.json` / `.xbs`
- 关键 `chapterList` 片段：

```json
"requestInfo": "@js: ... /book/{id}.html → /book/chapter/{id}.html; return {url, httpHeaders: config.httpHeaders}",
"list": "//div[@id='allchapter']//dd/a",
"title": "//text()",
"url": "//@href",
"detailUrl": "//@href"
```

- 交付前：`prune-sources --remove-prefix "<站点别名前缀>-"` 确保沙盒唯一

## 交付检查
- JSON 与 XBS 同步更新
- 交付备注包含：`公众号:好用的软件站`
- 编辑保存稳定性（2.56.1）：
  - 不改保存不闪退
  - 改名保存不闪退
  - 改 1 个规则字段后保存不闪退
- 模拟测试稳定性（导入前）：
  - `simulate-live` 四步均 pass
  - 若 blocked，备注中必须写明阻断原因（如 `403/challenge`）
  - WebView 源需附 `runtime_engine + webview_trace` 摘要
- 章节列表返回包含 `title + url + detailUrl`
- 若章节返回加密正文（如 `encrypt=1`），必须给出“解密成功且正文非空”的验证结论
- 分类功能不可缺失：`bookWorld` 与 `requestFilters` 两者都应提供；若站点限制无法提供，需在 `delivery_notes` 说明原因与降级策略
- 对 Windows/Termux 用户补充可直接运行命令，不要求用户手改脚本路径。
- Windows 首次排障先执行：
  - `python tools/scripts/xbs_tool.py doctor`
  - 需看到 `resolved_runner_source: builtin_windows_bin`（或显式 `XBSREBUILD_BIN`）。

## 弱模型（Tare）执行模式
1. 强制引用：`docs/TARE_USAGE_PLAYBOOK.md`
2. 强制单任务：`new_source / fix_source / convert_only` 三选一
3. 强制固定输出：仅允许返回手册中的 JSON 结构
4. 强制命令化交付：必须给可复制命令，不给“建议型段落”
5. 强制失败显式化：输入不足时只能返回 `status=need_input` + `missing[]`
6. 强制 schema 先行：返回结果里必须包含 `check_xiangse_schema.py` 的执行结论。
