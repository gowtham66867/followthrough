from __future__ import annotations

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Message(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1, max_length=250)
    thread_id: str = Field(min_length=1, max_length=250)
    subject: str = Field(min_length=1, max_length=2000)
    sender: str = Field(min_length=1, max_length=500)
    received_at: datetime
    body: str = Field(min_length=1, max_length=80000)
    external_url: str | None = None

    @field_validator('received_at')
    @classmethod
    def aware(cls, value):
        if value.utcoffset() is None:
            raise ValueError('Message timestamp needs a timezone')
        return value


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    messages: list[Message] = Field(min_length=1, max_length=50)
    mode: Literal['live'] = 'live'
    command_key: str = Field(min_length=8, max_length=200)


class Claim(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['registration', 'requirement', 'deadline', 'receipt']
    source_id: str
    quote: str = Field(min_length=1)
    span_start: int = Field(ge=0)
    span_end: int = Field(gt=0)
    opportunity_id: str = Field(pattern=r'^[a-z0-9][a-z0-9-]{2,100}$')
    opportunity_title: str = Field(min_length=1, max_length=300)
    organizer: str = Field(min_length=1, max_length=200)
    key: str = Field(default='', max_length=100)
    title: str = Field(default='', max_length=1000)
    required: bool = True
    due_at: str | None = None
    timezone: str | None = None
    ambiguity: str | None = None
    application_ref: str | None = None
    receipt_type: Literal['submission', 'registration', 'acceptance', 'other'] | None = None


class Extraction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    claims: list[Claim] = Field(max_length=100)


class RevisionCommand(BaseModel):
    expected_revision: int = Field(ge=1)


class AnswerCommand(RevisionCommand):
    answer: str = Field(max_length=16000)
    confirm: bool = True


class ReceiptCommand(RevisionCommand):
    receipt_id: str
    decision: Literal['confirm', 'reject']


class ChatCommand(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    field_key: str | None = None
    expected_revision: int | None = None


class FactsCommand(BaseModel):
    facts: dict[str, str]

    @field_validator('facts')
    @classmethod
    def bounded(cls, value):
        if len(value) > 30 or any(len(k) > 100 or len(v) > 16000 for k, v in value.items()):
            raise ValueError('Profile is too large')
        return value


class DeadlineCommand(RevisionCommand):
    source_id: str
    due_at: str | None = None
