---
name: xbs-booksource-workflow
description: Build, repair, convert, and verify Xiangse/StandarReader 2.56.1 text book sources in JSON or XBS form. Use when Codex must create a source from a website, fix a broken source, validate Xiangse schema or XPath/JS rules, convert JSON and XBS, investigate empty search/detail/catalog/content results, or produce an import-ready artifact with live-network and official-app evidence.
---

# XBS Booksource Workflow

Build only text sources for Xiangse/StandarReader 2.56.1. Keep every validation layer explicit and fail closed.

## Load the references

- Read [references/xbs-2561-contract.md](references/xbs-2561-contract.md) before creating or changing JSON rules.
- Read [references/verification-and-delivery.md](references/verification-and-delivery.md) before running validation, packaging XBS, importing into an app, or reporting success.

## Preserve the evidence layers

Never collapse these layers into one claim:

1. **Modified reverse-engineering sample**: `Tg@TrollstoreKios.app/` contains injected or modified components. Use it only for static compatibility clues such as field names, strings, and decoded metadata. Never call it the official app or runtime proof.
2. **Fixture simulation**: saved-page replay tests parser behavior only. It does not prove navigation, cookies, anti-bot handling, WebView execution, or valid URL propagation.
3. **Live simulation**: proves the validator completed the four-step network chain at that moment. It does not prove the official app uses identical runtime semantics.
4. **Official app runtime**: the final acceptance layer. Confirm the app's provenance and exact version before calling it official. Import, search, open detail, load catalog, read content, and test editor saves in that app.

If the official app or its provenance is unavailable, report `blocked`; do not report a final pass.

## Follow the fail-closed workflow

### 1. Establish inputs

Identify the task as `new_source`, `fix_source`, or `convert_only`.

For a new source, require:

- the site root URL;
- a test keyword;
- real search, detail, catalog, and content URLs, or saved responses for those four distinct pages;
- the target official app version and how it will be verified.

For `.xbs` input, decode and normalize before editing:

```bash
python3 tools/scripts/xbs_tool.py import-fix \
  -i /abs/input.xbs \
  -o /abs/input.fixed.json \
  --report /abs/input.fix-report.json
```

Do not generate XBS during this normalization step.

### 2. Capture real samples

Do not call `fetch-samples` with only `--site`: the command requires explicit detail, catalog, and content URLs, and a search URL should also be supplied instead of relying on a guessed route.

Pass four verified URLs explicitly:

```bash
python3 tools/scripts/pipeline_new_source.py fetch-samples \
  --site https://example.com/ \
  --search-url 'https://example.com/search?q=%E9%83%BD%E5%B8%82' \
  --detail-url 'https://example.com/book/123' \
  --list-url 'https://example.com/book/123/chapters' \
  --content-url 'https://example.com/book/123/chapter/1' \
  -o /abs/samples/example \
  --keyword 都市
```

Open the manifest and confirm that all four URLs and bodies represent different semantic steps. Stop on placeholders, challenge pages, login walls, duplicate homepages, or guessed routes.

### 3. Write or repair JSON

Use the alias wrapper and all required fields from the contract reference. Keep the implementation small and evidence-based.
Each delivery JSON/XBS artifact must contain exactly one alias. Split multiple sources into separate artifacts so the validated source set and packaged source set are identical.

Do not:

- mix Legado/Android fields or `java.getParams()` into Xiangse rules;
- use `method/data/headers` instead of `POST/httpParams/httpHeaders`;
- emit `responseFormatType: "text"`;
- use array/object `requestFilters` in a 2.56.1 delivery artifact;
- assume `CryptoJS`, `atob`, or a bundled script from the modified sample exists in the official rule runtime;
- invent WebView, pagination, decryption, or URL transformations without captured evidence.

### 4. Pass static gates

Run schema and editor checks before any simulation or packaging:

```bash
python3 tools/scripts/check_xiangse_schema.py --strict-requestinfo /abs/source.json
python3 tools/scripts/xbs_tool.py check-editor -i /abs/source.json
```

Stop on any failure. Resolve every high-risk editor finding. Record medium warnings for explicit official-app editor-save verification; the expected `NEW_SCHEMA_WRAPPER` warning cannot be cleared by static analysis alone. Use `--strict` only as a conservative triage mode, not as an impossible requirement that silently discards the required alias wrapper.

### 5. Run fixture parser tests

When saved samples exist, run fixture mode:

