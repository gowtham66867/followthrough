import React, { useEffect, useRef, useState } from 'react';
import { api, safeLink } from './api';
import { Icon } from './ui';
import type { Answer, Deadline, Job, Opportunity, Requirement, Snapshot, Source } from './types';

export function statusLabel(value: string) {
  return (
    (
      {
        discovered: 'Discovered',
        preparing: 'In preparation',
        ready: 'Ready to submit',
        awaiting_receipt: 'Awaiting receipt',
        closed: 'Receipt confirmed',
        cancelled: 'Cancelled',
      } as Record<string, string>
    )[value] || value
  );
}

interface EditorProps {
  requirement: Requirement;
  value?: Answer;
  revision: number;
  disabled: boolean;
  onSave: (key: string, answer: string, revision: number) => Promise<void>;
  onSource: () => void;
}
export function AnswerEditor({
  requirement: r,
  value,
  revision,
  disabled,
  onSave,
  onSource,
}: EditorProps) {
  const [answer, setAnswer] = useState(value?.answer || '');
  const [dirty, setDirty] = useState(false);
  const editRevision = useRef(revision);
  useEffect(() => {
    setAnswer(value?.answer || '');
    setDirty(false);
    editRevision.current = revision;
  }, [value?.answer, value?.confirmed]);
  return (
    <div className="answer-editor">
      <div>
        <label htmlFor={r.id}>
          {r.title}{' '}
          <span className={'badge ' + (value?.confirmed ? 'green' : '')}>
            {value?.confirmed ? 'Reviewed' : value?.answer ? 'Draft' : 'Missing'}
          </span>
        </label>
        <button className="text-button" onClick={onSource}>
          Source
        </button>
      </div>
      <textarea
        id={r.id}
        rows={r.requirement_key.endsWith('_url') ? 2 : 4}
        value={answer}
        onFocus={() => {
          editRevision.current = revision;
        }}
        onChange={(e) => {
          setDirty(true);
          setAnswer(e.target.value);
        }}
        placeholder={
          r.requirement_key.endsWith('_url')
            ? 'https://…'
            : 'Add the facts or answer you want to use…'
        }
        disabled={disabled}
      />
      <div>
        <small>
          {value?.fact_keys?.length
            ? 'Based on: ' + value.fact_keys.join(', ')
            : 'Your words are saved as a reviewed answer.'}
        </small>
        <button
          className="mini-button"
          disabled={disabled || !answer.trim()}
          onClick={() =>
            void onSave(r.requirement_key, answer, dirty ? editRevision.current : revision)
          }
        >
          Save & review <Icon name="check" size={13} />
        </button>
      </div>
    </div>
  );
}

export function DeadlineReview({
  deadline: d,
  selected,
  disabled,
  format,
  onSource,
  onConfirm,
}: {
  deadline: Deadline;
  selected: boolean;
  disabled: boolean;
  format: (v: string) => string;
  onSource: () => void;
  onConfirm: (v: string) => Promise<void>;
}) {
  const [resolved, setResolved] = useState('');
  return (
    <div className="deadline-candidate">
      <span className="eyebrow">{selected ? 'CONFIRMED SOURCE' : 'SOURCE PROPOSAL'}</span>
      <p>{d.due_at ? format(d.due_at) : 'Ambiguous date'}</p>
      <button className="text-button" onClick={onSource}>
        Read original wording
      </button>
      {!selected && (
        <>
          {d.ambiguity && <p className="small-note">{d.ambiguity}</p>}
          {(!d.due_at || d.ambiguity) && (
            <input
              aria-label="Resolved deadline with UTC offset"
              placeholder="2026-10-30T22:30:00+05:30"
              value={resolved}
              onChange={(e) => setResolved(e.target.value)}
            />
          )}
          <button
            className="mini-button"
            disabled={disabled || (!d.due_at && !resolved)}
            onClick={() => void onConfirm(resolved)}
          >
            Use this deadline
          </button>
        </>
      )}
    </div>
  );
}

export function SourceCard({ source, quotes }: { source?: Source; quotes: string[] }) {
  if (!source) return <p className="muted">No source selected.</p>;
  // Render original content as text only. React escapes all message HTML.
  let parts: React.ReactNode[] = [source.body];
  const quote = quotes.find((q) => source.body.includes(q));
  if (quote) {
    const index = source.body.indexOf(quote);
    parts = [
      source.body.slice(0, index),
      <mark key="quote">{quote}</mark>,
      source.body.slice(index + quote.length),
    ];
  }
  return (
    <article className="source-card">
      <div>
        <span className="source-icon">
          <Icon name="mail" />
        </span>
        <span className="badge">
          {source.mode === 'fixture' ? 'Fictional message' : 'Imported message'}
        </span>
      </div>
      <h3>{source.subject}</h3>
      <p className="muted">
        {source.sender} · {new Date(source.received_at).toLocaleDateString('en-IN')}
      </p>
      <div className="source-body">{parts}</div>
      <small className="source-id">Source ID: {source.id}</small>
      {safeLink(source.external_url) && (
        <a
          className="text-button"
          href={safeLink(source.external_url)}
          target="_blank"
          rel="noreferrer"
        >
          Open in Gmail <Icon name="arrow" size={14} />
        </a>
      )}
    </article>
  );
}

