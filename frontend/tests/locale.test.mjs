import assert from "node:assert/strict"
import test from "node:test"
import { resolveLocale } from "../src/locale.ts"

const cases = [
  ["Simplified Chinese", ["zh-CN"], "zh-CN"],
  ["Traditional Chinese", ["zh-TW"], "zh-TW"],
  ["Hong Kong Chinese", ["zh-HK"], "zh-TW"],
  ["Macao Chinese", ["zh-MO"], "zh-TW"],
  ["Singapore Chinese", ["zh-SG"], "zh-CN"],
  ["unspecified Chinese", ["zh"], "zh-CN"],
  ["Simplified script takes precedence over region", ["zh-Hans-TW"], "zh-CN"],
  ["Traditional script takes precedence over region", ["zh-Hant-CN"], "zh-TW"],
  ["mixed case", ["ZH-hANT-hk"], "zh-TW"],
  ["Unicode extensions", ["zh-TW-u-nu-hanidec"], "zh-TW"],
  ["English region", ["en-GB"], "en"],
  ["first supported preference wins", ["fr-FR", "zh-TW", "en"], "zh-TW"],
  ["English keeps its preference priority", ["en-US", "zh-TW"], "en"],
  ["unsupported languages fall through", ["ja-JP", "fr-FR", "zh-CN"], "zh-CN"],
  ["Zhuang must not match the Chinese prefix", ["zha", "en-US"], "en"],
  ["an unrelated language must not match the English prefix", ["enochian", "zh-TW"], "zh-TW"],
  ["Mandarin alias is canonicalized", ["cmn-Hant"], "zh-TW"],
  ["a variant is not a script", ["zh-hantfoo"], "zh-CN"],
  ["invalid subtag order is skipped", ["zh-TW-Hans", "en"], "en"],
  ["underscores are not locale separators", ["en_US", "zh-TW"], "zh-TW"],
  ["incomplete language tag is skipped", ["zh-", "en"], "en"],
  ["empty and malformed preferences are skipped", ["", "not_a_locale", "zh-TW"], "zh-TW"],
  ["no preferences defaults to English", [], "en"],
  ["no supported preferences defaults to English", ["ja-JP", "fr"], "en"],
]

for (const [name, languages, expected] of cases) {
  test(name, () => assert.equal(resolveLocale(languages), expected))
}
