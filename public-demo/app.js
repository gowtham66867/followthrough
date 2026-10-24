'use strict';

const rfp = `Northstar Retail requests a proposal for the Northstar Customer Portal.
Provide a technical approach for the customer portal.
Provide a delivery plan for a twelve week implementation.
Include two relevant case studies.
Complete the security questionnaire.
Provide a commercial proposal.
Submissions close October 30, 2026 at 17:00 UTC.`;
const amendment = `Amendment to Northstar Customer Portal from Northstar Retail.
Provide a revised delivery plan with a four week discovery phase.
Attach a completed security controls workbook as a separate file.
Clarify whether your agency holds ISO 27001 certification; do not claim certification without a valid certificate.
The revised submission deadline is October 29, 2026 at 17:00 UTC.`;

const definitions = [
  ['technical', 'Technical approach', 'Provide a technical approach for the customer portal.', 'React interface and API service, customer authentication and automated tests.', 'Fictional technical approach', 'Maya'],
  ['delivery', 'Delivery plan', 'Provide a delivery plan for a twelve week implementation.', 'Twelve-week implementation covering discovery, development, verification and handover. Scope remains subject to agreement.', 'Fictional delivery plan', 'Leon'],
  ['studies', 'Two relevant case studies', 'Include two relevant case studies.', 'Example Retail account portal and Example Services support dashboard. Both are fictional Atlas Studio case studies.', 'Fictional case-study pair', 'Maya'],
  ['security', 'Security questionnaire', 'Complete the security questionnaire.', 'Responses cover access controls, backups and incident handling. Atlas Studio does not hold ISO 27001 certification in this fictional scenario.', 'Fictional security response', 'Ari'],
  ['commercial', 'Commercial proposal', 'Provide a commercial proposal.', 'Milestone payments against an agreed scope. No binding price is supplied in this fictional example.', 'Fictional commercial response', 'Leon'],
];
let state;
let view = 'review';
let toast;
const $ = selector => document.querySelector(selector);
const escape = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[char]));
function reset() {
  state = {revision:1, approved:null, amended:false, deadlineReviewed:false, attachment:false,
    requirements:definitions.map(([id,title,quote,answer,evidence,owner]) => ({id,title,quote,answer,evidence,owner,reviewed:false,changed:false,source:'Original RFP'})),
    history:[{text:'Loaded fictional Northstar RFP and five prewritten evidence records.',revision:1}]};
  view = 'review';
  render();
}
function record(text) {
  state.revision++;
  state.history.push({text,revision:state.revision});
}
function blockers() {
  return state.requirements.filter(r => !r.reviewed).length + Number(!state.deadlineReviewed) + Number(state.amended && !state.attachment);
}
function approved() { return state.approved === state.revision && blockers() === 0; }
function notify(text) {
  $('#announcement').textContent=text;
  clearTimeout(toast);
  toast=setTimeout(() => { $('#announcement').textContent=''; },5000);
}
function render() {
  const missing=blockers();
  const current=approved();
  $('#metrics').innerHTML = `<div class="metric"><span>REQUIREMENTS</span><b>${state.requirements.length}</b></div><div class="metric"><span>REVIEW BLOCKERS</span><b>${missing}</b></div><div class="metric"><span>PACKAGE APPROVAL</span><b class="words">${current?'Approved':state.approved!==null?'Reopened':'Awaiting review'}</b></div><div class="metric"><span>SOURCED DEADLINE · UTC</span><b class="words">Oct ${state.amended?'29':'30'}, 17:00</b></div>`;
  $('#amend').disabled=state.amended;
  $('#amend').textContent=state.amended?'Amendment added':'+ Add client amendment';
  document.querySelectorAll('[data-view]').forEach(button => {
    if (button.dataset.view===view) button.setAttribute('aria-current','page');
    else button.removeAttribute('aria-current');
  });
  $('#approval').innerHTML = `<h3>${current?'Revision '+state.revision+' approved':missing+' blockers to resolve'}</h3><p>${current?'This fictional package is ready for a demo report. Nothing has been sent to a client.':'Review the sourced answers and deadline before approving this exact revision.'}</p><button data-action="approve" ${missing||current?'disabled':''}>${current?'Package approved':'Approve demo package'}</button><button data-action="download" class="secondary" ${!current?'disabled':''}>Download demo report</button><small>This exports a JSON walkthrough report, not a client proposal or submission.</small>`;
  const renderers={review:renderReview,map:renderMap,sources:renderSources,history:renderHistory};
  $('#content').innerHTML=renderers[view]();
}
function renderReview() {
  return `<div class="section-title"><h3>Review the promises before export</h3><span class="tag">Revision ${state.revision}</span></div>${approved()?'<div class="notice success">'+(state.amended?'Amended demo package approved. You can download the report or inspect the audit trail.':'Package approved. Add the client amendment to see approval reopen.')+'</div>':state.amended?'<div class="notice">Client amendment added. Delivery needs a revised answer, the separate workbook is missing, certification needs an accurate response, and the deadline moved one day earlier. All suggested fixes below are fictional fixtures.</div>':'<div class="notice">Open each suggested answer, compare it with the source and prewritten evidence, then mark it reviewed. This demo does not assess real proposal quality.</div>'}${state.requirements.map(r => `<article class="card"><span class="tag ${r.reviewed?'good':'warn'}">${r.reviewed?'Reviewed':r.changed?'Amendment · needs review':'Needs review'}</span><h4>${escape(r.title)}</h4><button class="source-link" data-action="sources">${escape(r.source)} · view original text ↗</button><blockquote>${escape(r.quote)}</blockquote>${r.changed&&r.id==='delivery'?'<p><strong>Earlier wording:</strong> twelve-week implementation. New wording specifies a four-week discovery phase; the rest of the schedule still needs an agreed interpretation.</p>':''}<details ${r.reviewed?'':'open'}><summary>Suggested answer & evidence</summary><div class="answer"><b>${escape(r.evidence)} · prewritten fixture</b><p>${escape(r.answer)}</p><p>Review owner: ${escape(r.owner)}</p></div></details><div class="card-actions"><button class="secondary" data-action="review" data-id="${r.id}" ${r.reviewed?'disabled':''}>${r.reviewed?'Answer reviewed':r.changed?'Use & review fictional response':'Mark answer reviewed'}</button><span>${r.changed&&!r.reviewed?'Review the prewritten example above before accepting it.':'Human review controls this status.'}</span></div>${r.id==='workbook'?`<div class="card-actions"><button class="secondary" data-action="attach" ${state.attachment?'disabled':''}>${state.attachment?'Demo workbook attached':'Attach fictional workbook'}</button><span>Simulated attachment only; no upload.</span></div>`:''}</article>`).join('')}<article class="card"><span class="tag ${state.deadlineReviewed?'good':'warn'}">${state.deadlineReviewed?'Confirmed':'Needs review'}</span><h4>Submission deadline</h4><blockquote>${state.amended?'The revised submission deadline is October 29, 2026 at 17:00 UTC.':'Submissions close October 30, 2026 at 17:00 UTC.'}</blockquote><p>Fixed date in the fictional brief, not a live hackathon deadline.</p><button class="secondary" data-action="deadline" ${state.deadlineReviewed?'disabled':''}>${state.deadlineReviewed?'Deadline confirmed':'Confirm sourced deadline'}</button></article>`;
}
function renderMap() {
  return `<div class="section-title"><h3>Trace each obligation</h3><span class="tag">Source → evidence → review</span></div><p class="notice">Links in this demo are prewritten. The full app derives its map from stored source, requirement, evidence and answer identifiers; it does not independently verify causality.</p>${state.requirements.map(r=>`<article class="map-row"><h4>${escape(r.title)} ${r.changed?'<span class="tag warn">Changed / added</span>':''}</h4><div class="nodes"><div class="node"><strong>01 / CLIENT SOURCE</strong>${escape(r.source)}<br>“${escape(r.quote)}”</div><div class="node"><strong>02 / COMPANY EVIDENCE</strong>${escape(r.evidence)}<br>${escape(r.answer)}</div><div class="node"><strong>03 / OWNER & PACKAGE</strong>${escape(r.owner)}<br>${r.reviewed?'Answer reviewed':'Answer review needed'}${r.id==='workbook'?'<br>'+(state.attachment?'Demo attachment present':'Separate attachment missing'):''}<br>Global approval: ${approved()?'current':'pending'}</div></div><p>${r.changed?'This obligation was changed or added by the fictional amendment. Prior package approval cannot satisfy this new review.':'Original RFP obligation. Its row status does not approve the entire package.'}</p><button class="source-link" data-action="sources">Inspect sources</button></article>`).join('')}`;
}
function renderSources() {
  return `<div class="section-title"><h3>Sources & approved example evidence</h3><span class="tag">All fictional</span></div><h4>Original Northstar RFP</h4><pre>${escape(rfp)}</pre>${state.amended?`<h4>Client amendment</h4><pre>${escape(amendment)}</pre>`:'<p class="notice">Add the client amendment to compare the original and revised obligations.</p>'}<h4>Company evidence / prewritten fixtures</h4>${state.requirements.map(r=>`<article class="card"><h4>${escape(r.evidence)}</h4><p>${escape(r.answer)}</p><span class="tag">Fictional · not a company credential</span></article>`).join('')}`;
}
function renderHistory() {
  return `<div class="section-title"><h3>Decisions, kept in order</h3><span class="tag">This browser tab only</span></div><p class="notice">This temporary walkthrough log resets on refresh. The full local app persists its audit history in SQLite.</p>${state.history.slice().reverse().map(e=>`<div class="event"><small>REVISION ${e.revision} / DEMO EVENT</small>${escape(e.text)}</div>`).join('')}`;
}
function amend() {
  if(state.amended)return;
  state.amended=true;
  state.deadlineReviewed=false;
  const delivery=state.requirements.find(r=>r.id==='delivery');
  Object.assign(delivery,{title:'Revised delivery plan',quote:'Provide a revised delivery plan with a four week discovery phase.',reviewed:false,changed:true,source:'Client amendment',evidence:'Fictional revised plan — clarification still required',answer:'Propose a four-week discovery phase. Ask the fictional client to confirm how it fits within the original twelve-week overall schedule. This is a proposed response, not a confirmed schedule or client clarification.'});
  state.requirements.push({id:'workbook',title:'Separate security controls workbook',quote:'Attach a completed security controls workbook as a separate file.',answer:'A fictional example workbook covers access controls, backups and incident handling. The demo attachment is simulated and cannot be sent to a client.',evidence:'Fictional security workbook',owner:'Ari',reviewed:false,changed:true,source:'Client amendment'},
    {id:'certification',title:'Clarify ISO 27001 certification',quote:'Clarify whether your agency holds ISO 27001 certification; do not claim certification without a valid certificate.',answer:'Atlas Studio does not hold ISO 27001 certification in this fictional scenario. Say so clearly; do not attach or invent a certificate.',evidence:'Fictional security response — no certification',owner:'Ari',reviewed:false,changed:true,source:'Client amendment'});
  record('Client amendment added: delivery review reopened, two obligations added, deadline review reopened. Prior approval is no longer current.');
  view='map';render();notify('Amendment added. Inspect the changed obligations, then return to final review.');
}
function download() {
  if(!approved())return;
  const report={demo:true,live_ai:false,not_a_client_submission:true,opportunity:'Fictional Northstar Customer Portal',revision:state.revision,approved:true,amendment_added:state.amended,requirements:state.requirements,deadline_utc:state.amended?'2026-10-29T17:00:00Z':'2026-10-30T17:00:00Z',simulated_workbook:state.attachment,limitations:'Prewritten fixtures; no uploads or AI calls. Delivery interpretation is a proposed response requiring client clarification. This JSON is not a proposal or independently verified readiness assessment.',history:state.history};
  const url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}));
  const link=document.createElement('a');link.href=url;link.download='followthrough-fictional-demo-report.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  notify('Fictional demo report downloaded. Nothing was submitted externally.');
}
document.addEventListener('click',event=>{
  const button=event.target.closest('button');if(!button||button.disabled)return;
  if(button.id==='reset'){reset();notify('Demo reset. All changes were temporary.');return;}
  if(button.id==='amend'){amend();return;}
  if(button.dataset.view){view=button.dataset.view;render();return;}
  const actions={
    sources:()=>{view='sources';render();},
    review:()=>{const row=state.requirements.find(r=>r.id===button.dataset.id);if(!row||row.reviewed)return;row.reviewed=true;record('Reviewed fictional answer: '+row.title+'.');render();notify('Answer reviewed. Package approval remains a separate step.');},
    deadline:()=>{if(state.deadlineReviewed)return;state.deadlineReviewed=true;record('Confirmed the fictional sourced deadline.');render();},
    attach:()=>{if(state.attachment||!state.amended)return;state.attachment=true;record('Attached simulated fictional workbook. No file was uploaded.');render();notify('Simulated workbook attached. Review its answer separately.');},
    approve:()=>{if(blockers()||approved())return;state.approved=state.revision;state.history.push({text:'Explicitly approved fictional package revision '+state.revision+'. No external submission.',revision:state.revision});render();notify('Demo package approved. You can now add an amendment or download its report.');},
    download,
  };
  if(actions[button.dataset.action])actions[button.dataset.action]();
});
reset();