export function Conversation({
  op,
  busy,
  onSend,
}: {
  op: Opportunity;
  busy: boolean;
  onSend: (message: string, field: string) => Promise<void>;
}) {
  const [message, setMessage] = useState(''),
    [field, setField] = useState('');
  return (
    <div className="conversation">
      <div className="rail-heading">
        <Icon name="spark" />
        <h3>One useful next step.</h3>
      </div>
      <p className="muted">
        A guided preparation conversation. Choose a field to save your exact words, or ask what
        needs attention.
      </p>
      {op.conversation.map((t) => (
        <div className={'turn ' + t.role} key={t.id}>
          <small>{t.role === 'user' ? 'You' : 'FollowThrough'}</small>
          <p>{t.text}</p>
        </div>
      ))}
      <select aria-label="Field to answer" value={field} onChange={(e) => setField(e.target.value)}>
        <option value="">Ask for the next step</option>
        {op.requirements.map((r) => (
          <option key={r.id} value={r.requirement_key}>
            Answer: {r.title}
          </option>
        ))}
      </select>
      <div className="chat-input">
        <input
          aria-label="Preparation message"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="What should I finish next?"
        />
        <button
          className="icon-button"
          aria-label="Send message"
          disabled={busy || !message.trim()}
          onClick={() => void onSend(message, field).then(() => setMessage(''))}
        >
          <Icon name="arrow" />
        </button>
      </div>
    </div>
  );
}

export function Profile({
  data,
  busy,
  onSave,
  onDemo,
  onClear,
}: {
  data: Snapshot;
  busy: boolean;
  onSave: (facts: Record<string, string>) => Promise<void>;
  onDemo: () => Promise<void>;
  onClear: () => Promise<void>;
}) {
  const keys = [
    ['project_summary', 'Project summary'],
    ['repository_url', 'Public repository URL'],
    ['demo_url', 'Working demo URL'],
    ['video_url', 'Public video URL'],
    ['tool_feedback', 'Observed tool feedback'],
  ];
  const [facts, setFacts] = useState<Record<string, string>>(
    Object.fromEntries(data.facts.map((f) => [f.key, f.value])),
  );
  useEffect(
    () => setFacts(Object.fromEntries(data.facts.map((f) => [f.key, f.value]))),
    [data.facts],
  );
  return (
    <>
      <section className="page-heading">
        <div>
          <p className="eyebrow">A REUSABLE FOUNDATION</p>
          <h1>Your project, in your words.</h1>
          <p className="subtitle">Confirm facts once. Use them to prepare grounded drafts.</p>
        </div>
      </section>
      <section className="profile-panel">
        <div className="notice">
          <Icon name="shield" />
          Only supplied facts support drafts. Leave unmeasured results and unavailable links empty.
        </div>
        {keys.map(([key, label]) => (
          <label className="field-label" key={key}>
            {label}
            <textarea
              rows={key.endsWith('_url') ? 2 : 4}
              value={facts[key] || ''}
              onChange={(e) => setFacts({ ...facts, [key]: e.target.value })}
            />
          </label>
        ))}
        <div className="button-row">
          <button className="button primary" disabled={busy} onClick={() => void onSave(facts)}>
            Save confirmed facts
          </button>
          <button className="button secondary" disabled={busy} onClick={() => void onDemo()}>
            Use fictional demo profile
          </button>
          <button className="text-button" disabled={busy} onClick={() => void onClear()}>
            Remove profile facts
          </button>
        </div>
        <p className="small-note">
          Fictional demo links are placeholders. They are never evidence of a working deployment.
        </p>
      </section>
    </>
  );
}

