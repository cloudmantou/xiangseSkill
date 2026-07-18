# Xiangse 2.56.1 JSON Contract

Use this contract for delivery JSON. It targets text sources only.

## Required top-level shape

Wrap one source in one stable alias. A delivery JSON/XBS artifact must contain exactly one alias; split multiple sources into separate artifacts so every packaged source receives the same validation:

```json
{
  "example-v1": {
    "sourceName": "Example-v1",
    "sourceUrl": "https://example.com/",
    "sourceType": "text",
    "enable": 1,
    "weight": "9999",
    "lastModifyTime": "1772463417",
    "searchBook": {
      "actionID": "searchBook",
      "parserID": "DOM",
      "responseFormatType": "html",
      "requestInfo": "@js:return {'url': config.host + 'search?q=' + encodeURIComponent(params.keyWord)};",
      "list": "//ul[@id='result']/li",
      "bookName": "//a/text()",
      "detailUrl": "//a/@href"
    },
    "bookDetail": {
      "actionID": "bookDetail",
      "parserID": "DOM",
      "responseFormatType": "html",
      "requestInfo": "%@result",
      "title": "//h1/text()",
      "cover": "//img[@class='cover']/@src",
      "desc": "//div[@class='intro']/text()"
    },
    "chapterList": {
      "actionID": "chapterList",
      "parserID": "DOM",
      "responseFormatType": "html",
      "requestInfo": "%@result",
      "list": "//div[@id='chapters']/a",
      "title": "//text()",
      "url": "//@href",
      "detailUrl": "//@href"
    },
    "chapterContent": {
      "actionID": "chapterContent",
      "parserID": "DOM",
      "responseFormatType": "html",
      "requestInfo": "%@result",
      "content": "//div[@id='content']/text()"
    }
  }
}
```

Replace every placeholder selector and URL with values proven against the target site.

## Field requirements

- `sourceType`: exactly `"text"`.
- `enable`: integer `1` or `0`.
- `weight`: positive integer string, normally `"9999"`.
- Each core action: object containing `actionID`, `parserID`, string `requestInfo`, and `responseFormatType`.
- Core actions: `searchBook`, `bookDetail`, `chapterList`, `chapterContent`.
- `parserID`: the app schema recognizes `DOM` and `JS`. The bundled validator currently executes `DOM` only; `JS` is reported as unsupported/blocked and cannot receive an automated pipeline pass.
- `responseFormatType`: one of `""`, `base64str`, `html`, `xml`, `json`, or `data`. Never use `text`.
- `responseDecryptType`: `""` or `encryptType1` only when verified.

The schema whitelist describes app-shaped data, not the validator's full execution ability. Automated live execution currently supports `DOM` with `html` or `json`; other schema-valid response formats remain an incomplete automation case.

## Request contract

Use `config`, `params`, and `result` in `@js:` rules.

Use these request object keys:

- `url`
- `POST`
- `httpParams`
- `httpHeaders`
- `forbidCookie`
- `forbidCache`
- `cacheTime`
- verified WebView keys when necessary

Do not use:

- `java.getParams()`
- `method`
- `data` or `body`
- `headers`
- Legado top-level keys such as `bookSourceName` or `bookSourceUrl`

## Editor compatibility

- Use a category map for `bookWorld`; never use `bookWorld.categories` as an array.
- Store `bookWorld.*.moreKeys.requestFilters` as the legacy string form. Non-string values are a high-risk editor-save input in 2.56.1.
- Prefer an empty string for optional `validConfig` unless a verified rule requires more.
- Keep JS compatible with the app's proven engine. Prefer `var` and ordinary functions; avoid optional chaining, nullish coalescing, and unverified browser globals.

Example string filter:

```text
category
玄幻::xuanhuan
都市::dushi
```

## XPath rules

For list child fields in this target, prefer the verified double-slash forms:

- `title`: `//text()`
- `url`: `//@href`
- `detailUrl`: `//@href`

Avoid `./` and `.//` in list children. Still inspect the actual App result: the validator's DOM implementation can differ from the app's parser.

## Decryption and WebView boundary

Do not infer official runtime APIs from files or strings found in the modified reverse sample.

- A bundled `crypto.min.js` does not prove `CryptoJS` is globally available to source rules in the official app.
- Do not assume `atob`, `CryptoJS`, `wkwebview_post`, `webViewSniff`, or LCJSTool methods work in a rule unless the official app runtime test demonstrates that exact path.
- Prefer a stable documented API response over copied WAF or challenge scripts.
- If decryption cannot be proven in live simulation and the official app, report `blocked` or `fail`.
