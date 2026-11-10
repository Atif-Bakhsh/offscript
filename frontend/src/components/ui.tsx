import type { ButtonHTMLAttributes, ReactNode } from 'react'
import type { ExecutionProvenance } from '../types'
import { provenanceLabel } from '../domain'
import { modeText } from './uiUtils'

export interface ErrorLike {
  code: string
  message: string
  details?: { field: string; message: string }[] | null
}

export function Diagnostic({ error }: { error?: ErrorLike | null }) {
  if (!error) return null
  return <div className="diagnostic" role="alert">
    <strong className="mono">{error.code}</strong>
    <p>{error.message}</p>
    {error.details?.length ? <ul>{error.details.map((detail, i) =>
      <li key={`${detail.field}-${i}`}><span className="mono">{detail.field}</span>: {detail.message}</li>,
    )}</ul> : null}
  </div>
}

export function ArrowButton({ children, className = '', ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button {...props} className={`primary-button ${className}`}>
    <span>{children}</span><span aria-hidden="true" className="button-arrow">↗</span>
  </button>
}

export function SectionHeading({ index, label, title, children }: { index: string; label: string; title: string; children?: ReactNode }) {
  return <div className="section-heading">
    <div><p className="section-index mono">{index} / {label}</p><h2 id={index === '01' ? 'scenario-title' : index === '02' ? 'arena-title' : 'scorecard-title'}>{title}</h2></div>
    {children ? <div className="section-heading-aside">{children}</div> : null}
  </div>
}

export function Provenance({ execution }: { execution: ExecutionProvenance }) {
  return <div className="provenance mono">
    <span>{modeText(execution.mode)}</span>
    <span>{provenanceLabel(execution)}</span>
    {execution.model && <span>{execution.model}</span>}
  </div>
}

export function Loading({ text = 'Loading results' }: { text?: string }) {
  return <div className="loading-placeholder" role="status"><span className="loading-line" aria-hidden="true" /><span>{text}</span></div>
}