export function Connections({
  data,
  busy,
  run,
  onJob,
}: {
  data: Snapshot;
  busy: boolean;
  run: (fn: () => Promise<unknown>, message?: string) => Promise<void>;
  onJob: (job: Job) => void;
}) {
  const [query, setQuery] = useState('newer_than:30d hackathon'),
    [results, setResults] = useState<{ id: string; subject: string; sender: string }[]>([]),
    [selected, setSelected] = useState<string[]>([]),
    [nextPage, setNextPage] = useState<string | null>(null);
  async function search(page?: string) {
    const result = await api<{ messages: typeof results; next_page_token: string | null }>(
      '/gmail/messages?q=' +
        encodeURIComponent(query) +
        (page ? '&page_token=' + encodeURIComponent(page) : ''),
    );
    setResults(result.messages);
    setSelected([]);
    setNextPage(result.next_page_token);
  }
  return (
    <>
      <section className="page-heading">
        <div>
          <p className="eyebrow">CHOOSE WHAT YOU SHARE</p>
          <h1>Your sources. Your control.</h1>
          <p className="subtitle">
            Connect selected information to a workspace that lives on this computer.
          </p>
        </div>
      </section>
      <section className="connection-grid">
        <article className="connection-card">
          <span className="source-icon">
            <Icon name="mail" size={25} />
          </span>
          <span className={'badge ' + (data.settings.gmail.connected ? 'green' : '')}>
            {data.settings.gmail.connected
              ? 'Connected'
              : data.settings.gmail.configured
                ? 'Ready to connect'
                : 'Setup needed'}
          </span>
          <h2>Gmail</h2>
          <p>
            Read-only access. Search first, then import the messages you choose. FollowThrough
            cannot send, archive or delete mail.
          </p>
          {data.settings.gmail.connected ? (
            <button
              className="button secondary"
              disabled={busy}
              onClick={() =>
                void run(
                  () => api('/gmail/disconnect', 'POST', {}),
                  'Gmail disconnected and local tokens removed.',
                )
              }
            >
              Disconnect Gmail
            </button>
          ) : data.settings.gmail.configured ? (
            <a className="button primary" href="/api/gmail/start">
              Connect Gmail
            </a>
          ) : (
            <div className="setup-note">
              Set <code>gmail_client_id</code> in config.yaml and <code>GOOGLE_CLIENT_SECRET</code>{' '}
              in the server environment. Register the exact loopback redirect URI in Google Cloud.
            </div>
          )}
        </article>
        <article className="connection-card">
          <span className="source-icon">
            <Icon name="spark" size={25} />
          </span>
          <span
            className={
              'badge ' + (data.settings.nebius_key_configured && data.settings.model ? 'green' : '')
            }
          >
            {data.settings.nebius_key_configured && data.settings.model
              ? 'Configured · not verified'
              : 'Setup needed'}
          </span>
          <h2>Nebius + NVIDIA</h2>
          <p>
            Live extraction and drafting use NVIDIA Nemotron on Nebius Token Factory. Demo fixtures
            never impersonate live inference.
          </p>
          <div className="setup-note">
            Model:{' '}
            <code>{data.settings.model || 'Select an available nvidia/ model in config.yaml'}</code>
            <br />
            API key:{' '}
            {data.settings.nebius_key_configured
              ? 'Present in server environment'
              : 'Set NEBIUS_API_KEY in the server environment'}
          </div>
        </article>
      </section>
      {data.settings.gmail.connected && (
        <section className="profile-panel">
          <h2>Choose messages to import</h2>
          <div className="search-row">
            <input
              aria-label="Gmail search query"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <button
              className="button primary"
              disabled={busy}
              onClick={() => void run(() => search())}
            >
              Search Gmail
            </button>
          </div>
          {results.map((m) => (
            <label className="mail-choice" key={m.id}>
              <input
                type="checkbox"
                checked={selected.includes(m.id)}
                onChange={(e) =>
                  setSelected(
                    e.target.checked ? [...selected, m.id] : selected.filter((id) => id !== m.id),
                  )
                }
              />
              <span>
                <strong>{m.subject}</strong>
                <small>{m.sender}</small>
              </span>
            </label>
          ))}
          <div className="button-row">
            <button
              className="button primary"
              disabled={busy || !selected.length}
              onClick={() =>
                void run(async () =>
                  onJob(
                    await api<Job>('/gmail/import', 'POST', {
                      message_ids: selected,
                      command_key: crypto.randomUUID(),
                    }),
                  ),
                )
              }
            >
              Import {selected.length} selected
            </button>
            {nextPage && (
              <button
                className="button secondary"
                disabled={busy}
                onClick={() => void run(() => search(nextPage))}
              >
                Next page
              </button>
            )}
          </div>
          <p className="small-note">
            Import sends the selected message bodies to Nebius. Start with a small, relevant
            selection.
          </p>
        </section>
      )}
      <div className="callout privacy">
        <Icon name="shield" />
        <div>
          <strong>Local, with clear boundaries.</strong>
          <p>
            {data.settings.data_policy} {data.settings.gmail.storage}. This is a single-owner
            loopback app, not a public multi-user service.
          </p>
        </div>
      </div>
    </>
  );
}
