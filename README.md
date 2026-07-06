# xiangseSkill

香色闺阁（StandarReader 2.56.1）书源开发资料仓库，聚焦三件事：
- **AI + Skill 根据网站写书源**（网站 → JSON → 校验 → XBS → 导入 App）
- 书源格式转换（JSON <-> XBS）
- Codex 技能（skill）沉淀与实战规则维护

注意：本仓仅服务香色闺阁 2.56.1，不承担安卓阅读/跨客户端兼容目标。

## 视频与社群

- B站视频：
  [别再手写书源了！用 ChatGPT Codex 全自动转换香色闺阁书源（成功率90%）](https://www.bilibili.com/video/BV14JPrzxEd2/?share_source=copy_web&vd_source=13e2e41429e96311a744cc03ef2e7861)
- 公众号：好用的软件站

公众号二维码：

![公众号二维码](assets/wechat-official-account-qr.jpg)

- 微信群：香色闺阁自动写源群（扫码入群，二维码以最新版本为准，过期请联系更新）

微信群二维码：

![微信群二维码](assets/wechat-group-qr.jpg)

## 目录说明

- `tools/scripts/`: 转换脚本
  - `xbs_tool.py`（跨平台主入口，推荐）
  - `json2xbs.sh`
  - `xbs2json.sh`
  - `roundtrip_check.sh`
  - `json2xbs.cmd`（Windows）
  - `xbs2json.cmd`（Windows）
  - `roundtrip_check.cmd`（Windows）
- `skills/global/`: 通用技能
  - `xbs-booksource-workflow.SKILL.md`
- `skills/local/`: 项目约束技能
  - `website-to-booksource.SKILL.md`（**网站写源主入口**）
  - `xiangse-booksource.SKILL.md`
- `docs/`: 规则文档与维护记录

## 环境要求

- Python 3.9+
- Node.js 18+（`simulate-live/simulate-fixture` 需要，首次执行前运行 `cd tools/validator && npm install`）
- Go 1.22+（仅在命中源码 fallback 时需要）
- `xbsrebuild` 工具满足任意一种即可：
  - 设置 `XBSREBUILD_BIN` 指向可执行文件（Windows 可指向 `.exe`）
  - Windows 直接使用仓库内置 `tools/bin/windows/xbsrebuild.exe`（无需 Go）
  - `xbsrebuild` 已加入 `PATH`
  - 设置 `XBSREBUILD_ROOT` 指向 `xbsrebuild` 源码目录（脚本会自动 `go run`）
  - 使用仓库内置源码快照 `tools/vendor/xbsrebuild`（脚本自动兜底）

## 已内置引入 xbsrebuild（Vendor Snapshot）

为降低外部仓推送权限对日常使用的影响，本仓已内置 `xbsrebuild` 源码快照：
- 内置路径：`tools/vendor/xbsrebuild/`
- 上游仓库：[ne1llee/xbsrebuild](https://github.com/ne1llee/xbsrebuild)
- 当前同步基线：`5cd1249`
- 追溯文件：`tools/vendor/xbsrebuild/UPSTREAM_SOURCE.md`

默认会按以下顺序自动探测：
1. `XBSREBUILD_BIN`
2. 内置 Windows 二进制 `tools/bin/windows/xbsrebuild.exe`
3. `PATH` 中的 `xbsrebuild`
4. `XBSREBUILD_ROOT`
5. 仓库同级目录 `../xbsrebuild`
6. 仓库内置源码 `tools/vendor/xbsrebuild`

建议显式设置：

```bash
export XBSREBUILD_ROOT=/path/to/xbsrebuild
```

Windows PowerShell 建议：

```powershell
$env:XBSREBUILD_BIN="D:\tools\xbsrebuild.exe"
```

## AI 根据网站写书源（推荐流程）

Skill 入口：`skills/local/website-to-booksource.SKILL.md`

```bash
# 1) 抓四页样本（搜索/详情/目录/正文）
python3 tools/scripts/pipeline_new_source.py fetch-samples \
  --site https://www.example.com/ \
  -o tools/verification/samples/example \
  --keyword 都市

# 2) AI 根据样本写 <name>.json 后，一键验收+打包+导入 Mac 版香色闺阁
python3 tools/scripts/pipeline_new_source.py run \
  -i tools/verification/<name>.json \
  --fixtures tools/verification/samples/example \
  --live \
  --import-mac \
  --report-dir tools/verification/out

# 3) 查看 Mac App 书源列表
python3 tools/scripts/mac_xiangse_app.py decode-sources
```

给 AI 的提问模板（复制即用）：

```text
请按 skills/local/website-to-booksource.SKILL.md 执行。
site=https://www.example.com/
task_type=new_source
keyword=都市
```

## 书源转换用法

### 推荐（跨平台统一命令）

```bash
python tools/scripts/xbs_tool.py import-fix -i <input.xbs|input.json> -o <fixed.json> --to-xbs <fixed.xbs> --report <fix_report.json>
python tools/scripts/check_xiangse_schema.py <input.json>
python tools/scripts/xbs_tool.py check-editor -i <input.json>
python tools/scripts/xbs_tool.py simulate-live -i <input.xbs|input.json> --engine auto --webview-timeout 25 --keyword 都市 --book-index 0 --chapter-index 0 --report <simulate_report.json>
python tools/scripts/xbs_tool.py simulate-fixture -i <input.xbs|input.json> --engine auto --webview-timeout 25 --fixtures <fixtures_dir_or_map> --report <simulate_fixture_report.json>
python tools/scripts/xbs_tool.py doctor
python tools/scripts/xbs_tool.py json2xbs -i <input.json> -o <output.xbs>
python tools/scripts/xbs_tool.py xbs2json -i <input.xbs> -o <output.json>
python tools/scripts/xbs_tool.py roundtrip -i <input.json> -p <output_prefix>
```

说明：
- `import-fix` 用于旧源导入修复：自动补齐 `requestInfo/responseFormatType` 等导入硬字段并输出修复报告。
- `xbs_tool.py` 在 `json2xbs/roundtrip` 会自动执行 schema 检查并在失败时中断。
- `simulate-live` 会自动执行：`import-fix -> schema_check -> editor_check -> 四步真实请求模拟`。
  - 四步为：`searchBook / bookDetail / chapterList / chapterContent`。
  - `--engine` 支持：`auto|http|webview`（默认 `auto`）。
  - `--webview-timeout` 控制 WebView 执行超时（秒）。
  - 命中风控会给出 `blocked`（例如 `403/challenge`），与 parser 规则失败分开标记。
- 仅在你明确要跳过时使用：`--skip-schema-check`。

## 真实模拟测试（导入前验收）

```bash
python tools/scripts/xbs_tool.py simulate-live -i /abs/source.json --engine auto --webview-timeout 25 --keyword 都市 --report /abs/source.sim.report.json
```

报告核心字段：
- `schema_check`
- `editor_check`
- `simulation_verdict`
- `overall_verdict`
- `steps.searchBook/bookDetail/chapterList/chapterContent`
- `steps.*.runtime_engine`
- `steps.*.webview_applied_keys`
- `steps.*.webview_trace`

判定规则：
- `overall_verdict=pass`：结构、编辑兼容、四步模拟均通过，可进入导入阶段。
- `simulation_verdict=blocked`：站点风控阻断（非 parser 规则错误），需处理请求策略或延后重试。
- `simulation_verdict=fail`：规则解析链路失败，按步骤报告定位字段修复。

### macOS / Linux / Termux（兼容旧命令）

#### 1) JSON -> XBS

```bash
bash tools/scripts/json2xbs.sh <input.json> <output.xbs>
```

#### 2) XBS -> JSON

```bash
bash tools/scripts/xbs2json.sh <input.xbs> <output.json>
```

#### 3) 回转校验（推荐）

```bash
bash tools/scripts/roundtrip_check.sh <input.json> <output_prefix>
```

会生成：
- `<output_prefix>.xbs`
- `<output_prefix>.roundtrip.json`

### Windows（CMD）

```bat
tools\scripts\json2xbs.cmd <input.json> <output.xbs>
tools\scripts\xbs2json.cmd <input.xbs> <output.json>
tools\scripts\roundtrip_check.cmd <input.json> <output_prefix>
```

### Windows（PowerShell）

```powershell
python .\tools\scripts\xbs_tool.py doctor
python .\tools\scripts\xbs_tool.py json2xbs -i .\in.json -o .\out.xbs
```

## 如何正确使用我们的 skill

### 在 Codex 中触发

1. 安装/放置 skill 文件（到你的 Codex skills 目录）。
2. 在对话中明确点名 skill：

```text
请使用 $xbs-booksource-workflow 为 https://example.com 写香色闺阁书源。
```

如果需要项目内约束一起执行：

```text
请同时按 $xbs-booksource-workflow 和本仓库 local 规则实现并验证。
```

给普通用户的建议话术（可直接复制）：

```text
请使用 $xbs-booksource-workflow，按香色闺阁 2.56.1 专用流程输出：
1) 先给 JSON 规则
2) 再给 xbs_tool.py 转换命令
3) 最后给 roundtrip 校验命令和失败排查点
```

## Tare（弱模型）专用用法

如果使用 Tare 这类弱模型，不要直接让它“自由发挥”，请强制走固定协议：

1. 先让它读取：`docs/TARE_USAGE_PLAYBOOK.md`
2. 每次只给一个任务类型：`new_source / fix_source / convert_only`
3. 要求它只按“固定输出 JSON”返回结果
4. 强制先跑：`python tools/scripts/check_xiangse_schema.py <json>`

可复制提问模板：

```text
请严格按 /docs/TARE_USAGE_PLAYBOOK.md 执行。
task_type=fix_source
site=https://m.libahao.com/
input_file=/abs/path/libahao_source.json
target_file=/abs/path/libahao_source_fixed.json
must_rules=1) list 子字段 XPath 必须 // 开头 2) 去除空白污染 3) 分类 cover 不能为空
samples=（粘贴你的错误解析 JSON）
只允许输出固定 JSON，不要输出自由文本。
```

### 推荐工作流

1. 先抓站点四类页面样本：搜索、详情、目录、正文。
2. 先产出 JSON 规则，再执行 `roundtrip_check.sh`。
3. 用文档规则复核：
   - `docs/XBS_JSON_CODING_RULES.md`
   - `docs/MAINTENANCE_WORKFLOW.md`
4. 最后导出可导入的 XBS，并记录变更到 `docs/CHANGELOG.md`。

## 参考文档

- `docs/香色书源开发指南与工作流程.md`
- `docs/XBS_JSON_CODING_RULES.md`
- `docs/REVERSE_WEBVIEW_BASELINE_2561.md`
- `docs/RETROSPECT_LOG.md`
- `docs/TARE_USAGE_PLAYBOOK.md`
