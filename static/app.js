const json = (response) => response.json().then((body) => { if (!response.ok) throw new Error(body.detail || 'Request failed'); return body; });

document.querySelectorAll('[data-scenario]').forEach((button) => button.addEventListener('click', async () => {
  button.disabled = true;
  try { const result = await json(await fetch(`/api/demo/${button.dataset.scenario}`, {method:'GET'})); window.location.href = `/cases/${result.case_id}`; }
  catch (error) { alert(error.message); button.disabled = false; }
}));

const form = document.querySelector('#case-form');
if (form) form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const status = document.querySelector('#form-status'); status.textContent = 'Creating case…';
  const data = new FormData(form);
  try { const body = {title:data.get('title'), answer:data.get('answer'), sources:[{name:data.get('source_name'),content:data.get('source_content')}]}; const result = await json(await fetch('/api/cases',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})); window.location.href=`/cases/${result.id}`; }
  catch (error) { status.textContent = error.message; }
});

const app = document.querySelector('#case-app');
if (app) {
  let state = window.INITIAL_CASE;
  const metrics = document.querySelector('#metrics'), claimsList = document.querySelector('#claims-list'), historyList = document.querySelector('#history-list');
  const render = () => {
    const metricsData = state.latest_run?.metrics || {total_claims:0,supported:0,contradicted:0,unsupported:0,needs_review:0,evidence_coverage:0};
    metrics.innerHTML = [['Claims',metricsData.total_claims,'Total extracted'],['Supported',metricsData.supported,'Direct evidence'],['Contradicted',metricsData.contradicted,'Explicit conflict'],['Coverage',`${Math.round(metricsData.evidence_coverage*100)}%`,'Decisive evidence']].map(item=>`<div class="metric"><span>${item[0]}</span><strong>${item[1]}</strong><small>${item[2]}</small></div>`).join('');
    const results = state.latest_run?.results?.results || [];
    claimsList.innerHTML = results.length ? results.map((result,index)=>`<article class="claim-card" data-status="${result.status}"><div class="claim-top"><span class="claim-number">${String(index+1).padStart(2,'0')}</span><div class="claim-text">${escapeHtml(result.claim.text)}</div><span class="status status-${result.status}">${result.status.replace('_',' ')}</span></div><div class="claim-body"><p class="reason">${escapeHtml(result.rationale)} <strong>Rule-backed finding; not a probability of truth.</strong></p>${result.evidence.length ? result.evidence.map(ev=>`<div class="evidence ${ev.relation==='contradicted'?'contradicted':ev.relation==='needs_review'?'review':''}"><p>“${escapeHtml(ev.text)}”</p><small>${escapeHtml(ev.source_id)} · characters ${ev.start}–${ev.end} · ${ev.reason}</small></div>`).join('') : '<div class="no-evidence">No sufficiently direct source passage was found. This is an evidence gap, not proof that the claim is false.</div>'}</div></article>`).join('') : '<div class="empty"><h3>Verification not run</h3><p>Run the deterministic engine to inspect claims and evidence.</p></div>';
    historyList.innerHTML = state.history.length ? state.history.map(event=>`<div class="history-item"><span class="history-dot"></span><div><strong>${event.event_type.replaceAll('_',' ')}</strong><small>${new Date(event.created_at).toLocaleString()} · ${escapeHtml(JSON.stringify(event.data))}</small></div></div>`).join('') : '<p class="muted">No events yet.</p>';
  };
  const escapeHtml = (text) => String(text).replace(/[&<>'"]/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
  const refresh = async () => { state = await json(await fetch(`/api/cases/${app.dataset.caseId}`)); render(); };
  document.querySelector('#verify-button').addEventListener('click', async (event) => { event.target.disabled=true; event.target.textContent='Verifying…'; try { await json(await fetch(`/api/cases/${app.dataset.caseId}/verify`,{method:'POST'})); await refresh(); } catch(error){ alert(error.message); } event.target.disabled=false; event.target.textContent='Run verification'; });
  document.querySelectorAll('[data-decision]').forEach((button) => button.addEventListener('click', async () => { const status=document.querySelector('#decision-status'); status.textContent='Recording decision…'; try { await json(await fetch(`/api/cases/${app.dataset.caseId}/decision`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({decision:button.dataset.decision,comment:document.querySelector('#decision-comment').value})})); await refresh(); status.textContent='Decision recorded.'; } catch(error){status.textContent=error.message;} }));
  document.querySelectorAll('[data-filter]').forEach((button) => button.addEventListener('click', () => { document.querySelectorAll('[data-filter]').forEach(item=>item.classList.remove('active')); button.classList.add('active'); document.querySelectorAll('.claim-card').forEach(card=>card.classList.toggle('hidden',button.dataset.filter!=='all'&&card.dataset.status!==button.dataset.filter)); }));
  render();
}
