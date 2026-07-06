# 网站 → 香色书源（AI 标准流程）

## 何时触发

用户给出**网站 URL**或说「为这个站写书源 / 修书源 / 导入香色闺阁」，必须走本 skill。

依赖技能（按顺序加载）：

1. `skills/local/xiangse-booksource.SKILL.md`（香色 2.56.1 硬约束）
2. `skills/global/xbs-booksource-workflow.SKILL.md`（构建与调试细节）
3. 弱模型任务：`docs/TARE_USAGE_PLAYBOOK.md`

## 目标产物

交付必须同时给出：

- `<name>.json`（可编辑规则）
- `<name>.xbs`（可导入香色闺阁）
- `<name>.simulate.json`（四步模拟报告，`pass` 或明确 `blocked`）
- `delivery_notes`：`公众号:好用的软件站`

## 七步流水线（AI 必须按序执行）

### Step 0 — 输入包（不足则停止）

```text
site=https://example.com/
task_type=new_source|fix_source
keyword=都市
must_rules=<可选硬规则>
samples=<可选：四页 HTML 样本目录>
```

缺 `site` 且不是 `fix_source` → 只返回 `status=need_input`。

### Step 1 — 站点侦察（recon）

抓取并分析四类页面（可用 `pipeline_new_source.py fetch-samples`）：

1. 搜索页（或分类页作搜索降级）
2. 书籍详情页
3. 章节目录页
4. 章节正文页

判定主链路（只选一条，写入交付说明）：

| 信号 | 选择 |
|---|---|
| 页面内 `fetch('/api/...')` / 返回 JSON | **API-first**（`responseFormatType=json`） |
| 静态 HTML + 表格/列表 | **DOM**（`parserID=DOM`） |
| 正文靠 `document.writeln`/挑战页/强 JS | **WebView 回退**（最后手段） |

禁止：未见证据就默认 WebView；禁止混入安卓阅读 `java.getParams()` / `method:` / `data:`。

### Step 2 — 生成 JSON 规则

顶层：

```json
{ "<站点别名>": { "sourceName", "sourceUrl", "sourceType":"text", "enable":1, "weight":"9999", ... } }
```

四大动作必填：`searchBook` / `bookDetail` / `chapterList` / `chapterContent`

每动作必填：`actionID` / `parserID` / `requestInfo` / `responseFormatType`

写规则时强制：

- `list` 子字段 XPath 用 `//`（禁用 `./` `.//`）
- `chapterList` 的 `title/url/detailUrl` 默认 `//text()` / `//@href` / `//@href`
- `requestInfo` 优先 `@js:`，上下文只用 `config/params/result`
- `bookWorld` 用分类 **map**（`bookWorld.{分类名}`），禁 `categories` 数组
- `weight` 字符串、`enable` 整型 `1/0`
- 正文分页必须「同章守卫」（见 `xiangse-booksource` skill）

### Step 3 — Schema 体检（硬门槛）

```bash
python3 tools/scripts/check_xiangse_schema.py <source.json>
```

FAIL → 先修 JSON，禁止转 XBS。

### Step 4 — 模拟四步（导入前）

优先 fixture（有样本时）：

```bash
python3 tools/scripts/xbs_tool.py simulate-fixture \
  -i <source.json> \
  --fixtures <samples_dir> \
  --report <source>.fixture.simulate.json
```

再跑 live（真实网络）：

```bash
python3 tools/scripts/xbs_tool.py simulate-live \
  -i <source.json> --engine auto --webview-timeout 25 \
  --keyword 都市 --book-index 0 --chapter-index 0 \
  --report <source>.simulate.json
```

判定：

- `simulation_verdict=pass` → 可交付
- `blocked`（403/429/challenge）→ 备注阻断原因，不算 parser 写错
- `fail` → 回到 Step 2 修规则

### Step 5 — 转 XBS

```bash
python3 tools/scripts/pipeline_new_source.py package -i <source.json> -o <source>.xbs
```

（内部：`check_xiangse_schema` → `decode_xbs.py --encode` 或 `xbs_tool.py json2xbs`）

