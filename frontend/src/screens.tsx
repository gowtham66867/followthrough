import React from 'react';
import { useView } from './view';
import { api } from './api';
import { Icon } from './ui';
import { statusLabel, AnswerEditor, DeadlineReview, SourceCard, Conversation, Profile, Connections } from './components';
import type { Job } from './types';

export function ChecklistView() {
  const { data, setTab, op, showSource } = useView();
  if (!data || !op) return null;
  return (
    <>
      <div className="inner-heading">
        <div>
          <h3>A clear path to ready.</h3>
          <p className="muted">Review each requirement, then prepare its answer.</p>
        </div>
        <span className="badge">{op.blockers.length} open items</span>
      </div>
      <div className="checklist">
        {op.requirements.map((r, i) => (
          <div className="check-row" key={r.id}>
            <span
              className={
                'check-circle ' +
                (op.package.answers[r.requirement_key]?.confirmed ? 'checked' : '')
              }
            >
              {op.package.answers[r.requirement_key]?.confirmed ? (
                <Icon name="check" size={15} />
              ) : (
                String(i + 1).padStart(2, '0')
              )}
            </span>
            <div>
              <h4>{r.title}</h4>
              <p>
                {op.package.answers[r.requirement_key]?.confirmed
                  ? 'Answer reviewed by you'
                  : op.package.answers[r.requirement_key]?.answer
                    ? 'Draft ready for review'
                    : 'Needs your input'}{' '}
                <span>· {r.required ? 'Required' : 'Optional'}</span>
              </p>
            </div>
            <button className="text-button" onClick={() => showSource(r.source_id)}>
              View source <Icon name="arrow" size={14} />
            </button>
            <button className="mini-button" onClick={() => setTab('Prepare')}>
              {op.package.answers[r.requirement_key]?.confirmed ? 'Edit' : 'Prepare'}
            </button>
          </div>
        ))}
      </div>
      {!op.requirements.length && (
        <p className="muted">
          No supported requirements were found. Registration alone does not establish the submission
          checklist.
        </p>
      )}
      <div className="callout">
        <Icon name="shield" size={21} />
        <div>
          <strong>Ready is a milestone. Received is evidence.</strong>
          <p>
            Approving a package prepares it for you to submit. A matching receipt is reviewed
            separately.
          </p>
        </div>
      </div>
    </>
  );
}

export function PrepareView() {
  const { data, op, busy, showSource, saveAnswer, act, watch } = useView();
  if (!data || !op) return null;
  return (
    <>
      <div className="inner-heading">
        <div>
          <h3>Good answers start with your facts.</h3>
          <p className="muted">Drafts stay unconfirmed until you review them.</p>
        </div>
        <button
          className="button secondary"
          disabled={busy || op.workflow === 'closed'}
          onClick={() =>
            void act(async () =>
              watch(
                await api<Job>(`/obligations/${op.id}/draft`, 'POST', {
                  expected_revision: op.revision,
                }),
              ),
            )
          }
        >
          <Icon name="spark" size={16} /> Draft from profile
        </button>
      </div>
      {!data.facts.length && (
        <div className="notice">
          Add confirmed project facts in Project profile, or write the answers below.
        </div>
      )}
      {op.requirements.map((r) => (
        <AnswerEditor
          key={r.id}
          requirement={r}
          value={op.package.answers[r.requirement_key]}
          revision={op.revision}
          disabled={busy || op.workflow === 'closed'}
          onSave={saveAnswer}
          onSource={() => showSource(r.source_id)}
        />
      ))}
      <Conversation
        op={op}
        busy={busy}
        onSend={(message, field_key) =>
          act(() =>
            api(`/obligations/${op.id}/conversation`, 'POST', {
              message,
              field_key: field_key || null,
              expected_revision: op.revision,
            }),
          )
        }
      />
    </>
  );
}

