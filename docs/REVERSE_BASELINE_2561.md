# StandarReader 2.56.1 逆向基线映射（并入 xiangseSkill）

更新时间：`2026-07-05`  
适用范围：`/Users/mantou/Documents/idea/xiangseSkill` 规则与工具链（文档 + 校验器 + 转换入口）

## 0. 当前 IPA 样本（仓库内置）

- App 包：`Tg@TrollstoreKios.app/`
- 主二进制：`Tg@TrollstoreKios.app/Tg@TrollstoreKios`（Mach-O arm64）
- 显示名：`香色闺阁Plus`（`CFBundleDisplayName`）
- 内部名：`StandarReader`（`CFBundleName`）
- 版本：`2.56.1`（`CFBundleShortVersionString` / `CFBundleVersion`）
- Bundle ID：`com.appbox.StandarReader0.7V6RKTCVR2.T43C7793Q3`
- 书源导入类型：`xsreader.config.xbs`（扩展名 `.xbs`），同族还有 `.xts`（排版）、`.xms`（主题）
- 编辑器字段元数据：`Tg@TrollstoreKios.app/lpnet_modelInfo`（XBS，可用 `tools/scripts/decode_xbs.py` 解包）

复现命令（本仓路径）：

```bash
plutil -p Tg@TrollstoreKios.app/Info.plist
strings Tg@TrollstoreKios.app/Tg@TrollstoreKios | rg "actionID|parserID|requestInfo|webView"
python3 tools/scripts/decode_xbs.py Tg@TrollstoreKios.app/lpnet_modelInfo
```

## 1. 证据来源与分级

主证据文件（3.3 逆向产物）：

- `/Users/mantou/Documents/idea/3.3/analysis/standarreader_2.56.1_reverse_ground_truth.md`
- `/Users/mantou/Documents/idea/3.3/analysis/standarreader_2.56.1_reverse_summary.json`
- `/Users/mantou/Documents/idea/3.3/analysis/reverse_inventory.md`
- `/Users/mantou/Documents/idea/3.3/analysis/hook_inventory.json`
- `/Users/mantou/Documents/idea/3.3/analysis/reverse_class_methods.json`

证据分级：

- `已实锤`：可由二进制符号、字符串或可解析配置直接复现。
- `高可信推断`：多处证据一致，但无单点强制约束证明。
- `待动态验证`：静态层无法确定运行时是否强制执行。

## 2. SDK / 内置 Tools 清单（并入后基线）

### 2.1 系统链接库（已实锤）

关键依赖（节选）：

- `Foundation/UIKit/WebKit/JavaScriptCore/SystemConfiguration/Security`
- `CoreFoundation/CoreGraphics/CoreImage/CoreMedia/CoreText/QuartzCore`
- `libsqlite3/libxml2/libz/libiconv`
- 注入链相关：`MikeCrack.dylib`、`Tg@TrollstoreKios.dylib`、`Tg@TrollstoreMios.dylib`、`SideloadMikepass1.dylib`、`SideloadMikepass2.dylib`

### 2.2 Pods 组件（已实锤）

- `AFNetworking`
- `FMDB`
- `MJRefresh`
- `SDWebImage` / `SDWebImageWebPCoder`
- `SSZipArchive`
- `XMLDictionary`
- `Masonry`
- `MBProgressHUD`
- `VIMediaCache`

### 2.3 业务工具类与职责映射

- `LCJSTool`：JS 侧工具能力（XPath、AES/Base64、Cookie、文件、日志）。
- `DomModelParser`：规则执行核心（requestInfo 组装、response 解析、DOM/JSONPath 取值）。
- `LPNetWork1/LPNetWork2`：请求层与响应处理（序列化、缓存键、回调格式化、HTML 清洗）。
- `BookQueryManager`：动作路由（search/detail/chapter/content）与结果回传。
- `BookSourceManager`：多源并发调度、失败/空结果管理、搜索生命周期控制。

结论：`xiangseSkill` 的动作骨架和字段模型（`actionID/parserID/requestInfo/responseFormatType/moreKeys`）与 2.56.1 主链路一致（`已实锤 + 高可信推断`）。

## 3. 规则引擎真值表（lpnet_modelInfo 基线）

`lpnet_modelInfo` 可配置键（已实锤）：

- `actionID`
- `moreKeys`
- `requestFunction`
- `requestJavascript`
- `requestParamsEncode`
- `responseDecryptType`
- `responseEncode`
- `responseFormatType`
- `responseFunction`
- `responseJavascript`
- `testConfig`
- `testRegex`

### 3.1 responseFormatType（已实锤）

- `""`（普通字符串）
- `base64str`
- `html`
- `xml`
- `json`
- `data`

### 3.2 responseDecryptType（已实锤）

- `""`（无需解密）
- `encryptType1`

### 3.3 其他编码枚举（已实锤）

- `requestParamsEncode`：`""(utf-8)`、`2147485234(gbk)`
- `responseEncode`：`""(utf-8)`、`2147485232(gb2312)`、`2147485234(gbk)`

