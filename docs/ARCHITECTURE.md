# Architecture and limits

FollowThrough is a single-owner local proposal workspace. Its HTTP boundary is loopback Host/Origin validation plus a local HttpOnly session cookie. This is not multi-user authentication.

## Decision boundaries

NVIDIA Nemotron 3 Nano on Nebius Token Factory extracts proposed requirements and deadlines from selected source text. The model cannot approve content or submit proposals. It returns strict JSON. Application code locates exact, unique quotations and derives character offsets. Unsupported quotations and malformed output fail before transaction commit.

A citation proves text exists, not that an interpretation is correct. Requirement confirmation remains a human decision. Ambiguous dates remain unconfirmed. Amendments preserve original sources and old requirement passages. They propose replacement requirements using model keys; users must inspect the matching because key stability is not guaranteed.

Offline evidence matching uses keywords. Optional semantic search embeds approved, current evidence passages using Qwen, shortlists up to eight with cosine similarity, and uses NVIDIA Nano chat to assess relevance. Dedicated Qwen reranking is unavailable on the tested account. Retrieval output is advice only, scoped to a requirement/evidence fingerprint, and never changes an answer automatically. Draft answers are exact evidence excerpts. This conservative design avoids fabricating capability claims but does not prove semantic relevance. Reviewed answers without supporting excerpts require an explicit owner exception. Exceptions remain visible in the internal package review, not the client-facing DOCX.

Vision import explicitly sends up to six rendered PDF pages or one PNG/JPEG to NVIDIA Super VL. Originals and model transcriptions are retained. Analysis and receipt confirmation require human transcription review first. Quotes refer to reviewed text; model omissions or visual errors remain possible. If a person edits the transcription, page offsets are replaced by an explicit human-corrected location rather than kept inaccurately.

Optional deeper review uses NVIDIA Super with thinking enabled and a bounded context. Its structured findings must cite exact passages from this opportunity. No reasoning trace is stored. Findings require an owner disposition. Once a review exists, changes to its source/requirement/deadline/approved-evidence fingerprint block approval until review is refreshed. Previous reviews are archived; decisions do not silently alter requirements. Review results and dispositions clear existing approval. Advisory retrieval is nonmaterial and cannot overwrite answers; network results still reject a changed starting package revision.

## Persistence and concurrency

SQLite schema v2 stores original email tables and proposal workspaces. Proposal writes use BEGIN IMMEDIATE and revision checks. Each material change invalidates approval. Approval binds a SHA-256 hash of source content, requirement state, evidence versions, answer text and attachments. Receipt sources and task progress do not change that package hash. Submission and acknowledgement are separate records; prior submission records retain their revision after amendments.

Proposal inference runs in FastAPI's synchronous threadpool. Results compare the starting revision before commit. The older email workflow has a persistent single-process job queue with recovery and SSE. There are no distributed worker leases; run one server per data directory.

## Files

PDF parser: pdfplumber, maximum 25 pages, readable text required in standard mode; explicit visual mode supports 1–6 pages and human-reviewed model transcription. DOCX parser: bounded ZIP and XML, no archive extraction or macro execution. Input limit 3 MB; expanded DOCX limit 15 MB; text limit 80,000 characters. Locations map extracted character offsets to pages or paragraphs. These are extracted-text coordinates, not exact visual bounding boxes.

The export is a ZIP with minimal standards-based OOXML, internal review JSON and original attachments. Source text, exceptions and evidence are local private records. Do not distribute real workspace data. Generated preview artifacts use fictional data.

## Security limits

No tenant isolation, team roles, encryption at rest, antivirus scanning, independently verified OCR, signed receipt authentication or continuous mail monitoring. Local cookie possession grants workspace access. Arbitrary large HTTP streams without Content-Length are not a hardened internet upload boundary; never expose this service publicly.

Third-party document content is untrusted. Prompts tell the model to treat it as data; schema and grounding checks enforce structural constraints. These checks do not guarantee resistance to all semantic prompt injection. The evaluation contains one synthetic injection example, not a security certification.

## Validation

Automated tests use real API requests, real SQLite, restart persistence, document parsing and package ZIP inspection. Live evaluation uses six fictional extraction examples and three additional synthetic semantic/vision/reasoning cases against actual Nebius inference. Keyword-based recall proxies and exact citation checks are useful smoke checks but cannot substantiate general accuracy or customer impact. Customer validation is outstanding.

## Readiness projection and impact map

`proposal_readiness.py` derives structured issues and dependency rows from persisted proposal state. `proposals.blockers()` consumes the same blocking issues that populate the final review, and approval, export and user-reported submission enforce them. A stored approval hash alone cannot bypass expired evidence or outstanding reviews. Projections are read-only; they are not persisted inside the package document or included recursively in approval hashing. Exported internal review JSON includes the evaluated readiness and impact snapshots.

Dependency edges use existing source IDs, requirement keys, selected evidence IDs, attachment associations and task keys. No new model call infers these edges. Historical before/after text comes from the stored previous requirement version and preserved sources. A requirement-key mismatch can still omit or misassociate an amendment change; the UI explicitly requires human review. Pending unanalyzed amendments are identified separately. Advisory owner assignments and exceptions are distinct from blocking obligations.


## Restricted judge configuration (v0.5)

The default loopback boundary remains unchanged. `run_judge.py` constructs a separate workspace with an exact HTTPS origin and invitation gate in `backend/judge_access.py`. Every private route, including assets, requires the gate before the existing process-local API session. Cookies are Secure/HttpOnly; sessions revoke on restart, invitations expire, and Gmail routes are disabled. This is one shared fictional workspace, not tenant isolation. No live host is deployed.

`backend/provider_budget.py` reserves each outbound HTTP attempt in a SQLite transaction before sending, including retry attempts. The lifetime ledger survives server restarts only when its data directory persists. It has an allowlist, expiry, output and request-size bounds. The ceiling does not represent currency cost; no automatic top-up or public unrestricted inference is offered.

`backend/proposal_dates.py` withholds a proposed date when the cited quote lacks explicit year, time or timezone. This avoids accepting guessed precision while preserving the original quote and human deadline review. It does not prove that a complete-looking source was interpreted correctly.

The evaluation scorer matches author-labelled synthetic obligations one-to-one and separates source quotation validity, label agreement and deadline checks. Raw outputs and guarded scores are both retained; repeated development examples are not held-out validation.
