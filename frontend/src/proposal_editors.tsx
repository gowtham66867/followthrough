import React,{useState} from 'react';
import {SemanticEvidence} from './proposal_intelligence';
import type {Proposal,ProposalRequirement,ProposalAnswer,CompanyEvidence} from './proposal_types';

export function ProposalAnswerEditor({op,requirement,busy,onSave,onSearch}:{op:Proposal;onSearch:()=>void;requirement:ProposalRequirement;busy:boolean;onSave:(key:string,body:ProposalAnswer)=>void}){
 const existing=op.answers[requirement.key];
 const [text,setText]=useState(existing?.text||'');
 const [refs,setRefs]=useState<string[]>(existing?.evidence_ids||[]);
 const [exception,setException]=useState(existing?.exception||'');
 const [reviewed,setReviewed]=useState(existing?.reviewed||false);
 const supported=!!refs.length && text===op.evidence.filter(e=>refs.includes(e.id)).map(e=>e.text).join('\n\n') && op.evidence.filter(e=>refs.includes(e.id)).every(e=>e.approved&&(!e.expires_on||e.expires_on>=new Date().toISOString().slice(0,10)));
 return <div className="p-answer"><SemanticEvidence result={op.retrieval?.[requirement.key]} busy={busy} onSearch={onSearch} onUse={id=>{const e=op.evidence.find(e=>e.id===id);if(e){setRefs([id]);setText(e.text);setReviewed(false);setException('')}}}/><label>Proposal answer<textarea aria-label={`Answer for ${requirement.key}`} value={text} onChange={e=>{setText(e.target.value);setReviewed(false)}} rows={5}/></label>
 <div className="p-evidence-options"><strong>Approved evidence</strong>{op.evidence.filter(e=>e.approved).map(e=><label key={e.id}><input type="checkbox" checked={refs.includes(e.id)} onChange={event=>{const next=event.target.checked?[...refs,e.id]:refs.filter(id=>id!==e.id);setRefs(next);setText(op.evidence.filter(item=>next.includes(item.id)).map(item=>item.text).join('\n\n'));setReviewed(false)}}/>{e.title} <small>v{e.version}</small></label>)}</div>
 <p className={supported?'p-supported':'p-warning'}>{supported?'Verbatim approved evidence • check relevance before review':'Unsupported or edited answer • add evidence or record an explicit owner exception'}</p>
 {!supported&&<label>Owner exception or verified factual correction<textarea aria-label={`Exception for ${requirement.key}`} rows={2} value={exception} onChange={e=>setException(e.target.value)} placeholder="Explain the evidence gap and who verified this answer. This is recorded in the internal review."/></label>}
 <label className="p-check"><input type="checkbox" checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/> I reviewed this answer against the requirement.</label>
 <button className="button primary" disabled={busy} onClick={()=>onSave(requirement.key,{text,evidence_ids:refs,reviewed,exception})}>Save answer</button></div>
}

export function EvidenceForm({busy,onSave,item}:{busy:boolean;onSave:(body:unknown)=>void;item?:CompanyEvidence}){
 const [title,setTitle]=useState(item?.title||''),[text,setText]=useState(item?.text||''),[approved,setApproved]=useState(item?.approved||false),[expires,setExpires]=useState(item?.expires_on||'');
 return <form className="p-form" onSubmit={e=>{e.preventDefault();onSave({title,text,approved,expires_on:expires||null,id:item?.id||null})}}><h3>{item?'Review evidence':'Add company evidence'}</h3><label>Evidence title<input required value={title} onChange={e=>setTitle(e.target.value)}/></label><label>Verified facts<textarea required rows={5} value={text} onChange={e=>setText(e.target.value)}/></label><label>Expiry date if applicable<input type="date" value={expires} onChange={e=>setExpires(e.target.value)}/></label><label className="p-check"><input type="checkbox" checked={approved} onChange={e=>setApproved(e.target.checked)}/> I approve this evidence for this opportunity.</label><button disabled={busy} className="button primary">Save evidence</button></form>
}

export function TaskForm({op,requirement,busy,onSave}:{op:Proposal;requirement:ProposalRequirement;busy:boolean;onSave:(body:unknown)=>void}){
 const task=op.tasks.find(t=>t.requirement_key===requirement.key);
 const [owner,setOwner]=useState(task?.owner||''),[due,setDue]=useState(task?.due_on||''),[done,setDone]=useState(task?.done||false);
 return <details id={'task-'+requirement.key} tabIndex={-1}><summary>Assign missing input {task?`· ${task.owner}`:''}</summary><form className="p-task" onSubmit={e=>{e.preventDefault();onSave({requirement_key:requirement.key,owner,due_on:due||null,done})}}><label>Owner<input required value={owner} onChange={e=>setOwner(e.target.value)}/></label><label>Due date<input type="date" value={due} onChange={e=>setDue(e.target.value)}/></label><label className="p-check"><input type="checkbox" checked={done} onChange={e=>setDone(e.target.checked)}/>Task done</label><button className="button secondary" disabled={busy}>Save task</button><small>Completing a task does not approve its answer.</small></form></details>
}
