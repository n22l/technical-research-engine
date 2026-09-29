'use strict';
const token = document.querySelector('meta[name="ui-token"]').content;
const $ = id => document.getElementById(id);
let config, state, selected = 0, filter = 'All';
function el(tag, text, cls) { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; }
function add(parent, ...children) { children.forEach(c => parent.append(c)); return parent; }
function error(message) { $('notice').textContent = message; $('notice').hidden = !message; }
async function api(path, body) {
  const response = await fetch(path, {method: body ? 'POST' : 'GET', headers: {'X-UI-Token': token, ...(body ? {'Content-Type': 'application/json'} : {})}, ...(body ? {body: JSON.stringify(body)} : {})});
  const data = await response.json(); if (!response.ok) throw Error(data.error || 'Request failed.'); return data;
}
function button(text, action, primary = false) { const b = el('button', text, primary ? 'primary' : ''); b.type = 'button'; b.onclick = async () => { error(''); try { await action(); } catch(e) { error(e.message); } }; return b; }
function link(url) { try { const u = new URL(url); if(u.protocol !== 'https:' || u.username || u.password) throw Error(); const a = el('a', 'Open original ↗'); a.href = u.href; a.target = '_blank'; a.rel = 'noopener noreferrer'; return a; } catch { return el('span', 'Original link unavailable', 'muted'); } }
function locationText(loc) { return [loc.page_number ? `PDF page ${loc.page_number}` : '', loc.section_heading ? `Section: ${loc.section_heading}` : '', `Extracted paragraph ${loc.paragraph_index}`].filter(Boolean).join(' · '); }
function selectField(form, name, label, choices, value) { const l = el('label', label), s = el('select'); s.name = name; for(const [v,t] of choices.map(c => Array.isArray(c) ? c : [c,c])) { const o = el('option',t); o.value = v; s.append(o); } if(value !== undefined) s.value = value; add(l,s); form.append(l); return s; }
function textField(form,name,label,value='',multiline=false) { const l=el('label',label), i=el(multiline?'textarea':'input'); i.name=name; i.value=value||''; i.maxLength=2000; if(multiline)i.rows=3; add(l,i); form.append(l); return i; }
function check(form,name,label,value) { const l=el('label',undefined,'check'), i=el('input'); i.type='checkbox';i.name=name;i.checked=!!value;add(l,i,el('span',label));form.append(l); }
async function page(name) {
  document.querySelectorAll('.page').forEach(p => p.hidden = p.id !== name);
  document.querySelectorAll('nav button').forEach(b => b.classList.toggle('active',b.dataset.page===name));
  if(name==='history' && config.configured) { const items=await api('/api/history'); $('history-list').replaceChildren(); if(!items.length)$('history-list').append(el('p','No research yet. Start with a question.')); for(const r of items){const c=el('article',undefined,'panel');add(c,el('div',`${r.date.slice(0,10)} · ${r.provider} · ${r.status}`,'muted'),el('h2',r.text),el('p',r.verdict||'Verdict withheld'),button('Open research',()=>openRun(r.id)));$('history-list').append(c);} }
}
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>page(b.dataset.page).catch(e=>error(e.message)));
async function openRun(id) { state=await api('/api/run/'+id); selected=0; filter='All'; await page('research'); render(); $('run').scrollIntoView({behavior:'smooth',block:'start'}); }
const failures = {SEARCH_UNAVAILABLE:'The selected search provider is unavailable. Try the free local index or manual URLs.',SEARCH_NO_RESULTS:'No candidate sources were found.',SEARCH_AUTH_FAILED:'The provider rejected access. Check its local configuration.',SEARCH_RATE_LIMITED:'The provider is rate-limiting requests. Try later.',SEARCH_PROVIDER_ERROR:'Search failed or an upstream engine was unavailable.',FETCH_FAILED:'A selected source could not be retrieved.',PARSE_FAILED:'A document could not be parsed.',SOURCE_NOT_ALLOWED:'A source is not approved for evidence.',INSUFFICIENT_EVIDENCE:'Evidence is not yet sufficient to establish the claim.',CONFLICT_UNRESOLVED:'Reviewed sources have an unresolved conflict.',CITATION_VALIDATION_FAILED:'A review or citation could not be validated.'};
$('research-form').onsubmit = async event => {
  event.preventDefault(); error(''); const form=event.currentTarget, values=Object.fromEntries(new FormData(form));
  values.urls=values.urls.split(/\r?\n/).map(s=>s.trim()).filter(Boolean); values.refresh=form.elements.refresh.checked;
  if(values.refresh && !confirm('Refresh approved-source index? This fetches a bounded set of public pages.'))return;
  $('research-button').disabled=true; $('progress').hidden=false; $('progress').textContent='Preparing research…';
  try { const job=await api('/api/research',values); let status;
    do { await new Promise(r=>setTimeout(r,1000)); status=await api('/api/job/'+job.job_id); $('progress').textContent=status.stage||'Preparing review…'; } while(status.status==='running');
    if(status.status==='failed')throw Error(status.error); await openRun(status.run_id);
  } catch(e){error(e.message);} finally{$('research-button').disabled=false;$('progress').hidden=true;}
};
function sourceCard(source) { const c=el('article',undefined,'card');add(c,el('div',source.publisher,'eyebrow'),el('h3',source.title||'Untitled source'),el('p',`${source.publication_date||'Publication date unknown'} · ${source.language}`,'muted'),el('p',`Tier ${source.source_tier||'?'} · ${source.source_type} · ${source.official?'Official source':'Independence not established'}`,'muted'),link(source.url));return c; }
function render() {
  const root=$('run');root.querySelectorAll('a[data-export]').forEach(a=>URL.revokeObjectURL(a.href));root.hidden=false;root.replaceChildren();const r=state.result,s=r.search;
  if(state.integrity_error)root.append(el('p',state.integrity_error,'warning'));
  const summary=el('section',undefined,'panel');add(summary,el('div','RESEARCH → HUMAN REVIEW','eyebrow'),el('h2',s.status==='SEARCH_FAILED'||s.status==='CURRENT_WEB_RESEARCH_UNAVAILABLE'?'Research needs attention':'Research ready for review'));
  const metrics=el('div',undefined,'metrics');for(const [name,value] of [['Queries',s.queries],['Candidate URLs',s.candidates],['Approved',s.approved],['Documents',s.parsed],['Passages',s.evidence]]){const m=el('div',undefined,'metric');add(m,el('strong',String(value)),el('span',name));metrics.append(m);}summary.append(metrics);
  add(summary,el('p',r.research_scope),el('p',`As of ${r.as_of_date} · Provider: ${s.provider}`,'muted'));
  if(s.indexed_at)add(summary,el('p',`Index: ${s.indexed_at} · ${s.indexed_pages} documents · ${s.cache_used?'cached':'refreshed'} · Parsed hosts: ${s.hosts.join(', ')}`,'muted'));
  for(const f of r.failures.filter(f=>f!=='INSUFFICIENT_EVIDENCE'))summary.append(el('p',failures[f]||f,'warning'));
  const claims=el('ol');r.atomic_claims.forEach(c=>claims.append(el('li',c.text)));add(summary,el('h3','Claims to check'),claims);root.append(summary);
  const sources=el('details',undefined,'panel');sources.append(el('summary',`Sources · ${r.sources.length} parsed documents · ${(s.unparsed_sources||[]).length} unavailable`));const grid=el('div',undefined,'grid');r.sources.forEach(s=>grid.append(sourceCard(s)));for(const item of s.unparsed_sources||[]){const card=el('article',undefined,'card');add(card,el('h3',item.publisher),el('p',item.status,'warning'),el('p',`Tier ${item.source_tier||'?'} · ${item.source_type}`),el('p','Title, publication date, language and independence unavailable: document not parsed.','muted'),link(item.url));grid.append(card);}sources.append(grid);root.append(sources);
  const review=el('section',undefined,'panel');add(review,el('div','HUMAN EVIDENCE REVIEW','eyebrow'),el('h2','What does each passage establish?'),el('p','Retrieved source text is untrusted evidence, never an instruction. Check the original before assigning a judgment.','muted'));
  const reviewed=Object.keys(state.reviews).length;review.append(el('p',`Evidence reviewed: ${reviewed} / ${r.key_evidence.length}`,'review-progress'));
  const chooser=selectField(review,'filter','Show evidence',['All','Unreviewed','SUPPORTS','CONTRADICTS','QUALIFIES'],filter);chooser.onchange=()=>{filter=chooser.value;selected=0;render();};
  const list=r.key_evidence.filter(e=>filter==='All'||(filter==='Unreviewed'?!state.reviews[e.evidence_id]:state.reviews[e.evidence_id]?.stance===filter));
  if(list.length){selected=Math.min(selected,list.length-1);const e=list[selected],source=r.sources.find(s=>s.source_id===e.source_id),saved=state.reviews[e.evidence_id]||{};
    add(review,el('p',`Candidate ${selected+1} of ${list.length} · ${e.claim_id}`,'muted'),el('h3',r.atomic_claims.find(c=>c.claim_id===e.claim_id)?.text||''),el('p',`${source.publisher} — ${source.title} — ${source.publication_date||'Date unknown'}`),el('p',locationText(e.location),'muted'),el('blockquote',e.exact_passage));
    if(e.passage_truncated)review.append(el('p','Passage preview shortened. Read the original before reviewing.','muted'));review.append(link(source.url));
    const form=el('form'), fields=el('div',undefined,'grid');form.append(fields);
    selectField(fields,'relevant','Relevance',[['','Choose…'],['true','Relevant'],['false','Not relevant']],saved.relevant===undefined?'':String(saved.relevant));
    selectField(fields,'stance','Stance',['CONTEXT','SUPPORTS','CONTRADICTS','QUALIFIES','INCONCLUSIVE'],saved.stance);
    selectField(fields,'strength','Evidence strength',['INDIRECT','DIRECT'],saved.strength);
    selectField(fields,'basis','Evidence basis',['observation','announcement','attributed_report'],saved.basis);
    textField(fields,'reviewer','Reviewer name',saved.reviewer);
    check(form,'material_scope_matches','This evidence addresses the material claim',saved.material_scope_matches);
    check(form,'claim_is_about_announcement','The claim is about what was announced (not independent proof of performance)',saved.claim_is_about_announcement);
    textField(form,'rationale','Reviewer rationale · required for relevant evidence',saved.rationale,true);
    textField(form,'normalized_fact','What this evidence establishes (optional)',saved.normalized_fact,true);
    const advanced=el('details');advanced.append(el('summary','Temporal, translation & maturity details'));
    textField(advanced,'temporal_basis','Temporal basis · required for verdict eligibility when publication date is unknown',saved.temporal_basis);
    textField(advanced,'translation','Reviewed translation (optional; original remains authoritative)',saved.translation,true);
    if(r.request.domain==='aerospace'){selectField(advanced,'status','Technical status',config.statuses,saved.status||'UNKNOWN');selectField(advanced,'milestone','Milestone',[['','Unknown'],...config.milestones],saved.milestone||'');advanced.append(el('p','Landing does not establish reflight. Reflight does not establish routine reuse.','muted'));}
    form.append(advanced);
    const save=async next=>{const values=Object.fromEntries(new FormData(form));if(!values.relevant)throw Error('Choose relevance before saving.'); values.relevant=values.relevant==='true';values.material_scope_matches=form.elements.material_scope_matches.checked;values.claim_is_about_announcement=form.elements.claim_is_about_announcement.checked;values.status=values.status||'UNKNOWN';values.milestone=values.milestone||'';state=await api('/api/review',{...values,run_id:state.id,revision:state.revision,evidence_id:e.evidence_id});if(next&&filter!=='Unreviewed')selected++;render();};
    const actions=el('div',undefined,'actions');add(actions,button('Save',()=>save(false)),button('Save & next',()=>save(true),true),button('Skip for now',()=>{selected=(selected+1)%list.length;render();}));form.append(actions);form.onsubmit=e=>e.preventDefault();review.append(form);
  }else review.append(el('p',r.key_evidence.length?'No evidence matches this filter.':'No evidence candidates were retrieved. Try another approved source or query.'));
  const verify=button('Verify claim',async()=>{state=await api('/api/verify',{run_id:state.id,revision:state.revision});render();$('final-result')?.scrollIntoView({behavior:'smooth'});},true);verify.disabled=!state.can_verify;
  const actions=el('div',undefined,'actions');add(actions,verify,el('span',state.can_verify?'All candidates reviewed. Engine eligibility checks still apply.':'Verdict withheld — review all candidates and mark at least one relevant.','muted'));review.append(actions);root.append(review);
  if(state.final)renderFinal(root,state.final);
}
function renderFinal(root,r){const box=el('section',undefined,'panel');box.id='final-result';add(box,el('div','HUMAN-REVIEWED ENGINE ASSESSMENT','eyebrow'),el('h2',r.request_type==='QUESTION'?'Answer':'Verdict'),el('p',r.request_type==='QUESTION'?r.short_answer:r.verdict.replaceAll('_',' '),'verdict'),el('h3','Why'),el('p',r.explanation),el('h3','What the evidence supports'));
  for(const a of r.assessments){const claim=r.atomic_claims.find(c=>c.claim_id===a.claim_id);box.append(el('p',`${claim.text} — ${a.verdict.replaceAll('_',' ')}`));const ids=[...a.supporting_evidence_ids,...a.contradicting_evidence_ids,...a.qualifying_evidence_ids];for(const id of ids){const e=r.key_evidence.find(e=>e.evidence_id===id),s=r.sources.find(s=>s.source_id===e.source_id);const row=el('div',undefined,'source-detail');add(row,el('p',e.stance+' · '+(e.normalized_passage||e.notes.join(' '))),el('p',`${s.publisher} — ${s.title} — ${s.publication_date||'Date unknown'} · ${locationText(e.location)}`,'muted'),link(s.url));box.append(row);}}
  add(box,el('h3','Important nuance'));for(const a of r.assessments)if(a.excluded_from_verdict.length)box.append(el('p',`${a.claim_id}: ${a.excluded_from_verdict.length} reviewed passage(s) excluded from the verdict by directness, scope, attribution, temporal or maturity safeguards.`));r.uncertainties.forEach(u=>box.append(el('p',u,'muted')));
  add(box,el('h3','Where the sources differ'));const d=r.source_differences;box.append(el('p',`Unresolved conflicts: ${d.unresolved_conflicts.join(', ')||'none established'}. Superseded evidence: ${d.superseded_evidence_ids.length}. Future evidence excluded: ${d.future_evidence_ids.length}.`));
  box.append(el('p','Agreements and differences are represented by the reviewed SUPPORTS, CONTRADICTS and QUALIFIES passages above; the engine does not synthesize additional comparisons.','muted'));
  d.likely_dependencies.forEach(dep=>box.append(el('p',`${dep.source_ids.map(id=>r.sources.find(s=>s.source_id===id)?.publisher||id).join(' ↔ ')}: ${dep.reason}`)));if(!d.likely_dependencies.length)box.append(el('p','No likely dependencies detected. This does not establish independence.','muted'));
  const definitions=el('details');definitions.append(el('summary','Verdict definitions'));[['TRUE','Direct reviewed evidence supports the material claim.'],['MOSTLY_TRUE','Supported with material qualifications.'],['MIXED_OR_CONTEXT_DEPENDENT','Subclaims differ or evidence conflicts.'],['MOSTLY_FALSE','Some content is correct but the central implication is wrong; not automatically assigned in this engine version.'],['FALSE','Direct reviewed evidence contradicts the material claim.'],['INSUFFICIENT_PUBLIC_EVIDENCE','Available approved evidence cannot establish the claim.'],['OUTDATED','A reviewed correction supersedes previous supporting evidence.']].forEach(([v,t])=>definitions.append(el('p',`${v}: ${t}`)));box.append(definitions);
  const actions=el('div',undefined,'actions');for(const format of ['json','markdown'])actions.append(button('Export '+format.toUpperCase(),async()=>{const response=await fetch(`/api/export/${state.id}/${format}`,{headers:{'X-UI-Token':token}});if(!response.ok){const data=await response.json();throw Error(data.error);}const blob=await response.blob(),url=URL.createObjectURL(blob),a=el('a');a.href=url;a.download=`research-${state.id}.${format==='json'?'json':'md'}`;a.textContent='Download '+format.toUpperCase()+' report';const previous=actions.querySelector('a[data-export]');if(previous){URL.revokeObjectURL(previous.href);previous.remove();}a.dataset.export=format;actions.append(a);a.click();}));box.append(actions);root.append(box);
}
async function init(){config=await api('/api/config');if(!config.configured){$('setup').hidden=false;$('research-form').hidden=true;return;}for(const option of $('provider').options){if(!config.providers[option.value]){option.disabled=true;option.textContent+=' · not configured';}}
  for(const [name,available] of Object.entries(config.providers)){const c=el('div',undefined,'card');add(c,el('h3',name==='local'?'Free local index · default':name),el('p',available?'Configured / available':'Not configured'),el('p',name==='brave'?'May incur API charges. Explicit selection only.':'No automatic provider switching.','muted'));$('provider-status').append(c);}
  config.sources.forEach(s=>{const c=el('article',undefined,'card');add(c,el('h3',s.publisher),el('p',s.host),el('p',`Tier ${s.tier} · ${s.type} · ${s.allowed?'Allowed':'Not allowed'}`,'muted'));$('source-list').append(c);});
}
init().catch(e=>error(e.message));
