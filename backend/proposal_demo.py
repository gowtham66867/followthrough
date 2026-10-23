"""Explicitly fictional RFP walkthrough; never a fallback for live failures."""
from .proposal_schema import ProposalAnalysis, EvidenceInput

RFP = '''Northstar Retail requests a proposal for the Northstar Customer Portal.
Provide a technical approach for the customer portal.
Provide a delivery plan for a twelve week implementation.
Include two relevant case studies.
Complete the security questionnaire.
Provide a commercial proposal.
Submissions close October 30, 2026 at 17:00 UTC.
'''
AMENDMENT = '''Amendment to Northstar Customer Portal from Northstar Retail.
Provide a revised delivery plan with a four week discovery phase.
Attach a completed security controls workbook as a separate file.
Clarify whether your agency holds ISO 27001 certification; do not claim certification without a valid certificate.
The revised submission deadline is October 29, 2026 at 17:00 UTC.
'''
BASE = [
 ('technical_approach', 'Technical approach for the customer portal', 'Provide a technical approach for the customer portal.', False),
 ('delivery_plan', 'Delivery plan for a twelve week implementation', 'Provide a delivery plan for a twelve week implementation.', False),
 ('case_studies', 'Two relevant case studies', 'Include two relevant case studies.', False),
 ('security_questionnaire', 'Complete security questionnaire', 'Complete the security questionnaire.', False),
 ('commercial_proposal', 'Commercial proposal', 'Provide a commercial proposal.', False),
]
CHANGES = [
 ('delivery_plan', 'Revised delivery plan with four week discovery', 'Provide a revised delivery plan with a four week discovery phase.', False),
 ('security_workbook', 'Separate completed security controls workbook', 'Attach a completed security controls workbook as a separate file.', True),
 ('certification', 'Clarify ISO 27001 certification with valid evidence', 'Clarify whether your agency holds ISO 27001 certification; do not claim certification without a valid certificate.', False),
]
EVIDENCE = [
 ('Technical approach', 'We propose a customer portal using a React interface and an API service, with customer authentication and automated tests.'),
 ('Delivery plan', 'Our proposed twelve week delivery plan includes discovery, implementation, verification and handover. Delivery timing is subject to an agreed scope.'),
 ('Case studies', 'Case study one: fictional Atlas Studio delivered an account portal for Example Retail. Case study two: fictional Atlas Studio delivered a support dashboard for Example Services.'),
 ('Security questionnaire', 'Our security questionnaire response covers access controls, backups and incident handling. We do not hold ISO 27001 certification.'),
 ('Commercial proposal', 'Our commercial proposal will use milestone payments against an agreed scope. This fictional example deliberately contains no binding price.'),
]


def analysis(amendment=False):
    rows = CHANGES if amendment else BASE
    quote = ('The revised submission deadline is October 29, 2026 at 17:00 UTC.' if amendment else 'Submissions close October 30, 2026 at 17:00 UTC.')
    return ProposalAnalysis.model_validate({'requirements': [dict(key=k, title=t, quote=q, required=True, attachment=a) for k,t,q,a in rows], 'deadline': {'quote': quote, 'due_at': '2026-10-29T17:00:00+00:00' if amendment else '2026-10-30T17:00:00+00:00'}})


def seed(service):
    d = service.create('Northstar Customer Portal', 'Northstar Retail', fictional=True)
    d = service.add_source(d['id'], d['revision'], 'Fictional Northstar RFP.txt', RFP, [{'location':'Text','start':0}])
    d = service.apply_analysis(d['id'], d['revision'], d['sources'][0]['id'], analysis(), {'model':'explicit fictional walkthrough', 'mode':'fixture'})
    for title, text in EVIDENCE:
        d = service.evidence(d['id'], EvidenceInput(expected_revision=d['revision'], title=title, text=text, approved=True))
    return d


def amend(service, pid, revision):
    d = service.get(pid)
    if not d['fictional']:
        raise ValueError('Fictional amendments are only available in fictional workspaces')
    d = service.add_source(pid, revision, 'Fictional client amendment.txt', AMENDMENT, [{'location':'Text','start':0}], amendment=True)
    return service.apply_analysis(pid, d['revision'], d['sources'][-1]['id'], analysis(True), {'model':'explicit fictional walkthrough', 'mode':'fixture'})
