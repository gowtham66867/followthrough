import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { api } from './api';
import type { Job, Opportunity, Snapshot } from './types';
import './style.css';
import { ViewContext } from './view';
import { Frame, Sidebar, PackageDialog, ImportDialog } from './screens';
import { Icon } from './ui';
import { ProposalWorkspace } from './proposals';

function App() {
  const [data, setData] = useState<Snapshot>();
  const [page, setPage] = useState('proposals');
  const [selected, setSelected] = useState('');
  const [tab, setTab] = useState('Checklist');
  const [sourceId, setSourceId] = useState('');
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');
  const [pending, setPending] = useState(false);
  const [preview, setPreview] = useState<Opportunity | null>(null);
  const [liveJob, setLiveJob] = useState<Job | null>(null);
  const [stage, setStage] = useState('');
  const [importOpen, setImportOpen] = useState(false);
  const [importText, setImportText] = useState('');
  const stream = useRef<EventSource | null>(null);

  async function refresh() {
    const snapshot = await api<Snapshot>('/snapshot');
    setData(snapshot);
    setSelected((old) =>
      snapshot.opportunities.some((o) => o.id === old) ? old : snapshot.opportunities[0]?.id || '',
    );
    return snapshot;
  }
  useEffect(() => {
    void refresh().catch((e) => setError(e.message));
    return () => stream.current?.close();
  }, []);
  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(''), 4500);
      return () => clearTimeout(timer);
    }
  }, [toast]);
  async function act(fn: () => Promise<unknown>, message?: string) {
    setPending(true);
    setError('');
    try {
      await fn();
      await refresh();
      if (message) setToast(message);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending(false);
    }
  }
  function watch(job: Job) {
    stream.current?.close();
    setLiveJob(job);
    setStage('Queued');
    const events = new EventSource(`/api/jobs/${job.id}/events`);
    stream.current = events;
    events.onmessage = (event) => {
      const value = JSON.parse(event.data);
      setStage(value.kind.replaceAll('_', ' '));
    };
    events.addEventListener('complete', () => {
      events.close();
      void api<Job>(`/jobs/${job.id}`)
        .then(async (result) => {
          setLiveJob(result);
          await refresh();
          if (result.status === 'failed') setError(result.error || 'The job failed.');
          else
            setToast(
              result.kind === 'draft'
                ? 'Drafts prepared. Review each answer before approval.'
                : 'Sources processed. Your workspace is up to date.',
            );
        })
        .catch((e) => setError(e.message));
    });
    events.onerror = () => {
      // Browser reconnect uses Last-Event-ID. A refresh also restores durable jobs.
      setStage('Reconnecting to saved progress…');
    };
  }
  useEffect(() => {
    if (!data || (liveJob && ['queued', 'running'].includes(liveJob.status))) return;
    const running = data.jobs.find((j) => ['queued', 'running'].includes(j.status));
    if (running) watch(running);
  }, [data]);
  async function scenario(name: string) {
    await act(async () => {
      const job = await api<Job>('/demo/import', 'POST', {
        scenario: name,
        command_key: crypto.randomUUID(),
      });
      watch(job);
      setPage('today');
    });
  }
  const op = data?.opportunities.find((o) => o.id === selected);
  const activeJobs =
    data?.jobs.some((j) => ['queued', 'running'].includes(j.status)) ||
    (liveJob && ['queued', 'running'].includes(liveJob.status));
  const busy = pending || !!activeJobs;
  const stats = data
    ? [
        {
          label: 'Open opportunities',
          value: data.opportunities.filter((o) => o.workflow !== 'closed').length,
          icon: 'inbox',
        },
        {
          label: 'Items to review',
          value: data.opportunities
            .filter((o) => o.workflow !== 'closed')
            .reduce((n, o) => n + o.blockers.length, 0),
          icon: 'clock',
        },
        {
          label: 'Approved packages',
          value: data.opportunities.filter((o) => o.package.approval_revision === o.revision)
            .length,
          icon: 'file',
        },
        {
          label: 'Receipts confirmed',
          value: data.opportunities.filter((o) => o.completion_basis === 'receipt_confirmed')
            .length,
          icon: 'shield',
        },
      ]
    : [];
  const fmtDate = (value: string) =>
    new Intl.DateTimeFormat('en-IN', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      timeZone: data?.settings.timezone || 'Asia/Kolkata',
    }).format(new Date(value));
  const showSource = (id: string) => {
    setSourceId(id);
    setTab('Evidence');
  };
  const saveAnswer = (key: string, answer: string, revision: number) =>
    act(
      () =>
        api(`/obligations/${op!.id}/answers/${encodeURIComponent(key)}`, 'PATCH', {
          answer,
          expected_revision: revision,
          confirm: true,
        }),
      'Answer saved and reviewed.',
    );

  return (
    <ViewContext.Provider
      value={{
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
      }}
    >
      <div className="app">
        <Sidebar />
        {page === 'proposals' ? <main className="main-content" style={{padding:'36px',flex:1,minWidth:0}}><ProposalWorkspace /></main> : <Frame />}
        {toast && (
          <div className="toast" role="status">
            <Icon name="check" size={18} />
            {toast}
          </div>
        )}
        {preview && op && <PackageDialog />}
        {importOpen && <ImportDialog />}
      </div>
    </ViewContext.Provider>
  );
}

createRoot(document.getElementById('root')!).render(<App />);
