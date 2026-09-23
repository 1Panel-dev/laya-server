import { useEffect, useState, useSyncExternalStore, type FormEvent, type ReactNode } from "react"
import { Activity, BookOpen, ChartNoAxesColumn, CircleHelp, Copy, KeyRound, Languages, LogOut, Menu, Plus, Send, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { apiErrorMessage, useI18n, type Locale, type MessageKey, type Translate } from "./i18n"
import { Playground, sampleRequest, type Model } from "./Playground"
import { api, ApiError, getSession, setSession, subscribeSession, type Session } from "./api"

type ApiKey = { id: number; name: string; mask: string; created_at: string; revoked_at: string | null; last_used_at: string | null }
type Usage = { totals: { requests: number; input_tokens: number; output_tokens: number }; daily: { day: string; requests: number; input_tokens: number; output_tokens: number }[]; sources: { source: string; key_id: number | null; requests: number; input_tokens: number; output_tokens: number }[] }
type Page = "home" | "keys" | "usage" | "playground" | "docs"

const navigation: { id: Page; label: MessageKey; icon: typeof Activity }[] = [
  { id: "home", label: "home", icon: Activity },
  { id: "playground", label: "playground", icon: Send },
  { id: "usage", label: "usage", icon: ChartNoAxesColumn },
  { id: "keys", label: "apiKeys", icon: KeyRound },
  { id: "docs", label: "documentation", icon: BookOpen },
]

function displayError(error: unknown, t: Translate) {
  return apiErrorMessage(error instanceof ApiError ? error.code : undefined, t)
}

function loadAvailableModels(): Promise<{ models: Model[] }> {
  return api("/internal/models")
}

function useSession() {
  const session = useSyncExternalStore(subscribeSession, getSession)
  const [ready, setReady] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    api<Session>("/internal/auth/session", { signal: controller.signal })
      .then(value => { if (!controller.signal.aborted) setSession(value) })
      .catch(cause => {
        if (!controller.signal.aborted && cause instanceof ApiError && cause.status === 401) setSession(null)
      })
      .finally(() => { if (!controller.signal.aborted) setReady(true) })
    return () => controller.abort()
  }, [])
  return { session, setSession, ready }
}

function BrandLogo() {
  return <img className="brand-logo" src="/laya-server-logo-black.png" alt="" aria-hidden="true" />
}

function LanguagePicker() {
  const { locale, setLocale, t } = useI18n()
  return <label className="locale-picker"><Languages size={16} aria-hidden="true" /><span className="sr-only">{t("language")}</span><select aria-label={t("language")} value={locale} onChange={event => setLocale(event.target.value as Locale)}><option value="zh-CN">简体中文</option><option value="en">English</option><option value="zh-TW">繁體中文</option></select></label>
}

function Login({ onLogin }: { onLogin: (session: Session) => void }) {
  const { t } = useI18n()
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api("/internal/auth/login", { method: "POST", body: JSON.stringify({ username, password }) })
      onLogin(await api<Session>("/internal/auth/session"))
    } catch (cause) {
      setError(cause)
    } finally {
      setBusy(false)
    }
  }

  return <div className="login-shell"><div className="login-panel">
    <div className="login-panel-header"><div className="brand-mark"><BrandLogo /></div><LanguagePicker /></div>
    <h1>{t("loginTitle")}</h1><p>{t("loginDescription")}</p>
    <form onSubmit={submit}>
      <label htmlFor="username">{t("username")}</label>
      <Input id="username" autoComplete="username" value={username} onChange={event => setUsername(event.target.value)} required />
      <label htmlFor="password">{t("password")}</label>
      <Input id="password" type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} required />
      {error ? <div className="form-error" role="alert">{displayError(error, t)}</div> : null}
      <Button type="submit" disabled={busy} className="full-button">{busy ? t("signingIn") : t("signIn")}</Button>
    </form>
  </div></div>
}