### Step 6 — Mac 本机导入（可选但推荐）

```bash
# 先退出 App，避免运行时导入把旧规则写回沙盒
osascript -e 'tell application "香色闺阁" to quit'

# 删掉同站点旧 alias（导入是合并，不会自动覆盖）
python3 tools/scripts/mac_xiangse_app.py prune-sources --remove-prefix "<站点别名前缀>-"

python3 tools/scripts/mac_xiangse_app.py import <source>.xbs
python3 tools/scripts/mac_xiangse_app.py decode-sources -o /tmp/mac_sourceModelList.json
```

验收：

- 新书源 alias 存在且 **同 `sourceName` 仅一条 `enable=1`**
- `chapterList.list/title/url` 与 JSON 一致
- 用户需 **删书架旧书重搜**（缓存可能绑旧目录）

勿用 `SourceRead.app`（源阅读/Legado）验 XBS；逆向真值见 `Tg@TrollstoreKios.app`。

### Step 7 — 一键流水线

```bash
python3 tools/scripts/pipeline_new_source.py run \
  -i <source.json> \
  --fixtures <samples_dir> \
  --keyword 都市 \
  --import-mac \
  --report-dir tools/verification/out
```

## AI 提问模板（复制即用）

```text
请按 skills/local/website-to-booksource.SKILL.md 执行。
site=https://www.example.com/
task_type=new_source
keyword=都市
must_rules=1) 章节 list 子字段 // 开头 2) 必须有 bookWorld 3) 交付 JSON+XBS+simulate 报告
```

## 交付 JSON（固定格式）

```json
{
  "status": "ok|need_input|blocked|fail",
  "site": "https://example.com/",
  "json_path": "/abs/path/source.json",
  "xbs_path": "/abs/path/source.xbs",
  "simulate_report": "/abs/path/source.simulate.json",
  "simulation_verdict": "pass|fail|blocked",
  "schema_check": "PASS|FAIL",
  "delivery_notes": "公众号:好用的软件站",
  "commands": ["..."],
  "missing": []
}
```

## 常见分支（AI 决策）

- 搜索 30 秒限流 → fixture 验证 + 交付备注限流
- 无站内搜索 → `searchBook` 降级为「分类遍历 + 关键词过滤」
- 加密正文 `encrypt=1` → 必须验证解密后正文非空
- 编辑保存闪退嫌疑 → `check-editor` + `profile editor_safe`
- Go `json2xbs` 崩溃 → `decode_xbs.py --encode`
- **simulate PASS 但 App 无目录** → 先 `decode-sources` 查同名 `sourceName` 叠版 → `prune-sources` → 用户删书重搜；勿信 JSDOM `sample_item` 垃圾值
- **详情页与目录页分离**（如 cuoceng：`/book/{id}.html` vs `/book/chapter/{id}.html`）→ 在 `chapterList.requestInfo` 做 URL 归一化，不要写 `chapterListUrl`
- **迭代多版 alias** → 每版用新后缀（`-v0713`），交付前 prune 旧版，禁止沙盒里多条同名共存

## 标杆案例：错层小说网（cuoceng）

已验可用：**错层小说网-v0713**（`tools/verification/cuoceng_source.json`）

| 页面 | URL |
|---|---|
| 详情 | `/book/{uuid}.html`（`#allchapter` 仅 3 章预览） |
| 全目录 | `/book/chapter/{uuid}.html`（约 500 章/页，`#linkNext`） |
| 正文 | `/book/{uuid}/{chapterUuid}.html` |

写源要点：

- `searchBook` 同时写 `url` + `detailUrl`
- `bookDetail.url` 保持详情页 URL（不是目录页）
- `chapterList` 克隆 80zw 子字段：`//text()` / `//@href`，`list` 收窄到 `//div[@id='allchapter']//dd/a`
- `requestInfo` 用 `config.httpHeaders`，禁 `Object.assign`
- 第二大脑记忆 tag：`xiangse,cuoceng,v0713`