### 3.4 占位符（已实锤）

- `%@result`
- `%@keyWord`
- `%@pageIndex`
- `%@offset`
- `%@filter`

### 3.5 样本统计（391 份 sourceModelList 快照）

- `parserID`：`DOM 3448`、`JS 56`
- `responseFormatType`：`html 1067`、`json 256`、`"" 2`、`xml 1`
- `bookWorld` 结构：`named_category_map 391`
- `weight` 类型：`str 388`、`int 3`
- `enable` 类型：`int 378`、`str 10`、`bool 3`

## 4. 加解密能力边界

### 4.1 原生层（已实锤）

- CommonCrypto：`_CCCrypt/_CCCryptorCreate/_CCCryptorUpdate`
- 摘要：`_CC_MD5/_CC_SHA1`
- `LCJSTool dataByAesDecryptWithBase64String:withKey:withIv:`
- `LCJSTool base64Encode:/base64Decode:`

### 4.2 JS 层（已实锤）

- `crypto.min.js` 存在
- `CryptoJS` 能力覆盖：`AES/DES/TripleDES/RC4/Rabbit/MD5/SHA1/SHA256`

### 4.3 规则引擎可配置解密入口（已实锤）

- 当前仅见：`responseDecryptType=encryptType1`

结论：

- 原生层可稳定覆盖常见 AES/MD5/SHA1/Base64。
- 更复杂站点解密通常走 `requestInfo` / 字段 `||@js` / `encryptType1` 协同（高可信推断）。

## 5. Hook / 注入链与可疑点

### 5.1 注入链（已实锤）

- 主程序直链：`MikeCrack.dylib`、`Tg@TrollstoreKios.dylib`、`Tg@TrollstoreMios.dylib`、`SideloadMikepass1/2.dylib`
- 相关依赖：`libsubstrate.dylib`、`libsubstitute.dylib`

### 5.2 可疑 Hook 点（已实锤）

- `_MSHookClassPair`
- `_MSHookFunction`
- `_MSHookMessageEx`
- `_substitute_hook_objc_message`
- `_substitute_hook_functions`
- `_substitute_dlopen_in_pid`
- `sandbox_check`

### 5.3 可疑 URL（已实锤）

- `https://commonconfig.oss-accelerate.aliyuncs.com/xsreader/xsreader.2.56.0`
- `https://www.baidu.com/s?word=%@`
- `https://itunes.apple.com/app/id%@`
- `https://audio_test.mp3`
- `https://video_test.mp4`
- `http://vjs.zencdn.net/v/oceans.mp4`
- `http://f3.htqyy.com/play9/5/mp3/6`
- `https://commonres.cdn.bcebos.com/normal/404.jpeg`

注：远程 `xsreader` 对象是否存在二次解密链，当前归类 `待动态验证`。

## 6. 与 xiangseSkill 规则主张对照矩阵

| ID | 规则主张 | 结论 | 处理建议 | 证据 |
|---|---|---|---|---|
| C01 | 四核心动作必须存在（search/detail/list/content） | 确认 | 保持硬约束 | E08 |
| C02 | `bookWorld` 使用分类 map（非数组） | 确认 | 保持硬约束 | E12 |
| C03 | `weight` 必须字符串 | 需放宽 | 改为归一化建议 + 警告 | E09 |
| C04 | `enable` 必须整型 1/0 | 需放宽 | 改为归一化建议 + 警告 | E09 |
| C05 | `responseFormatType` 仅 html/json/xml/text | 需补充 | 补齐 `""/base64str/data` | E05,E10 |
| C06 | `responseDecryptType` 支持 `encryptType1` | 确认 | 加入枚举白名单 | E05,E04 |
| C07 | 禁止 `method:/data:/headers:/java.getParams()` | 需分级 | `java.getParams` 仍错误；其余默认警告，可 strict 升级为错误 | E12 |
| C08 | 支持 `%@result/%@keyWord/%@pageIndex/%@offset/%@filter` | 确认 | 在规范文档明确保留 | E04 |
| C09 | `chapterContent.nextPageUrl` 必须同章守卫 | 待动态验证 | 继续作为强实践建议，不作为静态硬错误 | E11 |
| C10 | `requestInfo` 优先 `@js:` | 高可信推断 | 保持推荐项，不做硬挡 | E10 |

矩阵汇总：

- `确认`：动作骨架、bookWorld map、占位符、`encryptType1`
- `需放宽`：`weight/enable` 输入多态
- `需补充`：`responseFormatType`、`responseDecryptType` 枚举
- `待动态验证`：`nextPageUrl` 同章守卫是否客户端强制

## 7. 复现命令与证据编号

