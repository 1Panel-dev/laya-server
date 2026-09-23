export type Locale = "zh-CN" | "en" | "zh-TW"

export function resolveLocale(languages: readonly string[]): Locale {
  for (const language of languages) {
    let locale: Intl.Locale
    try {
      locale = new Intl.Locale(language)
    } catch {
      // Ignore malformed preferences and continue to the next supported language.
      continue
    }
    if (locale.language === "zh") {
      // An explicit script takes precedence over the region's usual script.
      if (locale.script) return locale.script === "Hant" ? "zh-TW" : "zh-CN"
      return ["TW", "HK", "MO"].includes(locale.region ?? "") ? "zh-TW" : "zh-CN"
    }
    if (locale.language === "en") return "en"
  }
  return "en"
}
