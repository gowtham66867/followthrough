"""Strict contracts for proposal analysis and human review."""
from pydantic import BaseModel, ConfigDict, Field

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')

class ExtractedRequirement(Strict):
    key: str = Field(pattern=r'^[a-z][a-z0-9_]{1,79}$')
    title: str = Field(min_length=1, max_length=500)
    quote: str = Field(min_length=1, max_length=4000)
    required: bool = True
    attachment: bool = False

class ExtractedDeadline(Strict):
    quote: str = Field(min_length=1, max_length=2000)
    due_at: str | None = None

class ProposalAnalysis(Strict):
    requirements: list[ExtractedRequirement] = Field(max_length=80)
    deadline: ExtractedDeadline | None = None

class CreateProposal(Strict):
    title: str = Field(min_length=1, max_length=200)
    client: str = Field(min_length=1, max_length=200)

class SourceInput(Strict):
    filename: str = Field(min_length=1, max_length=200)
    text: str = Field(default='', max_length=80000)
    base64: str = Field(default='', max_length=4_000_000)
    amendment: bool = False
    receipt: bool = False
    attachment: str = Field(default='', max_length=80)

class Revision(Strict):
    expected_revision: int

class AnswerInput(Revision):
    text: str = Field(max_length=16000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)
    reviewed: bool = False
    exception: str = Field(default='', max_length=2000)

class EvidenceInput(Revision):
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=16000)
    approved: bool = False
    expires_on: str | None = None
    id: str | None = None

class ReviewInput(Revision):
    decision: str = Field(pattern=r'^(confirmed|withdrawn)$')

class DeadlineInput(Revision):
    due_at: str
    source_id: str

class TaskInput(Revision):
    requirement_key: str
    owner: str = Field(max_length=200)
    due_on: str | None = None
    done: bool = False

class ReceiptInput(Revision):
    source_id: str
    quote: str = Field(min_length=1, max_length=4000)
    kind: str = Field(pattern=r'^(submission|acknowledgement)$')