function App() {
  const { t } = useI18n()
  const { session, setSession, ready } = useSession()
  const [page, setPage] = useState<Page>("home")
  const [mobileNav, setMobileNav] = useState(false)

  if (!ready) return <div className="loading">{t("loading")}</div>
  if (!session) return <Login onLogin={setSession} />

  async function logout() {
    try {
      await api("/internal/auth/logout", { method: "POST" }, session!.csrf_token)
      if (getSession() === session) setSession(null)
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) return
      alert(displayError(cause, t))
    }
  }

  const title = t(navigation.find(item => item.id === page)?.label || "home")
  return <div className="shell">
    <aside className={mobileNav ? "sidebar open" : "sidebar"}>
      <div className="brand"><div className="brand-mark"><BrandLogo /></div><span>LAYA SERVER</span><button className="mobile-close" aria-label={t("closeNavigation")} onClick={() => setMobileNav(false)}><X size={18} /></button></div>
      <nav>{navigation.map(item => <button key={item.id} className={page === item.id ? "nav-item active" : "nav-item"} onClick={() => { setPage(item.id); setMobileNav(false) }}><item.icon size={17} strokeWidth={1.8} /><span>{t(item.label)}</span></button>)}</nav>
      <div className="account"><div className="account-avatar">{session.username.slice(0, 1).toUpperCase()}</div><div className="account-name"><strong>{session.username}</strong><span>{t("administrator")}</span></div><button aria-label={t("signOut")} title={t("signOut")} onClick={logout}><LogOut size={17} /></button></div>
    </aside>
    <div className="main">
      <header className="topbar"><button className="menu-button" aria-label={t("openNavigation")} onClick={() => setMobileNav(true)}><Menu size={20} /></button><span>{title}</span><div className="topbar-controls"><span className="topbar-note">LAYA SERVER</span><LanguagePicker /></div></header>
      <main className="content">{page === "home" ? <Home setPage={setPage} /> : page === "keys" ? <Keys csrf={session.csrf_token} /> : page === "usage" ? <UsagePage /> : page === "playground" ? <Playground run={body => api("/internal/playground", { method: "POST", body }, session.csrf_token)} loadModels={loadAvailableModels} /> : <Docs />}</main>
    </div>
    {mobileNav ? <button className="nav-backdrop" aria-label={t("closeNavigation")} onClick={() => setMobileNav(false)} /> : null}
  </div>
}

function PageTitle({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <div className="page-title"><div><h1>{title}</h1><p>{description}</p></div>{action}</div>
}

function Home({ setPage }: { setPage: (page: Page) => void }) {
  const { t } = useI18n()
  const [keyCount, setKeyCount] = useState<number | null>(null)
  useEffect(() => { api<ApiKey[]>("/internal/api-keys").then(keys => setKeyCount(keys.filter(key => !key.revoked_at).length)).catch(() => {}) }, [])
  return <>
    <PageTitle title={t("homeTitle")} description={t("homeDescription")} />
    <div className="home-intro"><span className="intro-icon"><KeyRound size={22} /></span><h2>{keyCount ? t("activeKeyCount", { count: keyCount }) : t("createFirstKey")}</h2><p>{t(keyCount ? "homeWithKeys" : "homeWithoutKeys")}</p><Button onClick={() => setPage("keys")}>{t("manageKeys")}</Button></div>
    <div className="home-links"><button onClick={() => setPage("playground")}><Send size={19} /><strong>{t("tryPlayground")}</strong><span>{t("tryPlaygroundDescription")}</span></button><button onClick={() => setPage("docs")}><BookOpen size={19} /><strong>{t("viewDocs")}</strong><span>{t("viewDocsDescription")}</span></button></div>
  </>
}

function Keys({ csrf }: { csrf: string }) {
  const { t, locale } = useI18n()
  const [keys, setKeys] = useState<ApiKey[]>([])
  const [name, setName] = useState("")
  const [rawKey, setRawKey] = useState("")
  const [showCreate, setShowCreate] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const reload = () => api<ApiKey[]>("/internal/api-keys").then(setKeys).catch(setError)
  useEffect(() => { void reload() }, [])

  async function create(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const created = await api<{ key: string }>("/internal/api-keys", { method: "POST", body: JSON.stringify({ name }) }, csrf)
      setRawKey(created.key)
      setName("")
      setShowCreate(false)
      await reload()
    } catch (cause) {
      setError(cause)
    } finally {
      setBusy(false)
    }
  }

  async function revoke(key: ApiKey) {
    if (!confirm(t("revokeConfirm", { name: key.name }))) return
    try {
      await api("/internal/api-keys/" + key.id + "/revoke", { method: "POST" }, csrf)
      await reload()
    } catch (cause) {
      setError(cause)
    }
  }

  return <>
    <PageTitle title={t("apiKeys")} description={t("keysDescription")} action={<Button onClick={() => setShowCreate(true)}><Plus size={16} /> {t("createKey")}</Button>} />
    {error ? <div className="form-error" role="alert">{displayError(error, t)}</div> : null}
    {rawKey ? <div className="key-reveal"><div><strong>{t("saveKeyTitle")}</strong><p>{t("saveKeyDescription")}</p></div><div className="key-value"><code>{rawKey}</code><Button variant="outline" size="sm" onClick={() => navigator.clipboard.writeText(rawKey)}><Copy size={14} /> {t("copy")}</Button></div><button aria-label={t("closeKeyNotice")} onClick={() => setRawKey("")}><X size={18} /></button></div> : null}
    <div className="section-head"><h2>{t("keyList")}</h2><span>{t("keyCount", { count: keys.length })}</span></div>
    {keys.length === 0 ? <div className="empty"><KeyRound size={23} /><h3>{t("noKey")}</h3><p>{t("noKeyDescription")}</p><Button variant="outline" onClick={() => setShowCreate(true)}>{t("createKey")}</Button></div> :
      <div className="table-wrap"><table><thead><tr><th>{t("name")}</th><th>{t("key")}</th><th>{t("createdAt")}</th><th>{t("lastUsed")}</th><th>{t("status")}</th><th></th></tr></thead><tbody>{keys.map(key =>
        <tr key={key.id}><td className="strong">{key.name}</td><td><code>{key.mask}</code></td><td>{formatDate(key.created_at, locale)}</td><td>{key.last_used_at ? formatDate(key.last_used_at, locale) : "—"}</td><td><span className={key.revoked_at ? "status revoked" : "status"}>{t(key.revoked_at ? "revoked" : "active")}</span></td><td>{!key.revoked_at ? <button className="text-danger" onClick={() => revoke(key)}>{t("revoke")}</button> : null}</td></tr>
      )}</tbody></table></div>}
    {showCreate ? <div className="dialog-backdrop" role="presentation" onMouseDown={() => setShowCreate(false)}><div className="dialog" role="dialog" aria-modal="true" aria-labelledby="create-title" onMouseDown={event => event.stopPropagation()}><button className="dialog-close" aria-label={t("close")} onClick={() => setShowCreate(false)}><X size={18} /></button><h2 id="create-title">{t("createKeyTitle")}</h2><p>{t("createKeyDescription")}</p><form onSubmit={create}><label htmlFor="key-name">{t("name")}</label><Input id="key-name" maxLength={80} autoFocus value={name} onChange={event => setName(event.target.value)} placeholder={t("keyNameExample")} required /><div className="dialog-actions"><Button type="button" variant="outline" onClick={() => setShowCreate(false)}>{t("cancel")}</Button><Button type="submit" disabled={busy}>{busy ? t("creating") : t("createKey")}</Button></div></form></div></div> : null}
  </>
}

