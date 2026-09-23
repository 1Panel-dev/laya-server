export type Session = { username: string; csrf_token: string }

let session: Session | null = null
let sessionVersion = 0
const listeners = new Set<() => void>()

export function getSession() { return session }

export function setSession(value: Session | null) {
  session = value
  sessionVersion += 1
  listeners.forEach(listener => listener())
}

export function subscribeSession(listener: () => void) {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}

export class ApiError extends Error {
  readonly code?: string
  readonly status: number

  constructor(status: number, code?: string) {
    super(code || "UNKNOWN_ERROR")
    this.name = "ApiError"
    this.status = status
    this.code = code
  }
}

export async function api<T>(path: string, options: RequestInit = {}, csrf?: string): Promise<T> {
  const requestSessionVersion = sessionVersion
  const headers = new Headers(options.headers)
  const body = options.body
  const method = options.method?.toUpperCase()
  if (typeof body === "string" && !headers.has("Content-Type")) {
    const payload = body.trim()
    if (payload.startsWith("{") || payload.startsWith("[")) headers.set("Content-Type", "application/json")
  }
  if (method && !["GET", "HEAD"].includes(method)) headers.set("X-CSRF-Token", csrf || "")
  const response = await fetch(path, { credentials: "same-origin", ...options, method, headers })
  if (!response.ok) {
    const unauthenticated = response.status === 401 && path.startsWith("/internal/") && path !== "/internal/auth/login"
    if (unauthenticated && requestSessionVersion === sessionVersion) setSession(null)
    const data = await response.json().catch(() => null)
    throw new ApiError(response.status, data?.detail?.code || (unauthenticated ? "UNAUTHENTICATED" : undefined))
  }
  const responseBody = await response.text()
  return (responseBody ? JSON.parse(responseBody) : undefined) as T
}
