(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]));
  const request = async (url, options = {}) => {
    const response = await fetch(url, options);
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || 'The request could not be completed.');
    return body;
  };
  const setBusy = (button, busy, label) => { if (!button) return; button.disabled = busy; button.setAttribute('aria-busy', String(busy)); if (label) button.dataset.readyLabel = button.dataset.readyLabel || button.textContent; button.textContent = busy ? label : (button.dataset.readyLabel || button.textContent); };

  const health = $('.topbar-meta');
  if (health) request('/health').then((body) => { health.innerHTML = `<span class="health-dot"></span><span>Backend connected · ${escapeHtml(body.service)}</span>`; }).catch(() => { health.innerHTML = '<span class="health-dot health-offline"></span><span>Backend unavailable</span>'; });
  $('#sidebar-toggle')?.addEventListener('click', () => { const shell = $('.app-shell'); const collapsed = shell.classList.toggle('sidebar-collapsed'); $('#sidebar-toggle').setAttribute('aria-label', collapsed ? 'Expand navigation' : 'Collapse navigation'); });

  $$('.scenario').forEach((button) => button.addEventListener('click', async () => {
    setBusy(button, true, 'Opening…');
    try { const result = await request(`/api/demo/${button.dataset.scenario}`); window.location.href = `/cases/${result.case_id}`; } catch (error) { showError($('#form-error') || $('#form-status'), error.message); setBusy(button, false); }
  }));

  const sourceInputs = $('#source-inputs');
  $('#add-source')?.addEventListener('click', () => {
    const wrapper = document.createElement('div'); wrapper.className = 'source-input'; wrapper.innerHTML = `<div class="form-grid"><label>Source name<input name="source_name" placeholder="e.g. Research notes" autocomplete="off" required></label><button class="icon-button remove-source" type="button" aria-label="Remove source">×</button></div><label>Source text<span class="label-hint">The material the answer should be grounded in</span><textarea name="source_content" rows="5" placeholder="Paste another source…" required></textarea></label>`;
    sourceInputs.appendChild(wrapper); updateSourceRemoveButtons(); wrapper.querySelector('input')?.focus();
  });
  function updateSourceRemoveButtons() { $$('.remove-source', sourceInputs).forEach((button) => { button.hidden = $$('.source-input', sourceInputs).length < 2; button.onclick = () => { button.closest('.source-input').remove(); updateSourceRemoveButtons(); }; }); }
  updateSourceRemoveButtons();

  $('#case-form')?.addEventListener('submit', async (event) => {
    event.preventDefault(); const form = event.currentTarget; const button = $('button[type="submit"]', form); const status = $('#form-status');
    try {
      setBusy(button, true, 'Creating…'); status.textContent = 'Creating case and extracting claims…';
      const data = new FormData(form); const names = data.getAll('source_name'); const contents = data.getAll('source_content');
      const body = { title: data.get('title'), answer: data.get('answer'), sources: names.map((name, index) => ({ name, content: contents[index] })) };
      const result = await request('/api/cases', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); window.location.href = `/cases/${result.id}`;
    } catch (error) { showError($('#form-error') || status, error.message); setBusy(button, false); }
  });

  $$('.case-row').forEach((row) => row.dataset.caseTitle && row.closest('.case-list'));
  $('#case-search')?.addEventListener('input', filterCases);
  $$('[data-case-filter]').forEach((button) => button.addEventListener('click', () => { $$('[data-case-filter]').forEach((item) => item.classList.remove('active')); button.classList.add('active'); filterCases(); }));
  function filterCases() { const query = ($('#case-search')?.value || '').toLowerCase(); const filter = $('[data-case-filter].active')?.dataset.caseFilter || 'all'; let visible = 0; $$('.case-row').forEach((row) => { const matchesText = row.dataset.caseTitle.includes(query); const matchesFilter = filter === 'all' || (filter === 'pending' ? row.dataset.decision === 'pending' : row.dataset.caseStatus === filter); row.hidden = !(matchesText && matchesFilter); if (!row.hidden) visible++; }); const empty = $('#empty-filtered'); if (empty) empty.hidden = visible > 0 || !query && filter === 'all'; }

  const app = $('#case-app');
  if (!app) return;
  let state = window.INITIAL_CASE || {};
  const caseId = app.dataset.caseId; const metrics = $('#metrics'); const claimsList = $('#claims-list'); const historyList = $('#history-list'); const sourceList = $('#source-list');
  const sourceName = (id) => state.sources?.find((source) => source.id === id)?.name || id;
  const latestResults = () => state.latest_run?.results?.results || [];
  const render = () => {
    const metricsData = state.latest_run?.metrics || { total_claims: 0, supported: 0, contradicted: 0, unsupported: 0, needs_review: 0, evidence_coverage: 0, source_count: state.sources?.length || 0 };
    metrics.innerHTML = [['Claims checked', metricsData.total_claims, 'Claims in latest run'], ['Supported', metricsData.supported, 'Direct source match'], ['Needs attention', (metricsData.unsupported || 0) + (metricsData.contradicted || 0) + (metricsData.needs_review || 0), 'Unsupported, conflict, or review'], ['Coverage', `${Math.round((metricsData.evidence_coverage || 0) * 100)}%`, 'Decisive evidence · not truth probability']].map(([label, value, note]) => `<div class="metric"><span>${label}</span><strong>${value}</strong><small>${note}</small></div>`).join('');
    const results = latestResults();
    claimsList.innerHTML = results.length ? results.map((result, index) => claimMarkup(result, index)).join('') : '<div class="empty inline-empty"><span class="loading-spinner" aria-hidden="true"></span><h3>Verification not run</h3><p>Run the deterministic engine to inspect claims and evidence.</p></div>';
    renderSources(); renderRepairs(results); renderHistory();
  };
  const claimMarkup = (result, index) => {
    const claim = state.claims?.[index]; const evidence = result.evidence || [];
    return `<article class="claim-card" data-status="${result.status}" data-index="${index}"><div class="claim-top"><span class="claim-number">${String(index + 1).padStart(2, '0')}</span><div class="claim-text">${escapeHtml(result.claim.text)}</div><span class="status status-${result.status}">${result.status.replace('_', ' ')}</span><button class="icon-button edit-claim" data-claim-id="${claim?.id || ''}" aria-label="Edit claim">✎</button></div><div class="claim-body"><p class="reason">${escapeHtml(result.rationale)} <strong>Rule-backed finding; not a probability of truth.</strong></p>${evidence.length ? evidence.map((item) => `<button class="evidence ${item.relation === 'contradicted' ? 'contradicted' : item.relation === 'needs_review' ? 'review' : ''}" data-source-id="${item.source_id}" data-start="${item.start}" data-end="${item.end}"><p>“${escapeHtml(item.text)}”</p><small>${escapeHtml(sourceName(item.source_id))} · characters ${item.start}–${item.end} · ${escapeHtml(item.reason)}</small></button>`).join('') : '<div class="no-evidence">No sufficiently direct source passage was found. This is an evidence gap, not proof that the claim is false.</div>'}</div></article>`;
  };
  function renderSources() { if (!sourceList) return; sourceList.innerHTML = (state.sources || []).map((source) => `<article class="source-card" data-source-id="${source.id}"><div class="source-card-header"><span class="source-file-icon" aria-hidden="true">⌁</span><div><h3>${escapeHtml(source.name)}</h3><small><code>${escapeHtml(source.id.slice(0, 10))}</code> · SHA-256 recorded</small></div></div><p class="source-content">${escapeHtml(source.content)}</p></article>`).join('') || '<div class="empty inline-empty"><h3>No source material</h3><p>Add source text to make findings inspectable.</p></div>'; }
  function renderRepairs(results) { const container = $('#repairs-list'); if (!container) return; const repairs = results.flatMap((result, index) => (result.repair_proposals || []).map((proposal) => ({ ...proposal, claimId: state.claims?.[index]?.id }))); container.innerHTML = repairs.length ? repairs.map((repair) => `<article class="repair-card"><div class="repair-card-top"><span class="status status-${repair.status}">${repair.status.replace('_', ' ')}</span><strong>${escapeHtml(repair.action)}</strong></div><p>${escapeHtml(repair.claim)}</p><small>${escapeHtml(repair.rationale)}</small><div class="repair-controls"><button class="button secondary apply-repair" data-claim-id="${repair.claimId || ''}" data-action="REMOVE">Remove claim</button><button class="button secondary apply-repair" data-claim-id="${repair.claimId || ''}" data-action="MANUAL_REVIEW">Keep for review</button></div></article>`).join('') : '<div class="empty inline-empty"><span class="empty-icon" aria-hidden="true">✧</span><h3>No repairs queued</h3><p>Run verification to surface evidence-grounded next steps.</p></div>'; }
  function renderHistory() { if (!historyList) return; historyList.innerHTML = state.history?.length ? `<div class="history-stream">${state.history.map((event) => `<div class="history-item"><span class="history-dot" aria-hidden="true"></span><div><strong>${escapeHtml(event.event_type.replaceAll('_', ' '))}</strong><small>${new Date(event.created_at).toLocaleString()} · ${escapeHtml(JSON.stringify(event.data))}</small></div></div>`).join('')}</div>` : '<p class="muted">No events yet.</p>'; }
  const refresh = async () => { state = await request(`/api/cases/${caseId}`); render(); };
  function showError(node, message) { if (node) { node.textContent = message; node.classList.add('visible'); } }
  $('#verify-button')?.addEventListener('click', async (event) => { const button = event.currentTarget; try { setBusy(button, true, 'Verifying…'); await request(`/api/cases/${caseId}/verify`, { method: 'POST' }); await refresh(); } catch (error) { showError($('#claims-error'), error.message); } finally { setBusy(button, false); } });
  $('#extract-button')?.addEventListener('click', async (event) => { try { setBusy(event.currentTarget, true, 'Extracting…'); await request(`/api/cases/${caseId}/claims/extract`, { method: 'POST' }); await refresh(); } catch (error) { showError($('#claims-error'), error.message); } finally { setBusy(event.currentTarget, false); } });
  $$('.filter').forEach((button) => button.addEventListener('click', () => { $$('.filter').forEach((item) => item.classList.remove('active')); button.classList.add('active'); $$('.claim-card').forEach((card) => { card.hidden = button.dataset.filter !== 'all' && card.dataset.filter !== card.dataset.status; }); }));
  claimsList.addEventListener('click', async (event) => { const evidence = event.target.closest('.evidence'); if (evidence) { const source = $(`.source-card[data-source-id="${CSS.escape(evidence.dataset.sourceId)}"]`); $$('.source-card').forEach((item) => item.classList.remove('selected')); source?.classList.add('selected'); source?.scrollIntoView({ behavior: 'smooth', block: 'center' }); return; } const edit = event.target.closest('.edit-claim'); if (edit) { const next = window.prompt('Edit claim text', state.claims.find((claim) => claim.id === edit.dataset.claimId)?.text || ''); if (next?.trim()) { try { await request(`/api/claims/${edit.dataset.claimId}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: next.trim() }) }); await refresh(); } catch (error) { showError($('#claims-error'), error.message); } } } });
  $('#repairs-list')?.addEventListener('click', async (event) => { const button = event.target.closest('.apply-repair'); if (!button) return; try { setBusy(button, true, 'Applying…'); await request(`/api/cases/${caseId}/repairs/apply`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify([{ claim_id: button.dataset.claimId, action: button.dataset.action }]) }); await refresh(); } catch (error) { showError($('#claims-error'), error.message); } finally { setBusy(button, false); } });
  $$('.source-card').forEach((card) => card.addEventListener('click', () => { $$('.source-card').forEach((item) => item.classList.remove('selected')); card.classList.add('selected'); }));
  $$('[data-decision]').forEach((button) => button.addEventListener('click', async () => { const status = $('#decision-status'); try { setBusy(button, true, 'Saving…'); await request(`/api/cases/${caseId}/decision`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ decision: button.dataset.decision, comment: $('#decision-comment').value }) }); await refresh(); status.textContent = 'Decision recorded in the audit trail.'; } catch (error) { showError(status, error.message); } finally { setBusy(button, false); } }));
  render();
})();
