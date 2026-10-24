"""One readiness contract for review, approval, export and actionable navigation."""
from .proposals import answer_supported, evidence_valid


def issues(d):
    result=[]
    def add(identity,category,title,action,target,*,key=None,source_id=None,blocking=True,detail='',requirement_keys=None,citations=None,section=None):
        result.append({'id':identity,'category':category,'title':title,'detail':detail,'blocking':blocking,
                       'requirement_keys':requirement_keys or ([key] if key else []),'citations':citations or [],
                       'target':{'view':target,'requirement_key':key,'source_id':source_id,**({'section':section} if section else {})},'action':action})
    active=[r for r in d['requirements'] if r['status']!='withdrawn']
    if not active:
        add('requirements:none','requirements','Analyze and review at least one requirement','Import or analyze an RFP','Sources')
    for s in d['sources']:
        if (s.get('ingestion') or {}).get('review_required') and not s.get('transcription_reviewed'):
            add('transcription:'+s['id'],'sources','Review visual transcription: '+s['filename'],
                'Compare original pages','Sources',source_id=s['id'])
        if not s.get('receipt') and not s.get('attachment') and not s.get('analyzed'):
            add('analysis:'+s['id'],'sources','Analyze source: '+s['filename'],'Open source analysis','Sources',source_id=s['id'],
                detail='Analyze this amendment to identify affected requirements.' if s['amendment'] else 'Extract proposed requirements, then verify them.')
    for r in active:
        key=r['key'];a=d['answers'].get(key,{})
        if r['status']!='confirmed':
            add('requirement:'+key,'requirements','Review requirement: '+r['title'],'Review requirement and source','Requirements',key=key,source_id=r['source_id'])
        if r['required']:
            if not a.get('text','').strip():
                add('answer:'+key,'answers','Review answer: '+r['title'],'Prepare missing answer','Requirements',key=key)
            else:
                if not a.get('reviewed'):
                    add('answer:'+key,'answers','Review answer: '+r['title'],'Review answer','Requirements',key=key)
                if not answer_supported(d,a) and not a.get('exception','').strip():
                    add('support:'+key,'evidence','Unsupported answer: '+r['title'],'Check evidence or document exception','Requirements',key=key,
                        detail='Answer text must match approved, unexpired evidence or have an explicit owner exception. Matching text does not establish relevance.')
            if r['attachment'] and not any(s.get('attachment')==key for s in d['sources']):
                add('attachment:'+key,'attachments','Missing attachment: '+r['title'],'Import required attachment','Import',key=key)
        elif not a.get('text','').strip():
            add('optional:'+key,'answers','Optional answer omitted: '+r['title'],'Review optional answer','Requirements',key=key,blocking=False)
        if a.get('exception','').strip():
            add('exception:'+key,'exceptions','Owner exception: '+r['title'],'Inspect documented exception','Requirements',key=key,blocking=False,detail=a['exception'])
        task=next((t for t in d['tasks'] if t['requirement_key']==key),None)
        if any(i['blocking'] and i['target']['requirement_key']==key for i in result) and (not task or not task['owner'].strip()):
            add('owner:'+key,'owners','Unassigned follow-up: '+r['title'],'Assign missing-input owner','Requirements',key=key,blocking=False,
                detail='Ownership is a follow-up recommendation, not an approval requirement.',section='owner')
    if not d['deadline'] or not d['deadline'].get('confirmed'):
        add('deadline','deadline','Confirm the submission deadline','Review deadline and source','Deadline',source_id=(d['deadline'] or {}).get('source_id'))
    review=d.get('risk_review')
    if review:
        from .proposal_risks import fingerprint
        if review['fingerprint']!=fingerprint(d):
            add('risk:stale','conflicts','Refresh outdated conflict review','Refresh cited conflict review','Conflict review')
        else:
            for item in review['issues']:
                if not item['decision']:
                    add('risk:'+item['id'],'conflicts','Decide review finding: '+item['summary'],'Review citations and record decision','Conflict review',detail=item['question'],requirement_keys=item['requirement_keys'],citations=item['citations'])
    return result