function UsagePage() {
  const { t, locale } = useI18n()
  const [usage, setUsage] = useState<Usage | null>(null)
  const [error, setError] = useState<unknown>(null)
  useEffect(() => { api<Usage>("/internal/usage").then(setUsage).catch(setError) }, [])
  const totals = usage?.totals
  const daily = usage?.daily || []
  const maxTokens = Math.max(1, ...daily.map(day => day.input_tokens + day.output_tokens))
  const maxRequests = Math.max(1, ...daily.map(day => day.requests))
  const number = (value: number) => value.toLocaleString(locale)

  return <>
    <PageTitle title={t("usage")} description={t("usageDescription")} />
    {error ? <div className="form-error" role="alert">{displayError(error, t)}</div> : null}
    <section className="chart-section"><div className="chart-head"><h2>{t("tokens")}</h2><strong>{number((totals?.input_tokens || 0) + (totals?.output_tokens || 0))}</strong></div><div className="bars">{daily.length ? daily.map(day => <div className="bar-column" key={day.day} title={t("tokenTooltip", { day: day.day, count: number(day.input_tokens + day.output_tokens) })}><div className="bar" style={{ height: Math.max(2, ((day.input_tokens + day.output_tokens) / maxTokens) * 100) + "%" }} /><span>{day.day.slice(5)}</span></div>) : <div className="chart-empty">{t("noUsage")}</div>}</div></section>
    <section className="chart-section"><div className="chart-head"><h2>{t("requests")}</h2><strong>{number(totals?.requests || 0)}</strong></div><div className="bars">{daily.length ? daily.map(day => <div className="bar-column" key={day.day} title={t("requestTooltip", { day: day.day, count: number(day.requests) })}><div className="bar" style={{ height: Math.max(2, (day.requests / maxRequests) * 100) + "%" }} /><span>{day.day.slice(5)}</span></div>) : <div className="chart-empty">{t("noRequests")}</div>}</div></section>
    <div className="section-head"><h2>{t("sources")}</h2><span>{t("inputOutputSummary", { input: number(totals?.input_tokens || 0), output: number(totals?.output_tokens || 0) })}</span></div>
    <div className="table-wrap"><table><thead><tr><th>{t("sources")}</th><th>{t("requests")}</th><th>{t("inputTokens")}</th><th>{t("outputTokens")}</th></tr></thead><tbody>{usage?.sources.map(source => <tr key={source.source + "-" + source.key_id}><td className="strong">{source.source === "playground" ? t("playgroundSource") : "API Key #" + source.key_id}</td><td>{number(source.requests)}</td><td>{number(source.input_tokens)}</td><td>{number(source.output_tokens)}</td></tr>)}</tbody></table></div>
  </>
}

function Docs() {
  const { t } = useI18n()
  return <>
    <PageTitle title={t("documentation")} description={t("docsDescription")} />
    <div className="docs"><h2>POST /v1/systemone</h2><p>{t("docsIntro")}</p><pre>{JSON.stringify(sampleRequest, null, 2)}</pre><h2>{t("docsResponse")}</h2><p>{t("docsResponseDescription")}</p><p className="docs-note"><CircleHelp size={16} /> {t("docsNote")}</p></div>
  </>
}

function formatDate(value: string, locale: Locale) {
  return new Date(value).toLocaleString(locale, { hour12: false })
}

export default App
