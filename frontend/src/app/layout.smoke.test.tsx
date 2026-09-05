import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("root layout tolerates browser extension attributes on the html element", () => {
  const source = readFileSync(new URL("./layout.tsx", import.meta.url), "utf8");

  assert.match(source, /<html lang="zh-CN" suppressHydrationWarning>/);
});