export function EvidenceView() {
  const { data, sourceId, setSourceId, op, busy, act } = useView();
  if (!data || !op) return null;
  return (
    <>
      <div className="inner-heading">
        <div>
          <h3>Go straight to the source.</h3>
          <p className="muted">Original messages stay beside the claims they support.</p>
        </div>
      </div>
      <div className="source-tabs">
        {op.messages.map((m) => (
          <button
            className={sourceId === m.id ? 'active' : ''}
            key={m.id}
            onClick={() => setSourceId(m.id)}
          >
            {m.subject}
          </button>
        ))}
      </div>
      <SourceCard
        source={op.messages.find((m) => m.id === sourceId) || op.messages[0]}
        quotes={op.requirements
          .filter((r) => r.source_id === (sourceId || op.messages[0]?.id))
          .map((r) => r.quote)}
      />
      <div className="receipt-section">
        <h3>Receipt review</h3>
        {op.receipts.length === 0 ? (
          <p className="muted">No receipt candidates yet. Welcome emails do not count.</p>
        ) : (
          op.receipts.map((r) => (
            <div
              className={'receipt-card ' + (r.verdict === 'mismatch' ? 'warning' : '')}
              key={r.id}
            >
              <span className="badge">{r.verdict.replaceAll('_', ' ')}</span>
              <blockquote>{r.quote}</blockquote>
              <p>{r.reason}</p>
              <button className="text-button" onClick={() => setSourceId(r.source_id)}>
                Inspect original message
              </button>
              {!r.reviewed && r.verdict === 'review_required' && (
                <div className="button-row">
                  <button
                    className="button primary"
                    disabled={busy}
                    onClick={() =>
                      void act(
                        () =>
                          api(`/obligations/${op.id}/receipt-review`, 'POST', {
                            receipt_id: r.id,
                            decision: 'confirm',
                            expected_revision: op.revision,
                          }),
                        'Receipt confirmed. This records receipt, not acceptance.',
                      )
                    }
                  >
                    I reviewed this matching receipt
                  </button>
                  <button
                    className="button secondary"
                    disabled={busy}
                    onClick={() =>
                      void act(() =>
                        api(`/obligations/${op.id}/receipt-review`, 'POST', {
                          receipt_id: r.id,
                          decision: 'reject',
                          expected_revision: op.revision,
                        }),
                      )
                    }
                  >
                    Reject match
                  </button>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </>
  );
}

export function ActivityView() {
  const { data, op, fmtDate } = useView();
  if (!data || !op) return null;
  return (
    <>
      <h3>A history you can follow.</h3>
      <div className="timeline">
        {op.events.map((e) => (
          <div className="timeline-row" key={e.id}>
            <span className="timeline-dot" />
            <div>
              <strong>{e.kind.replaceAll('_', ' ')}</strong>
              <p>{fmtDate(e.created_at)}</p>
              <details>
                <summary>View recorded details</summary>
                <pre>{JSON.stringify(JSON.parse(e.detail_json), null, 2)}</pre>
              </details>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

export function ContextRail() {
  const { data, selected, setTab, op, busy, fmtDate, showSource, act } = useView();
  if (!data || !op) return null;
  return (
    <aside className="context-rail">
      <div className="rail-heading">
        <Icon name="clock" size={18} />
        <h3>The deadline</h3>
      </div>
      {op.deadline?.selected ? (
        <>
          <strong className="deadline-date">{fmtDate(op.deadline.selected.due_at!)}</strong>
          <p className="timezone">{data.settings.timezone} · confirmed by you</p>
          <button
            className="text-button"
            onClick={() => showSource(op.deadline!.selected!.source_id)}
          >
            See supporting message <Icon name="arrow" size={14} />
          </button>
        </>
      ) : (
        <p className="muted">Needs your review before the package can be approved.</p>
      )}
      {op.deadline?.candidates.map((d, i) => (
        <DeadlineReview
          key={d.source_id + i}
          deadline={d}
          selected={op.deadline?.selected?.source_id === d.source_id}
          disabled={busy || op.workflow === 'closed'}
          format={fmtDate}
          onSource={() => showSource(d.source_id)}
          onConfirm={(value) =>
            act(
              () =>
                api(`/obligations/${op.id}/deadline`, 'POST', {
                  source_id: d.source_id,
                  expected_revision: op.revision,
                  due_at: value || null,
                }),
              'Deadline confirmed. Package approval requires a fresh review.',
            )
          }
        />
      ))}
      <div className="rail-divider" />
      <div className="rail-heading">
        <Icon name="shield" size={18} />
        <h3>Where things stand</h3>
      </div>
      <div className="state-line">
        <span className="step-done">
          <Icon name="check" size={12} />
        </span>
        <div>
          Sources linked
          <small>{op.messages.length} original messages</small>
        </div>
      </div>
      <div className="state-line">
        <span className={op.package.approval_revision === op.revision ? 'step-done' : 'step-open'}>
          {op.package.approval_revision === op.revision ? <Icon name="check" size={12} /> : 2}
        </span>
        <div>
          Package reviewed
          <small>
            {op.package.approval_revision === op.revision
              ? 'Current revision approved'
              : 'Review and approve a revision'}
          </small>
        </div>
      </div>
      <div className="state-line">
        <span className={op.workflow === 'closed' ? 'step-done' : 'step-open'}>
          {op.workflow === 'closed' ? <Icon name="check" size={12} /> : 3}
        </span>
        <div>
          Receipt found
          <small>
            {op.workflow === 'closed' ? 'Matched and confirmed by you' : 'Still needs evidence'}
          </small>
        </div>
      </div>
      {op.completion_basis === 'user_asserted' && (
        <p className="small-note">Marked submitted by you. Receipt still unverified.</p>
      )}
      <div className="rail-divider" />
      <div className="eyebrow">YOUR NEXT STEP</div>
      <p className="next-step">
        {op.workflow === 'closed'
          ? 'All set. Your reviewed receipt is saved with the source history.'
          : op.blockers[0]
            ? 'Review: ' + op.blockers[0]
            : op.package.approval_revision !== op.revision
              ? 'Preview and approve the complete package.'
              : 'Submit externally, then bring back the receipt.'}
      </p>
      <button
        className="text-button"
        onClick={() => setTab(op.workflow === 'closed' ? 'Evidence' : 'Prepare')}
      >
        Continue <Icon name="arrow" size={16} />
      </button>
    </aside>
  );
}

export function WorkspacePanel() {
  const { data, tab, setTab, setPreview, op, busy, scenario } = useView();
  if (!data || !op) return null;
  return (
    <section className="workspace-panel">
      <header className="panel-heading">
        <div>
          <p className="eyebrow">PREPARATION WORKSPACE</p>
          <h2>{op.title}</h2>
          <p className="muted">
            {op.mode === 'fixture' ? 'Fictional demonstration · ' : ''}Revision {op.revision} ·{' '}
            {op.messages.length} linked sources
          </p>
        </div>
        <button className="button primary" onClick={() => setPreview(op)}>
          <Icon name="file" size={17} /> Preview package
        </button>
      </header>
      {op.mode === 'fixture' && (
        <div className="demo-controls">
          <span>Walk through the story</span>
          {[
            ['change', 'Add requirement change'],
            ['wrong-receipt', 'Test unrelated receipt'],
            ['receipt', 'Add matching receipt'],
          ].map(([s, label]) => (
            <button key={s} disabled={busy} onClick={() => void scenario(s)}>
              {label}
              <Icon name="arrow" size={13} />
            </button>
          ))}
        </div>
      )}
      <div className="tabs" role="tablist" aria-label="Opportunity views">
        {['Checklist', 'Prepare', 'Evidence', 'Activity'].map((t) => (
          <button
            role="tab"
            aria-selected={tab === t}
            className={tab === t ? 'active' : ''}
            key={t}
            onClick={() => setTab(t)}
          >
            {t}
            {t === 'Checklist' && <span>{op.requirements.length}</span>}
          </button>
        ))}
      </div>
      <div className="panel-body">
        <div className="panel-main">
          {tab === 'Checklist' && <ChecklistView />}
          {tab === 'Prepare' && <PrepareView />}
          {tab === 'Evidence' && <EvidenceView />}
          {tab === 'Activity' && <ActivityView />}
        </div>
        <ContextRail />
      </div>
    </section>
  );
}

export function Overview() {
  const { data, selected, setSelected, setTab, setImportOpen, op, busy, stats, scenario } =
    useView();
  if (!data) return null;
  return (
    <>
      <section className="page-heading">
        <div>
          <p className="eyebrow">LESS CHASING. MORE FINISHING.</p>
          <h1>Your next step, with proof.</h1>
          <p className="subtitle">
            Bring the loose ends together. Know what’s ready, what’s missing, and what’s received.
          </p>
        </div>
        <button className="button primary" disabled={busy} onClick={() => setImportOpen(true)}>
          <Icon name="mail" size={17} /> Import emails
        </button>
      </section>
      <section className="stats">
        {stats.map((s) => (
          <div className="stat" key={s.label}>
            <div>
              <p>{s.label}</p>
              <strong>{String(s.value).padStart(2, '0')}</strong>
            </div>
            <span className="stat-icon">
              <Icon name={s.icon} />
            </span>
          </div>
        ))}
      </section>
      {!data.opportunities.length ? (
        <div className="empty-state">
          <div className="empty-art">
            <div className="paper one">
              <Icon name="mail" size={25} />
              <i />
              <i />
            </div>
            <div className="paper two">
              <Icon name="check" size={25} />
              <i />
              <i />
            </div>
            <span className="empty-arrow">
              <Icon name="arrow" size={26} />
            </span>
          </div>
          <p className="eyebrow">FROM “I SHOULD” TO “IT’S RECEIVED”</p>
          <h2>
            Important work starts in your inbox.
            <br />
            Let’s help it get finished.
          </h2>
          <p>
            Import selected messages, turn requirements into a clear plan,
            <br />
            and keep the evidence beside every decision.
          </p>
          <button
            className="button primary"
            disabled={busy}
            onClick={() => void scenario('welcome')}
          >
            Explore with fictional emails <Icon name="arrow" size={17} />
          </button>
          <small>No account connection or API credits needed.</small>
        </div>
      ) : (
        <>
          <div className="section-label">
            <h2>
              Your opportunities <span>{data.opportunities.length}</span>
            </h2>
            <span className="muted">Every status has a source.</span>
          </div>
          <div className="opportunities">
            {data.opportunities.map((item) => (
              <button
                className={'op-card ' + (selected === item.id ? 'selected' : '')}
                key={item.id}
                onClick={() => {
                  setSelected(item.id);
                  setTab('Checklist');
                }}
              >
                <div className="op-card-top">
                  <span className="op-icon">
                    <Icon name="file" size={20} />
                  </span>
                  <span className={'badge ' + (item.mode === 'fixture' ? 'fixture' : '')}>
                    {item.mode === 'fixture' ? 'Fictional demo' : 'Live sources'}
                  </span>
                </div>
                <h3>{item.title}</h3>
                <p>{item.organizer}</p>
                <div className="op-card-foot">
                  <span className={'status ' + (item.workflow === 'closed' ? 'complete' : '')}>
                    <span className="dot" />
                    {statusLabel(item.workflow)}
                  </span>
                  <span>
                    {
                      item.requirements.filter(
                        (r) => item.package.answers[r.requirement_key]?.confirmed,
                      ).length
                    }
                    /{item.requirements.length} reviewed
                  </span>
                </div>
              </button>
            ))}
          </div>
          {op && <WorkspacePanel />}
        </>
      )}
    </>
  );
}

export function Sidebar() {
  const { data, page, setPage, busy, scenario } = useView();
  return (
    <aside className="sidebar">
      <a className="brand" href="/" aria-label="FollowThrough home">
        <span className="brand-mark">
          <Icon name="arrow" size={21} />
        </span>
        followthrough<span className="brand-dot">.</span>
      </a>
      <div className="workspace-label">
        <span className="avatar">G</span>
        <div>
          Personal workspace<small>Local · private to this device</small>
        </div>
        <Icon name="down" size={14} />
      </div>
      <p className="nav-label">YOUR WORKSPACE</p>
      <nav>
        {[
          ['proposals', 'file', 'Proposal readiness'],
          ['today', 'home', 'Overview'],
          ['opportunities', 'inbox', 'Opportunities'],
          ['profile', 'person', 'Project profile'],
          ['connections', 'link', 'Connections'],
        ].map(([id, icon, label]) => (
          <button
            key={id}
            className={'nav-item ' + (page === id ? 'active' : '')}
            onClick={() => setPage(id)}
          >
            <Icon name={icon} />
            {label}
            {id === 'opportunities' && (
              <span className="nav-count">{data?.opportunities.length || 0}</span>
            )}
          </button>
        ))}
      </nav>
      <div className="sidebar-demo">
        <div className="eyebrow">
          <span className="dot amber" /> TRY THE COMPLETE JOURNEY
        </div>
        <p>A safe place to see it work.</p>
        <span>Fictional emails. Real workflow.</span>
        <button disabled={busy} onClick={() => void scenario('welcome')}>
          Load demo workspace <Icon name="arrow" size={16} />
        </button>
      </div>
      <div className="sidebar-foot">
        <Icon name="shield" size={17} />
        <div>
          Evidence at every step<small>Prepared ≠ submitted.</small>
        </div>
      </div>
    </aside>
  );
}

export function PackageDialog() {
  const { preview, setPreview, op, busy, act } = useView();
  if (!preview || !op) return null;
  return (
    <div className="modal-backdrop">
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="preview-title">
        <button className="modal-close" aria-label="Close preview" onClick={() => setPreview(null)}>
          <Icon name="close" />
        </button>
        <p className="eyebrow">REVIEW BEFORE YOU APPROVE</p>
        <h2 id="preview-title">The complete package.</h2>
        <p className="muted">
          {preview.title} · Revision {preview.revision} ·{' '}
          {preview.mode === 'fixture' ? 'Fictional demo' : 'Live sources'}
        </p>
        {preview.revision !== op.revision && (
          <div className="notice error">
            This preview is stale. Close it and review the current revision.
          </div>
        )}
        {preview.requirements.map((r) => (
          <div className="preview-answer" key={r.id}>
            <h4>
              {r.title}
              <span className="badge">
                {preview.package.answers[r.requirement_key]?.confirmed
                  ? 'Reviewed'
                  : 'Needs review'}
              </span>
            </h4>
            <p>{preview.package.answers[r.requirement_key]?.answer || 'Not supplied'}</p>
            <small>Requirement source: “{r.quote}”</small>
          </div>
        ))}
        {preview.blockers.length > 0 && (
          <div className="notice warning">Still to review: {preview.blockers.join(' · ')}</div>
        )}
        <p className="small-note">
          Approval covers these exact answers. You submit externally. A receipt is reviewed
          separately.
        </p>
        <div className="button-row">
          <button
            className="button primary"
            disabled={
              busy ||
              !!preview.blockers.length ||
              preview.revision !== op.revision ||
              op.workflow === 'closed'
            }
            onClick={() =>
              void act(async () => {
                await api(`/obligations/${op.id}/approve`, 'POST', {
                  expected_revision: preview.revision,
                });
                setPreview(null);
              }, 'Package approved. Nothing has been submitted.')
            }
          >
            Approve revision {preview.revision}
          </button>
          {op.package.approval_revision === op.revision && (
            <>
              <a className="button secondary" href={`/api/obligations/${op.id}/export`} download>
                Download package
              </a>
              {op.workflow === 'ready' && (
                <button
                  className="button secondary"
                  disabled={busy}
                  onClick={() =>
                    void act(async () => {
                      await api(`/obligations/${op.id}/submitted`, 'POST', {
                        expected_revision: op.revision,
                      });
                      setPreview(null);
                    }, 'Marked submitted by you. A receipt is still needed.')
                  }
                >
                  I submitted externally
                </button>
              )}
            </>
          )}
        </div>
      </section>
    </div>
  );
}

export function ImportDialog() {
  const { setPage, setImportOpen, importText, setImportText, busy, act, watch } = useView();
  return (
    <div className="modal-backdrop">
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="import-title">
        <button
          className="modal-close"
          aria-label="Close import"
          onClick={() => setImportOpen(false)}
        >
          <Icon name="close" />
        </button>
        <p className="eyebrow">SELECTED SOURCES ONLY</p>
        <h2 id="import-title">Bring your emails together.</h2>
        <p className="muted">
          Connect Gmail in Connections, or paste an email JSON export. Live imports send selected
          text to Nebius and require a configured key and model.
        </p>
        <label className="field-label">
          Email JSON array
          <textarea
            rows={10}
            value={importText}
            onChange={(e) => setImportText(e.target.value)}
            placeholder={
              '[{"id":"…","thread_id":"…","subject":"…","sender":"…","received_at":"2026-10-21T09:00:00Z","body":"…"}]'
            }
          />
        </label>
        <div className="button-row">
          <button
            className="button primary"
            disabled={busy || !importText.trim()}
            onClick={() =>
              void act(async () => {
                const job = await api<Job>('/imports', 'POST', {
                  messages: JSON.parse(importText),
                  mode: 'live',
                  command_key: crypto.randomUUID(),
                });
                watch(job);
                setImportOpen(false);
              })
            }
          >
            Process with Nebius
          </button>
          <button
            className="button secondary"
            onClick={() => {
              setImportOpen(false);
              setPage('connections');
            }}
          >
            Gmail connection
          </button>
        </div>
      </section>
    </div>
  );
}

export function Frame() {
  const {
    data,
    page,
    setPage,
    selected,
    setSelected,
    tab,
    setTab,
    sourceId,
    setSourceId,
    error,
    setError,
    toast,
    preview,
    setPreview,
    liveJob,
    stage,
    importOpen,
    setImportOpen,
    importText,
    setImportText,
    op,
    busy,
    stats,
    fmtDate,
    showSource,
    saveAnswer,
    act,
    scenario,
    watch,
  } = useView();
  return (
    <main>
      <header className="topbar">
        <div>
          <span className="breadcrumb">Workspace</span>
          <span className="slash">/</span>
          {page === 'today'
            ? 'Overview'
            : page === 'profile'
              ? 'Project profile'
              : page === 'connections'
                ? 'Connections'
                : 'Opportunities'}
        </div>
        <div className="top-right">
          <span className="local-pill">
            <span className="dot" /> Local workspace
          </span>
          <span className="avatar small">G</span>
        </div>
      </header>
      <div className="content">
        {error && (
          <div className="notice error" role="alert">
            <Icon name="shield" />
            {error}
            <button aria-label="Dismiss error" onClick={() => setError('')}>
              <Icon name="close" size={16} />
            </button>
          </div>
        )}
        {liveJob && ['queued', 'running'].includes(liveJob.status) && (
          <div className="notice processing" role="status">
            <span className="spinner" />
            {liveJob.kind === 'draft' ? 'Preparing your package' : 'Processing selected sources'}
            <span className="muted">{stage}</span>
          </div>
        )}
        {data ? (
          <>
            {(page === 'today' || page === 'opportunities') && <Overview />}
            {page === 'profile' && (
              <Profile
                data={data}
                busy={busy}
                onSave={(facts) =>
                  act(
                    () => api('/profile', 'PUT', { facts }),
                    'Profile facts saved. Relevant approvals need a fresh review.',
                  )
                }
                onDemo={() =>
                  act(
                    () => api('/demo/profile', 'POST', {}),
                    'Fictional project facts loaded. Demo links are placeholders.',
                  )
                }
                onClear={() => act(() => api('/profile', 'DELETE'), 'Profile facts removed.')}
              />
            )}
            {page === 'connections' && (
              <Connections data={data} busy={busy} run={act} onJob={watch} />
            )}
            {data.jobs.some((j) => j.status === 'failed') && (
              <section className="failed-jobs">
                <h3>Processing needs attention</h3>
                {data.jobs
                  .filter((j) => j.status === 'failed')
                  .map((j) => (
                    <div key={j.id}>
                      <span>{j.error}</span>
                      <button
                        className="mini-button"
                        disabled={busy}
                        onClick={() =>
                          void act(async () =>
                            watch(await api<Job>(`/jobs/${j.id}/retry`, 'POST', {})),
                          )
                        }
                      >
                        Retry job
                      </button>
                    </div>
                  ))}
              </section>
            )}
            <footer>
              <span>
                FollowThrough <span className="footer-dot">·</span> Built to finish, grounded in
                evidence.
              </span>
              <span>Personal AI workspace</span>
            </footer>
          </>
        ) : (
          <div className="loading">
            <span className="spinner" /> Opening your workspace…
          </div>
        )}
      </div>
    </main>
  );
}
