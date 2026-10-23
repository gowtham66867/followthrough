export interface Answer {
  answer: string;
  confirmed: boolean;
  fact_keys: string[];
  provenance: string;
}
export interface Requirement {
  id: string;
  requirement_key: string;
  title: string;
  required: number;
  source_id: string;
  quote: string;
}
export interface Source {
  id: string;
  subject: string;
  sender: string;
  received_at: string;
  body: string;
  mode: string;
  external_url?: string;
}
export interface Deadline {
  source_id: string;
  quote: string;
  due_at: string | null;
  timezone?: string;
  ambiguity?: string;
  confirmed: boolean;
}
export interface Receipt {
  id: string;
  source_id: string;
  quote: string;
  verdict: string;
  reason: string;
  reviewed: number;
}
export interface Activity {
  id: number;
  kind: string;
  detail_json: string;
  created_at: string;
}
export interface Turn {
  id: number;
  role: string;
  text: string;
}
export interface Opportunity {
  id: string;
  title: string;
  organizer: string;
  mode: string;
  revision: number;
  workflow: string;
  completion_basis: string;
  deadline: { candidates: Deadline[]; selected: Deadline | null } | null;
  requirements: Requirement[];
  blockers: string[];
  messages: Source[];
  receipts: Receipt[];
  events: Activity[];
  conversation: Turn[];
  package: {
    revision: number;
    approval_revision: number | null;
    approval_hash: string | null;
    answers: Record<string, Answer>;
  };
}
export interface Job {
  id: string;
  kind: string;
  mode: string;
  status: string;
  error?: string;
}
export interface Settings {
  timezone: string;
  model: string;
  nebius_key_configured: boolean;
  deployment: string;
  data_policy: string;
  gmail: { configured: boolean; connected: boolean; scope: string; storage: string };
}
export interface Fact {
  key: string;
  value: string;
  provenance: string;
}
export interface Snapshot {
  opportunities: Opportunity[];
  jobs: Job[];
  facts: Fact[];
  settings: Settings;
}
