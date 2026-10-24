"""Proposal endpoints share the application's loopback session boundary."""
from io import BytesIO
import base64
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from fastapi import APIRouter
from fastapi.responses import Response
from . import proposal_demo
from . import proposal_retrieval, proposal_risks, proposal_vision
from .proposal_files import read_document, proposal_docx
from .proposal_schema import (CreateProposal, SourceInput, Revision, AnswerInput, EvidenceInput,
                              ReviewInput, DeadlineInput, TaskInput, ReceiptInput, SemanticSearch,
                              RiskDecision, TranscriptionReview)
from .proposals import Proposals
from .store import Conflict


def router(store, config):
    api = APIRouter(prefix='/api/proposals')
    service = Proposals(store, config)

    @api.get('')
    def listing():
        return service.list()

    @api.post('')
    def create(body: CreateProposal):
        return service.create(body.title, body.client)

    @api.post('/demo')
    def demo():
        return proposal_demo.seed(service)

    @api.get('/{pid}')
    def get(pid: str):
        return service.get(pid)

    @api.post('/{pid}/sources')
    def source(pid: str, body: SourceInput, revision: int):
        if service.get(pid)['revision'] != revision:
            raise Conflict('Refresh before importing a source')
        if body.receipt and (body.amendment or body.attachment):
            raise ValueError('Receipt sources cannot also be amendments or attachments')
        if body.vision:
            if not body.base64:
                raise ValueError('Choose an image or PDF file for visual import')
            text, locations, ingestion = proposal_vision.import_visual(config, body.filename, body.base64)
            return service.add_source(pid, revision, body.filename, text, locations, amendment=body.amendment,
                receipt=body.receipt, attachment=body.attachment, encoded=body.base64, ingestion=ingestion)
        text, locations = read_document(body.filename, body.base64) if body.base64 else (body.text, [{'location':'Text','start':0}])
        return service.add_source(pid, revision, body.filename, text, locations, amendment=body.amendment, receipt=body.receipt, attachment=body.attachment, encoded=body.base64)

    @api.post('/{pid}/sources/{sid}/analyze')
    def analyze(pid: str, sid: str, body: Revision):
        return service.analyze(pid, body.expected_revision, sid)

    @api.get('/{pid}/sources/{sid}/pages/{page}')
    def original_page(pid: str, sid: str, page: int):
        source = next((s for s in service.get(pid)['sources'] if s['id'] == sid), None)
        if not source or not (source.get('ingestion') or {}).get('review_required'):
            raise ValueError('Choose a visually imported source')
        return Response(proposal_vision.page_image(source['filename'], proposal_vision.decode(source['original_base64']), page),media_type='image/png')

    @api.post('/{pid}/sources/{sid}/transcription')
    def transcription(pid: str, sid: str, body: TranscriptionReview):
        return proposal_vision.confirm(service,pid,sid,body)

    @api.post('/{pid}/semantic-search')
    def semantic_search(pid: str, body: SemanticSearch):
        return proposal_retrieval.search(service,pid,body.expected_revision,body.requirement_key)

    @api.post('/{pid}/risk-review')
    def risk_review(pid: str, body: Revision):
        return proposal_risks.review(service,pid,body.expected_revision)

    @api.post('/{pid}/risk-review/{issue_id}')
    def risk_decision(pid: str, issue_id: str, body: RiskDecision):
        return proposal_risks.decide(service,pid,issue_id,body)

    @api.post('/{pid}/requirements/{key}/review')
    def review(pid: str, key: str, body: ReviewInput):
        return service.review_requirement(pid, body.expected_revision, key, body.decision)

    @api.post('/{pid}/evidence')
    def evidence(pid: str, body: EvidenceInput):
        return service.evidence(pid, body)

    @api.post('/{pid}/answers/{key}')
    def answer(pid: str, key: str, body: AnswerInput):
        return service.answer(pid, key, body)

    @api.post('/{pid}/draft')
    def draft(pid: str, body: Revision):
        return service.draft(pid, body.expected_revision)

    @api.post('/{pid}/deadline')
    def deadline(pid: str, body: DeadlineInput):
        return service.deadline(pid, body)

    @api.post('/{pid}/tasks')
    def tasks(pid: str, body: TaskInput):
        return service.task(pid, body)

    @api.post('/{pid}/approve')
    def approve(pid: str, body: Revision):
        return service.approve(pid, body.expected_revision)

    @api.post('/{pid}/submission')
    def submitted(pid: str, body: Revision):
        return service.report_submission(pid, body.expected_revision)

    @api.post('/{pid}/receipts')
    def receipt(pid: str, body: ReceiptInput):
        return service.receipt(pid, body)

    @api.post('/{pid}/demo-amendment')
    def amend(pid: str, body: Revision):
        return proposal_demo.amend(service, pid, body.expected_revision)

    @api.get('/{pid}/export')
    def export(pid: str):
        d = service.get(pid)
        if not d['approved_current'] or d['blockers']:
            raise Conflict('Approve the current ready package before export')
        output = BytesIO()
        with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
            archive.writestr('proposal.docx', proposal_docx(d))
            archive.writestr('internal-review.json', json.dumps({k:d.get(k) for k in ('requirements','evidence','answers','deadline','approval','blockers','risk_review','risk_review_history','retrieval','readiness','impact')},indent=2))
            attachments = [s for s in d['sources'] if s.get('attachment')]
            archive.writestr('attachment-manifest.json',json.dumps([{k:s[k] for k in ('id','filename','hash','attachment')} for s in attachments],indent=2))
            for s in attachments:
                filename = s['id'] + '-' + Path(s['filename']).name.replace('\\', '_')
                archive.writestr('attachments/' + filename, base64.b64decode(s['original_base64']) if s.get('original_base64') else s['text'].encode())
        return Response(output.getvalue(),media_type='application/zip',headers={'Content-Disposition':'attachment; filename="followthrough-proposal.zip"'})
    return api
