"""Fictional fixtures. These interpretations never run on arbitrary email."""
from .schemas import Message, Extraction

OPPORTUNITY = 'open-build-2026'
TITLE = 'Open Build Challenge'
ORGANIZER = 'Open Build team'
FACTS = {
    'project_summary': 'FollowThrough turns selected email threads into a sourced preparation checklist, reviewed answers and receipt-linked history.',
    'repository_url': 'https://github.com/example/followthrough-demo',
    'demo_url': 'https://example.com/followthrough-demo',
    'video_url': 'https://www.youtube.com/watch?v=DEMO_ONLY',
    'tool_feedback': 'Fictional demo feedback. Replace this with observations from a real Nebius run before submitting.',
}

SCENARIOS = {
    'welcome': [
        ('demo-registration', 'You are registered', '2026-10-20T09:00:00+00:00',
         'You are registered for Open Build Challenge. Your event reference is OPENBUILD-2026. Registration is not a project submission.'),
        ('demo-requirements', 'Your submission checklist', '2026-10-21T08:00:00+00:00',
         'For Open Build Challenge, provide a public repository URL, a working demo URL, a project summary, and a public video URL. Submissions close October 30, 2026 at 10:00 AM PDT (UTC-07:00).'),
    ],
    'change': [
        ('demo-change', 'Updated deadline and one new requirement', '2026-10-22T08:00:00+00:00',
         'For Open Build Challenge, include specific feedback on the tools used. The new deadline is October 29, 2026 at 10:00 AM PDT (UTC-07:00); this replaces the earlier deadline.'),
    ],
    'wrong-receipt': [
        ('demo-wrong-receipt', 'Your submission was received', '2026-10-23T08:00:00+00:00',
         'Your submission for a different event, Winter Build Challenge, was received. Event reference WINTERBUILD-2026.'),
    ],
    'receipt': [
        ('demo-receipt', 'We received your Open Build project', '2026-10-24T08:00:00+00:00',
         'Your project submission for Open Build Challenge was received. Event reference OPENBUILD-2026. This confirms receipt, not acceptance or an award.'),
    ],
}


def messages_for(scenario):
    if scenario not in SCENARIOS:
        raise ValueError('Unknown demo scenario')
    return [Message(id=key, thread_id='demo-open-build', subject=subject,
                    sender='organizer@example.com', received_at=received, body=body)
            for key, subject, received, body in SCENARIOS[scenario]]


def extract(messages):
    known = {m.id: m for scenario in SCENARIOS for m in messages_for(scenario)}
    claims = []
    for message in messages:
        if message.id not in known or message.model_dump() != known[message.id].model_dump():
            raise ValueError('Fixture mode only accepts the unchanged fictional demo messages')
        def add(kind, quote, **fields):
            start = message.body.index(quote)
            claims.append(dict(type=kind, source_id=message.id, quote=quote,
                               span_start=start, span_end=start + len(quote),
                               opportunity_id=OPPORTUNITY, opportunity_title=TITLE,
                               organizer=ORGANIZER, **fields))
        rules = {
            'demo-registration': [('registration', message.body, {'application_ref': 'OPENBUILD-2026'})],
            'demo-requirements': [
                ('requirement', quote, {'key': key, 'title': title}) for key, title, quote in [
                    ('repository_url', 'Public code repository', 'a public repository URL'),
                    ('demo_url', 'Working demo', 'a working demo URL'),
                    ('project_summary', 'Project description', 'a project summary'),
                    ('video_url', 'Public demo video', 'a public video URL'),
                ]
            ] + [('deadline', 'Submissions close October 30, 2026 at 10:00 AM PDT (UTC-07:00).',
                  {'due_at': '2026-10-30T17:00:00+00:00', 'timezone': 'America/Los_Angeles'})],
            'demo-change': [
                ('requirement', 'include specific feedback on the tools used', {'key': 'tool_feedback', 'title': 'Feedback on tools used'}),
                ('deadline', 'The new deadline is October 29, 2026 at 10:00 AM PDT (UTC-07:00); this replaces the earlier deadline.',
                 {'due_at': '2026-10-29T17:00:00+00:00', 'timezone': 'America/Los_Angeles'}),
            ],
            'demo-receipt': [('receipt', message.body, {'receipt_type': 'submission', 'application_ref': 'OPENBUILD-2026'})],
            'demo-wrong-receipt': [('receipt', message.body, {'receipt_type': 'submission', 'application_ref': 'WINTERBUILD-2026'})],
        }
        for kind, quote, fields in rules[message.id]:
            add(kind, quote, **fields)
    return Extraction.model_validate({'claims': claims})