- E01：`otool -L Tg@TrollstoreKios`
- E02：`strings | rg PodsDummy_`
- E03：`nm -u | rg CCCrypt|CC_MD5|CC_SHA1`
- E04：`strings | rg actionID|parserID|requestInfo|responseFormatType|...`
- E05：`xbs_tool.py xbs2json -i lpnet_modelInfo -o /tmp/lpnet_modelInfo.json`
- E06：`nm -gU Tg@TrollstoreMios.dylib | rg MSHook|sandbox`
- E07：`nm -gU libsubstrate.dylib | rg MSHook|substitute_hook`
- E08-E12：`/private/tmp/sourceModelList.from_xbs.json` 统计结论

推荐直接使用 `/Users/mantou/Documents/idea/3.3/analysis/standarreader_2.56.1_reverse_summary.json` 作为机器可读证据索引。

## 8. 2026-07-05 复扫增量（仓库内置 `Tg@TrollstoreKios.app`）

### 8.1 新增/补全字段

| 字段 | 结论 | skill 处理 |
|---|---|---|
| `webViewSkipUrlsUnless` | 主二进制字符串存在；为 skip 规则白名单覆盖 | 写入 WebView 基线与 workflow skill |
| `webViewSniff` | 存在；配套 `arrWebViewSniff`、`canLoadUrl:fromSniff:` | 标注为高级选项，默认优先 HTTP/API |
| `wkwebview_post` | WebView 内置 form POST 辅助函数 | 挑战页/登录页二次提交可用 |
| `loginUrl` / `loginWebView` | 登录动作链路存在 | 仅登录型站点按需配置 |
| `miniAppVersion` | 顶层可选字段（历史源常见） | 交付可不写；写了也不阻断 |

### 8.2 解析类与调用链（静态符号）

- `DomModelParser`
  - `getRequestInfoForConfig:parserParams:error:`
  - `valueForNode:config:rule:ruleKey:userInfo:removeHtml:`
  - `valueForNode:jsonPath:`
- `BookQueryManager`
  - `queryByActionID:book:queryInfo:sourceName:userInfo:target:notify:cachePolicy:`
- `LPNetWork2`
  - `startWithUrl:requestInfo:config:userInfo:`
  - `requestWithUrl:requestInfo:config:userInfo:`
- `LCJSTool`
  - `base64Encode:` / `base64Decode:`
  - `md5Encode:` / `sha1Encode:`
  - `dataByAesDecryptWithBase64String:withKey:withIv:`
  - `cookieByKey:` / `searchWithXPathQuery:`

### 8.3 内置模板与远程配置

- 包内引用：`sourceModelList.xbs`、`xsBookSource.xbs`、`sourceModelTemplate`
- 远程对象：`https://commonconfig.oss-accelerate.aliyuncs.com/xsreader/xsreader.2.56.0`
  - 可下载，但不是标准 XBS 长度对齐格式；不要把它当书源模板直接解包

### 8.4 skill 同步清单（本次已完成）

- `skills/local/xiangse-booksource.SKILL.md`：新增「IPA 逆向基线」整节
- `skills/global/xbs-booksource-workflow.SKILL.md`：新增 IPA 真值表 + WebView 键补全
- `docs/REVERSE_WEBVIEW_BASELINE_2561.md`：补 `webViewSkipUrlsUnless` / `webViewSniff` / `wkwebview_post`
- `tools/scripts/decode_xbs.py`：Go 工具不可用时的 XBS 解包回退

### 8.5 动态验证执行结果（2026-07-05）

执行报告：`tools/verification/VERIFICATION_RUN_2026-07-05.json`

| 项目 | 结果 | 说明 |
|---|---|---|
| IPA 静态基线核对 | PASS | `python3 tools/scripts/verify_ipa_baseline.py` |
| `lpnet_modelInfo` 解包 | PASS | 枚举与 skill 一致 |
| 四步 fixture 模拟 | PASS | 样本源 `雪飞阁` + `tools/verification/fixtures/xuefeige/` |
| 四步 live 模拟 | FAIL | 目标站 TLS/网络不可用（环境限制，非 parser 逻辑错误） |
| Python XBS 往返 | PASS | `decode_xbs.py --encode` 生成 `xuefeige_fixed.xbs` 并可回解 |
| Frida 动态 Hook | SKIPPED | 当前无 USB iOS 设备；脚本已就绪：`tools/scripts/frida_dommodel_trace.js` |

本轮修复：

- `xbs_tool.py`：`simulate-fixture --fixtures` 改为传绝对路径（修复相对路径在 validator cwd 下找不到 fixture）
- `decode_xbs.py`：新增 `--encode`，在 macOS `go run` 因 `dyld LC_UUID` 崩溃时仍可 json2xbs

复现命令：

```bash
python3 tools/scripts/verify_ipa_baseline.py
python3 tools/scripts/xbs_tool.py simulate-fixture \
  -i tools/verification/xuefeige_fixed.json \
  --fixtures tools/verification/fixtures/xuefeige \
  --report tools/verification/xuefeige_fixed.fixture.simulate.json
python3 tools/scripts/decode_xbs.py --encode tools/verification/xuefeige_fixed.json tools/verification/xuefeige_fixed.xbs
```