def report(d,items=None):
    items=issues(d) if items is None else items
    blocking=[i for i in items if i['blocking']]
    return {'revision':d['revision'],'status':'blocked' if blocking else 'approved' if d.get('approved_current') else 'ready_for_review',
            'ready_for_approval':not blocking,'blocking_count':len(blocking),'advisory_count':len(items)-len(blocking),
            'issues':items,'checks':[{'category':category,'blocking_count':sum(i['blocking'] and i['category']==category for i in items),
                'advisory_count':sum(not i['blocking'] and i['category']==category for i in items)} for category in
                ['sources','requirements','answers','evidence','attachments','deadline','conflicts','exceptions','owners']],
            'conflict_review':'not_run' if not d.get('risk_review') else 'current' if d['risk_review'].get('current') else 'outdated',
            'approval':d.get('approval'),'last_approval':d['approval'] if d.get('approval') and not d.get('approved_current') else (d.get('approval_history') or [None])[-1]}


def impact_map(d,items):
    by_source={s['id']:s for s in d['sources']};by_evidence={e['id']:e for e in d['evidence']}
    last_approval=d['approval'] if d.get('approval') and not d.get('approved_current') else (d.get('approval_history') or [None])[-1]
    rows=[]
    for r in d['requirements']:
        a=d['answers'].get(r['key'],{});source=by_source.get(r['source_id'],{})
        attached=[{'id':s['id'],'filename':s['filename'],'reviewed':not (s.get('ingestion') or {}).get('review_required') or bool(s.get('transcription_reviewed'))} for s in d['sources'] if s.get('attachment')==r['key']]
        task=next((t for t in d['tasks'] if t['requirement_key']==r['key']),None)
        refs=[]
        for eid in a.get('evidence_ids',[]):
            e=by_evidence.get(eid)
            refs.append({'id':eid,'title':e['title'] if e else 'Unavailable evidence','version':e['version'] if e else None,
                         'valid':bool(e and evidence_valid(e)),'expires_on':e.get('expires_on') if e else None})
        linked=[i['id'] for i in items if r['key'] in i['requirement_keys']]
        row_blockers=[i['id'] for i in items if i['blocking'] and r['key'] in i['requirement_keys']]
        previous=r.get('previous')
        previous_source=by_source.get((previous or {}).get('source_id'),{})
        rows.append({'key':r['key'],'title':r['title'],'required':r['required'],'version':r['version'],'status':r['status'],
            'change':'changed' if previous else 'added_by_amendment' if source.get('amendment') else 'original',
            'source':{'id':r['source_id'],'filename':source.get('filename','Unknown source'),'quote':r['quote'],
                      'location':next((l['location'] for l in reversed(source.get('locations',[])) if l['start']<=r['start']),'Source text')},
            'previous':{**previous,'filename':previous_source.get('filename','Previous source')} if previous else None,
            'answer':{'present':bool(a.get('text','').strip()),'reviewed':bool(a.get('reviewed')),'supported':answer_supported(d,a),
                      'exception':a.get('exception','')},'evidence':refs,'attachment_required':r['attachment'],'attachments':attached,
            'task':task,'issue_ids':linked,'blocking_issue_ids':row_blockers,
            'package_approval':{'current':d['approved_current'],'approved_revision':d['approval']['revision'] if d['approval'] else None,
                                'previous_revision':last_approval['revision'] if last_approval else None}})
    return {'rows':rows,'changed_count':sum(r['change']!='original' for r in rows),
            'pending_amendments':[{'id':s['id'],'filename':s['filename']} for s in d['sources'] if s.get('amendment') and not s.get('analyzed') and not s.get('receipt') and not s.get('attachment')],
            'scope':'Links reflect stored source IDs, requirement keys and selected evidence; semantic relevance and amendment authority require human review.'}