```bash
python3 tools/scripts/xbs_tool.py simulate-fixture \
  -i /abs/source.json \
  --fixtures /abs/samples/example \
  --engine auto \
  --webview-timeout 25 \
  --keyword 都市 \
  --report /abs/source.fixture.simulate.json
```

Treat this as a parser unit test only. Directory fixtures read each expected URL from `manifest.json` and fail when the generated request URL differs. If URL metadata is absent, the report contains `url_unverified`; inspect every selected item and propagated request URL. Fail the fixture gate if a URL is empty, contains multiple concatenated URLs, contains whitespace-separated paths, or does not match the expected next step.

Fixture success never authorizes packaging, import, or a final `pass`.

### 6. Pass the live four-step gate

Run the live chain against the real site:

```bash
python3 tools/scripts/xbs_tool.py simulate-live \
  -i /abs/source.json \
  --engine auto \
  --webview-timeout 25 \
  --keyword 都市 \
  --book-index 0 \
  --chapter-index 0 \
  --report /abs/source.live.simulate.json
```

Require `schema_check=PASS`, no blocking editor risk, `simulation_verdict.status=pass`, `overall_verdict.status=pass`, and successful `searchBook`, `bookDetail`, `chapterList`, and `chapterContent` steps.

Treat `blocked` as blocked, not pass. Treat WebView fallback or unsupported sniff/decryption behavior as incomplete evidence.
The current validator executes only `parserID: DOM` with `responseFormatType: html|json`. It reports JS parsers/hooks, pagination (`nextPageUrl` or `maxPage > 1`), other response formats, `webViewSniff`, and `webViewContentRules` as unsupported errors. It also blocks HTTP/JSDOM fallback when a requested Playwright WebView runtime is unavailable. These are automation capability gaps, not proof that the official App rejects the source; record the automated gate as incomplete/blocked and do not package it as a live pass.

### 7. Package only after live success

After reviewing the live report, package and round-trip:

```bash
python3 tools/scripts/pipeline_new_source.py package \
  -i /abs/source.json \
  -o /abs/source.xbs

python3 tools/scripts/xbs_tool.py roundtrip \
  -i /abs/source.json \
  -p /abs/source.verify
```

Compare the round-tripped source semantically and record the XBS SHA-256.

`pipeline_new_source.py run --live` is a fail-closed automated convenience gate: it stops before packaging when schema, editor, fixture, or live validation fails. Its `PIPELINE_STATUS: pass` still is not a final delivery pass because the command does not execute the official-app interaction checklist. Treat `--import-mac` only as an artifact handoff; it is not official-app runtime evidence. Mac handoff also requires `--app-source-backup /new/backup/path.xbs`; the tool refuses a running App and refuses to overwrite an existing backup.

### 8. Verify in the official app

Confirm the runtime target is an official, unmodified StandarReader 2.56.1 build. Keep its identity/provenance in the delivery evidence.

Before import:

1. Quit the App completely.
2. Locate `sourceModelList.xbs`, record its SHA-256, and create a new non-overwriting backup. The Mac import command requires `--backup`; `prune-sources` also requires a backup and refuses to run while the App is open.
3. Only after that backup exists, remove or disable stale aliases for the same site. Never prune a live source list without a verified backup.
4. Open/import the XBS. A successful `open` call means only `IMPORT_REQUESTED`; confirm the import dialog and source-list change separately.

Then verify in the official app:

- import completes without a crash;
- only the intended enabled source/version is selected;
- keyword search returns the expected book;
- detail page fields are correct;
- catalog loads real chapter titles and links;
- at least one normal chapter and one pagination edge case render correctly;
- editor save succeeds unchanged, after renaming, and after one rule-field edit.

After a reversible smoke test, quit the App, restore the exact pre-test `sourceModelList.xbs`, verify the restored SHA-256 equals the recorded pre-test hash, relaunch once to confirm it remains stable, and quit again. Keep the backup path and both hashes in the delivery record.

Do not substitute `Tg@TrollstoreKios.app`, SourceRead/Legado, fixture output, or validator output for this layer.

### 9. Deliver with explicit status

Use these statuses:

- `need_input`: required URL, sample, source file, or official-app target is missing.
- `fail`: a schema, editor, fixture, live, roundtrip, or official-app check failed.
- `blocked`: anti-bot, authentication, unavailable official app, or unverifiable provenance prevents completion.
- `pass`: live simulation and official-app verification both passed, after packaging and roundtrip.

Include absolute paths to JSON, XBS, fixture/live reports, roundtrip output, XBS SHA-256, official-app evidence, exact commands, and any remaining warnings. Never emit `pass` with a blocked step or empty blocking reason.
