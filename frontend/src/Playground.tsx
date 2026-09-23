import { useEffect, useState } from "react"
import { Code2, ListFilter, Plus, Send, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { apiErrorMessage, useI18n, type MessageKey, type Translate } from "./i18n"

type QuestionType = "noul" | "score" | "choice"
export type Model = "auto" | "english" | "multilingual" | "typed-decisions"
type Question = {
  uid: string
  id: string
  type: QuestionType
  instructions: string
  choices: { label: string; description: string }[]
  levels: string[]
}
type Draft = { state: string; stateMode: "text" | "json"; model: Model; questions: Question[] }
type Prediction = { answers: Record<string, unknown>; model?: string; routing?: { model?: string }; usage?: { input_tokens?: number; output_tokens?: number } }

export const sampleRequest = {
  state: { message: "I was charged twice and need a refund today." },
  questions: {
    intent: { type: "choice", instructions: "What does the customer want?", criteria: { refund: "money returned", technical_help: "a technical problem" } },
    urgent: { type: "noul", instructions: "Does the customer express urgency?" },
    frustration: { type: "score", instructions: "How frustrated is the customer?", criteria: ["calm", "concerned", "very angry"] },
  },
  model: "auto",
}
const chineseSampleRequest = { ...sampleRequest, state: { message: "我的账户被重复扣费了，请尽快退款。" }, model: "multilingual" }
const traditionalSampleRequest = { ...sampleRequest, state: { message: "我的帳戶被重複扣款了，請盡快退款。" }, model: "multilingual" }
const models: Model[] = ["auto", "english", "multilingual", "typed-decisions"]

class DraftError extends Error {
  constructor(readonly key: MessageKey, readonly values?: Record<string, string | number>) { super(key) }
}

let nextQuestionUid = 0

function makeQuestion(type: QuestionType = "noul"): Question {
  return { uid: String(++nextQuestionUid), id: "", type, instructions: "", choices: [{ label: "", description: "" }, { label: "", description: "" }], levels: ["", ""] }
}

function parseDraft(value: string): Draft {
  let request: unknown
  try { request = JSON.parse(value) } catch { throw new DraftError("playgroundInvalidJson") }
  if (!request || typeof request !== "object" || Array.isArray(request)) throw new DraftError("playgroundFormUnsupported")
  const data = request as Record<string, unknown>
  if (Object.keys(data).some(key => !["state", "questions", "model"].includes(key))) throw new DraftError("playgroundFormUnsupported")
  if (!(typeof data.state === "string" || (data.state !== null && typeof data.state === "object"))) throw new DraftError("playgroundFormUnsupported")
  const model = Object.hasOwn(data, "model") ? data.model : "auto"
  if (!models.includes(model as Model)) throw new DraftError("playgroundFormUnsupported")
  if (!data.questions || typeof data.questions !== "object" || Array.isArray(data.questions)) throw new DraftError("playgroundFormUnsupported")
  const questions = Object.entries(data.questions).map(([id, definition]) => {
    if (!definition || typeof definition !== "object" || Array.isArray(definition)) throw new DraftError("playgroundFormUnsupported")
    const q = definition as Record<string, unknown>
    if (typeof q.instructions !== "string" || !["noul", "choice", "score"].includes(String(q.type))) throw new DraftError("playgroundFormUnsupported")
    if (Object.keys(q).some(key => !["type", "instructions", "criteria"].includes(key))) throw new DraftError("playgroundFormUnsupported")
    const question = { ...makeQuestion(q.type as QuestionType), id, instructions: q.instructions }
    if (q.type === "noul") {
      if (q.criteria !== undefined) throw new DraftError("playgroundFormUnsupported")
    } else if (q.type === "choice") {
      if (Array.isArray(q.criteria) && q.criteria.every(item => typeof item === "string")) {
        question.choices = q.criteria.map(label => ({ label, description: "" }))
      } else if (q.criteria && typeof q.criteria === "object" && !Array.isArray(q.criteria) && Object.values(q.criteria).every(item => item === null || typeof item === "string")) {
        question.choices = Object.entries(q.criteria).map(([label, description]) => ({ label, description: description ?? "" }))
      } else throw new DraftError("playgroundFormUnsupported")
    } else {
      if (!Array.isArray(q.criteria) || !q.criteria.every(item => typeof item === "string")) throw new DraftError("playgroundFormUnsupported")
      question.levels = q.criteria
    }
    return question
  })
  return { state: typeof data.state === "string" ? data.state : JSON.stringify(data.state, null, 2), stateMode: typeof data.state === "string" ? "text" : "json", model: model as Model, questions }
}

function buildRequest(draft: Draft): string {
  let state: unknown = draft.state
  if (draft.stateMode === "json") {
    try { state = JSON.parse(draft.state) } catch { throw new DraftError("playgroundInvalidState") }
    if (state === null || !(typeof state === "string" || typeof state === "object")) throw new DraftError("playgroundInvalidState")
  }
  if (typeof state === "string" && !state.trim()) throw new DraftError("playgroundEmptyState")
  if (!draft.questions.length) throw new DraftError("playgroundNoQuestions")
  const questions: Record<string, unknown> = Object.create(null)
  for (const [index, q] of draft.questions.entries()) {
    const id = q.id.trim()
    if (!id) throw new DraftError("playgroundMissingId", { number: index + 1 })
    if (Object.hasOwn(questions, id)) throw new DraftError("playgroundDuplicateId", { id })
    if (!q.instructions.trim()) throw new DraftError("playgroundMissingInstructions", { id })
    const definition: Record<string, unknown> = { type: q.type, instructions: q.instructions.trim() }
    if (q.type === "choice") {
      if (q.choices.length < 2 || q.choices.some(option => !option.label.trim()) || new Set(q.choices.map(option => option.label.trim())).size !== q.choices.length) throw new DraftError("playgroundInvalidChoice", { id })
      definition.criteria = Object.fromEntries(q.choices.map(option => [option.label.trim(), option.description.trim()]))
    }
    if (q.type === "score") {
      if (q.levels.length < 2 || q.levels.some(level => !level.trim())) throw new DraftError("playgroundInvalidScore", { id })
      definition.criteria = q.levels.map(level => level.trim())
    }
    questions[id] = definition
  }
  return JSON.stringify({ state, questions, model: draft.model }, null, 2)
}

function errorText(error: unknown, t: Translate): string {
  if (error instanceof DraftError) return t(error.key, error.values)
  if (error && typeof error === "object" && "code" in error) return apiErrorMessage(String(error.code), t)
  return apiErrorMessage(undefined, t)
}

export function Playground({ run, loadModels }: { run: (body: string) => Promise<unknown>; loadModels: () => Promise<{ models: Model[] }> }) {
  const { t, locale } = useI18n()
  const [draft, setDraft] = useState<Draft>(() => parseDraft(JSON.stringify(sampleRequest)))
  const [editor, setEditor] = useState<"form" | "json">("form")
  const [raw, setRaw] = useState(JSON.stringify(sampleRequest, null, 2))
  const [result, setResult] = useState<Prediction | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [availableModels, setAvailableModels] = useState<Model[]>(["auto"])

  useEffect(() => {
    let active = true
    loadModels().then(({ models: installed }) => {
      if (active) setAvailableModels(installed.filter(model => models.includes(model)))
    }).catch(() => {})
    return () => { active = false }
  }, [loadModels])

  function loadExample(example: unknown) {
    const value = JSON.stringify(example, null, 2)
    setDraft(parseDraft(value))
    setRaw(value)
    setResult(null)
    setError(null)
  }

  function selectEditor(next: "form" | "json") {
    if (next === editor) return
    try {
      if (next === "json") setRaw(buildRequest(draft))
      else {
        const parsed = parseDraft(raw)
        if (!availableModels.includes(parsed.model)) throw new DraftError("errorModelNotAvailable")
        setDraft(parsed)
      }
      setEditor(next)
      setError(null)
    } catch (cause) { setError(errorText(cause, t)) }
  }

  function changeDraft(update: (previous: Draft) => Draft) {
    setDraft(update)
    setResult(null)
    setError(null)
  }

  function selectStateMode(next: Draft["stateMode"]) {
    if (next === draft.stateMode) return
    changeDraft(previous => {
      if (next === "json") return { ...previous, state: JSON.stringify(previous.state), stateMode: next }
      let state = previous.state
      try {
        const parsed: unknown = JSON.parse(state)
        if (typeof parsed === "string") state = parsed
      } catch { /* Keep the current text so it can be edited. */ }
      return { ...previous, state, stateMode: next }
    })
  }

  function updateQuestion(uid: string, change: Partial<Question>) {
    changeDraft(previous => ({ ...previous, questions: previous.questions.map(q => q.uid === uid ? { ...q, ...change } : q) }))
  }

  async function submit() {
    setError(null)
    let body: string
    try { body = editor === "json" ? raw : buildRequest(draft) }
    catch (cause) { setError(errorText(cause, t)); setResult(null); return }
    setBusy(true)
    try {
      const response = await run(body)
      setResult(response as Prediction)
    } catch (cause) {
      setResult(null)
      setError(errorText(cause, t))
    } finally { setBusy(false) }
  }

  return <>
    <div className="page-title"><div><h1>{t("playground")}</h1><p>{t("playgroundDescription")}</p></div></div>
    <div className="playground-layout">
      <div className="playground-editor">
        <div className="playground-toolbar">
          <div className="playground-tabs" role="group" aria-label={t("playgroundEditorMode")}>
            <button type="button" className={editor === "form" ? "selected" : ""} aria-pressed={editor === "form"} onClick={() => selectEditor("form")}><ListFilter size={15} />{t("playgroundForm")}</button>
            <button type="button" className={editor === "json" ? "selected" : ""} aria-pressed={editor === "json"} onClick={() => selectEditor("json")}><Code2 size={15} />JSON</button>
          </div>
          <div className="sample-actions"><button type="button" onClick={() => loadExample(sampleRequest)}>{t("englishExample")}</button><button type="button" onClick={() => loadExample(locale === "zh-TW" ? traditionalSampleRequest : chineseSampleRequest)}>{t("chineseExample")}</button></div>
        </div>
        {editor === "json" ? <div className="playground-raw"><label htmlFor="playground-request-json">{t("requestJson")}</label><textarea id="playground-request-json" spellCheck={false} value={raw} onChange={event => { setRaw(event.target.value); setResult(null); setError(null) }} /></div> : <>
          <section className="playground-section">
            <div className="playground-section-head"><div><h2>{t("playgroundState")}</h2><p>{t("playgroundStateHint")}</p></div><div className="playground-segmented" role="group" aria-label={t("playgroundStateFormat")}><button type="button" className={draft.stateMode === "text" ? "selected" : ""} aria-pressed={draft.stateMode === "text"} onClick={() => selectStateMode("text")}>{t("playgroundText")}</button><button type="button" className={draft.stateMode === "json" ? "selected" : ""} aria-pressed={draft.stateMode === "json"} onClick={() => selectStateMode("json")}>JSON</button></div></div>
            <textarea className="playground-state" aria-label={t("playgroundState")} spellCheck={false} value={draft.state} onChange={event => changeDraft(previous => ({ ...previous, state: event.target.value }))} placeholder={t("playgroundStatePlaceholder")} />
          </section>
          <section className="playground-section">
            <div className="playground-section-head"><div><h2>{t("playgroundQuestions")}</h2><p>{t("playgroundQuestionsHint")}</p></div><span className="playground-count">{draft.questions.length}/50</span></div>
            <div className="playground-question-list">{draft.questions.map((q, index) => <div className="playground-question" key={q.uid}>
              <div className="playground-question-head"><span>{t("playgroundQuestionNumber", { number: index + 1 })}</span><button type="button" className="playground-icon-button" title={t("playgroundRemoveQuestion")} aria-label={t("playgroundRemoveQuestionNamed", { number: index + 1 })} onClick={() => changeDraft(previous => ({ ...previous, questions: previous.questions.filter(item => item.uid !== q.uid) }))}><Trash2 size={16} /></button></div>
              <div className="playground-fields"><label>{t("playgroundQuestionId")}<Input value={q.id} onChange={event => updateQuestion(q.uid, { id: event.target.value })} placeholder={t("playgroundQuestionIdPlaceholder")} /></label><label>{t("playgroundQuestionType")}<select value={q.type} onChange={event => updateQuestion(q.uid, { type: event.target.value as QuestionType })}><option value="noul">Noul · {t("playgroundNoulHint")}</option><option value="score">Score · {t("playgroundScoreHint")}</option><option value="choice">Choice · {t("playgroundChoiceHint")}</option></select></label></div>
              <label className="playground-field">{t("playgroundInstructions")}<textarea rows={2} value={q.instructions} onChange={event => updateQuestion(q.uid, { instructions: event.target.value })} placeholder={t("playgroundInstructionsPlaceholder")} /></label>
              {q.type === "choice" ? <div className="playground-options"><div className="playground-subhead">{t("playgroundChoices")}</div>{q.choices.map((option, optionIndex) => <div className="playground-option-row" key={optionIndex}><Input aria-label={t("playgroundChoiceLabel", { number: optionIndex + 1 })} placeholder={t("playgroundChoiceLabelPlaceholder")} value={option.label} onChange={event => updateQuestion(q.uid, { choices: q.choices.map((item, i) => i === optionIndex ? { ...item, label: event.target.value } : item) })} /><Input aria-label={t("playgroundChoiceDescription", { number: optionIndex + 1 })} placeholder={t("playgroundChoiceDescriptionPlaceholder")} value={option.description} onChange={event => updateQuestion(q.uid, { choices: q.choices.map((item, i) => i === optionIndex ? { ...item, description: event.target.value } : item) })} /><button type="button" className="playground-icon-button" title={t("playgroundRemoveOption")} aria-label={t("playgroundRemoveOptionNamed", { number: optionIndex + 1 })} disabled={q.choices.length <= 2} onClick={() => updateQuestion(q.uid, { choices: q.choices.filter((_, i) => i !== optionIndex) })}><Trash2 size={15} /></button></div>)}<button type="button" className="playground-add-inline" disabled={q.choices.length >= 50} onClick={() => updateQuestion(q.uid, { choices: [...q.choices, { label: "", description: "" }] })}><Plus size={14} />{t("playgroundAddChoice")}</button></div> : null}
              {q.type === "score" ? <div className="playground-options"><div className="playground-subhead">{t("playgroundScoreLevels")}</div>{q.levels.map((level, levelIndex) => <div className="playground-option-row score" key={levelIndex}><span className="playground-level-index">{levelIndex}</span><Input aria-label={t("playgroundScoreLevel", { number: levelIndex + 1 })} placeholder={t("playgroundScoreLevelPlaceholder")} value={level} onChange={event => updateQuestion(q.uid, { levels: q.levels.map((item, i) => i === levelIndex ? event.target.value : item) })} /><button type="button" className="playground-icon-button" title={t("playgroundRemoveOption")} aria-label={t("playgroundRemoveOptionNamed", { number: levelIndex + 1 })} disabled={q.levels.length <= 2} onClick={() => updateQuestion(q.uid, { levels: q.levels.filter((_, i) => i !== levelIndex) })}><Trash2 size={15} /></button></div>)}<button type="button" className="playground-add-inline" disabled={q.levels.length >= 50} onClick={() => updateQuestion(q.uid, { levels: [...q.levels, ""] })}><Plus size={14} />{t("playgroundAddLevel")}</button></div> : null}
            </div>)}</div>
            <button type="button" className="playground-add-question" disabled={draft.questions.length >= 50} onClick={() => changeDraft(previous => ({ ...previous, questions: [...previous.questions, makeQuestion()] }))}><Plus size={16} />{t("playgroundAddQuestion")}</button>
          </section>
          <section className="playground-section playground-model"><label htmlFor="playground-model">{t("playgroundModel")}</label><select id="playground-model" value={draft.model} onChange={event => changeDraft(previous => ({ ...previous, model: event.target.value as Model }))}>{availableModels.map(model => <option key={model} value={model}>{model}</option>)}</select><p>{t("playgroundModelHint")}</p></section>
        </>}
        <div className="playground-submit">{error ? <p className="form-error" role="alert">{error}</p> : null}<Button type="button" onClick={submit} disabled={busy}><Send size={16} />{busy ? t("runningInference") : t("runInference")}</Button></div>
      </div>
      <aside className="playground-output" aria-live="polite"><div className="playground-output-head"><h2>{t("response")}</h2>{result?.routing?.model || result?.model ? <span>{result.routing?.model || result.model}</span> : null}</div>
        {result ? <><div className="playground-usage"><span>{t("inputTokens")} <strong>{result.usage?.input_tokens ?? 0}</strong></span><span>{t("outputTokens")} <strong>{result.usage?.output_tokens ?? 0}</strong></span></div><div className="playground-answer-list">{Object.entries(result.answers).map(([id, answer]) => <section className="playground-answer" key={id}><h3>{id}</h3><pre>{JSON.stringify(answer, null, 2)}</pre></section>)}</div><details className="playground-full-response"><summary>{t("playgroundFullResponse")}</summary><pre>{JSON.stringify(result, null, 2)}</pre></details></> : <div className="playground-output-empty"><Send size={22} strokeWidth={1.5} /><p>{t("noResult")}</p></div>}
      </aside>
    </div>
  </>
}
