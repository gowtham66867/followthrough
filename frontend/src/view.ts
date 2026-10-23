import { createContext, useContext } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import type { Job, Opportunity, Snapshot } from './types';

type Setter<T> = Dispatch<SetStateAction<T>>;
export interface WorkspaceView {
  data?: Snapshot;
  op?: Opportunity;
  page: string;
  setPage: Setter<string>;
  selected: string;
  setSelected: Setter<string>;
  tab: string;
  setTab: Setter<string>;
  sourceId: string;
  setSourceId: Setter<string>;
  error: string;
  setError: Setter<string>;
  toast: string;
  preview: Opportunity | null;
  setPreview: Setter<Opportunity | null>;
  liveJob: Job | null;
  stage: string;
  importOpen: boolean;
  setImportOpen: Setter<boolean>;
  importText: string;
  setImportText: Setter<string>;
  busy: boolean;
  stats: Array<{ label: string; value: number; icon: string }>;
  fmtDate: (value: string) => string;
  showSource: (id: string) => void;
  saveAnswer: (key: string, answer: string, revision: number) => Promise<void>;
  act: (fn: () => Promise<unknown>, message?: string) => Promise<void>;
  scenario: (name: string) => Promise<void>;
  watch: (job: Job) => void;
}

export const ViewContext = createContext<WorkspaceView | null>(null);
export function useView() {
  const view = useContext(ViewContext);
  if (!view) throw new Error('Workspace view is unavailable');
  return view;
}
