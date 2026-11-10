import type { PromptDiffResponse } from '../types'
import { Diagnostic, Loading } from './ui'
import type { ErrorLike } from './ui'

export interface PromptLabProps {
  data: PromptDiffResponse | null
  error?: ErrorLike | null
  onRetry?: () => void
}

export function PromptLab({ data, error, onRetry }: PromptLabProps) {
  return <section className="prompt-section architectural-section" aria-labelledby="prompt-title">
    <div className="prompt-heading"><div><p className="section-index mono">PROMPT ENGINEERING / FOUR RULE CHANGES</p><h2 id="prompt-title">A prompt with boundaries</h2></div><p>The state-guarded prompt makes the next safe action explicit</p></div>
    <Diagnostic error={error} />
    {data ? <>
      <div className="prompt-rules">{data.rules.map((rule, i) => <article className="prompt-rule" key={rule.rule_id}><span className="rule-number mono">{String(i + 1).padStart(2, '0')}</span><div><p className="mono rule-id">{rule.rule_id}</p><h3>{rule.title}</h3><p>{rule.description}</p></div></article>)}</div>
      <details className="system-prompts"><summary>Inspect complete system prompts <span className="mono">V1 ↔ V2</span></summary><div className="prompt-grid"><div><h3 className="mono">BASELINE / PROMPT V1</h3><pre tabIndex={0}>{data.prompt_v1}</pre></div><div><h3 className="mono">STATE-GUARDED / PROMPT V2</h3><pre tabIndex={0}>{data.prompt_v2}</pre></div></div></details>
    </> : error ? onRetry && <button className="secondary-button" onClick={onRetry}>Reload prompt rules</button> : <Loading text="Loading prompt rules" />}
  </section>
}
