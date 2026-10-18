'use strict';
const el = id => document.getElementById(id);
let items = [], selected = new Set(), session, busy = false, page = 1, shown = 0, draftsRequest = 0;
const node = (tag, text, cls) => {const n = document.createElement(tag); if(text !== undefined) n.textContent = text; if(cls) n.className = cls; return n;};
async function api(url, options) {
  const response = await fetch(url, options), data = await response.json();
  if (!response.ok) throw new Error(data.error || '요청에 실패했습니다.');
  return data;
}
function status(text) {el('draft-status').textContent = text;}
function setGenerating(value) {
  busy = value;
  el('draft-analysis').disabled = value;
  el('draft-loading').hidden = !value;
  el('draft-button-spinner').hidden = !value;
  el('generate-draft-label').textContent = value ? '초안 생성 중…' : '선택 항목으로 초안 생성';
  el('generate-draft').setAttribute('aria-busy', String(value));
  el('draft-items').setAttribute('aria-busy', String(value));
  renderItems();
}
function selection() {
  el('draft-selection').textContent = `선택 ${selected.size}/${session?.max_posts || 3}개 · 필터 밖의 선택도 유지됩니다.`;
  el('generate-draft').disabled = busy || !selected.size || selected.size > session.max_posts;
}
function renderItems() {
  el('draft-items').replaceChildren();
  items.forEach((item, i) => {
    if(el('draft-category').value && item.category !== el('draft-category').value) return;
    if(el('draft-source').value && item.source !== el('draft-source').value) return;
    const label = node('label', undefined, 'draft-choice'), check = node('input'); check.type = 'checkbox'; check.checked = selected.has(i); check.disabled = busy;
    check.addEventListener('change', () => {check.checked ? selected.add(i) : selected.delete(i); selection();});
    const info = node('span', `${item.title}\n${item.category} · ${item.source}\n`);
    const known = typeof item.has_draft === 'boolean';
    const badge = node('span', !known ? '초안 상태 확인 필요' : item.has_draft ? `초안 생성됨 · ${item.draft_count}개` : '초안 미생성',
      item.has_draft ? 'draft-badge ready' : 'draft-badge');
    if(item.draft_created_at) badge.title = `최근 생성: ${new Date(item.draft_created_at).toLocaleString()}`;
    info.append(badge);
    if(item.has_draft && typeof item.published_count === 'number') {
      info.append(node('span', item.published_count > 0 ? `✓ 발행 완료 · ${item.published_count}개` : 'Threads 미발행',
        item.published_count > 0 ? 'draft-badge published' : 'draft-badge not-published'));
    }
    label.append(check, info); el('draft-items').append(label);
  });
  if(!el('draft-items').children.length) el('draft-items').append(node('p', '해당 조건의 항목이 없습니다.'));
  selection();
}
async function loadItems() {
  const id = el('draft-analysis').value;
  items = id ? (await api('/api/draft-items?id=' + encodeURIComponent(id))).items : [];
  selected.clear();
  for(const [id, key, title] of [['draft-category','category','모든 카테고리'],['draft-source','source','모든 소스']]) {
    el(id).replaceChildren(new Option(title, ''));
    [...new Set(items.map(x => x[key]))].sort().forEach(value => el(id).add(new Option(value, value)));
  }
  renderItems();
}
async function refreshItemStatus() {
  const id = el('draft-analysis').value;
  if(!id || busy) return;
  const data = await api('/api/draft-items?id=' + encodeURIComponent(id));
  // Preserve selection by source + URL rather than relying on list positions.
  const keys = new Set([...selected].map(i => JSON.stringify([items[i].source, items[i].url])));
  items = data.items;
  selected = new Set(items.flatMap((item, i) => keys.has(JSON.stringify([item.source, item.url])) ? [i] : []));
  if(items.some(item => typeof item.has_draft !== 'boolean')) {
    status('실행 중인 뷰어가 초안 상태를 제공하지 않습니다. 뷰어 서버를 재시작하고 페이지를 새로고침해 주세요.');
  }
  renderItems();
}
async function loadDrafts(reset = true) {
  const request = ++draftsRequest;
  if(reset) {page = 1; shown = 0; el('saved-drafts').replaceChildren();}
  const params = new URLSearchParams({page, page_size:20, q:el('saved-search').value,
    status:el('saved-status').value, category:el('saved-category').value, source:el('saved-source').value});
  const data = await api('/api/drafts?' + params);
  if(request !== draftsRequest) return;
  for(const [id, values, title] of [['saved-category',data.categories,'모든 카테고리'],['saved-source',data.sources,'모든 소스']]) {
    const current = el(id).value;
    el(id).replaceChildren(new Option(title, ''));
    (values || []).forEach(value => el(id).add(new Option(value,value)));
    el(id).value = current;
  }
  el('saved-count').textContent = `조건에 맞는 초안 ${data.total}개`;
  for(const draft of data.rows) {
    const card = node('article', undefined, 'draft-card');
    card.append(node('h3', new Date(draft.created_at).toLocaleString()), node('p', `분석 ${draft.analysis_id || '미지정'} · 초안 ${draft.draft_id}`));
    const labels = session.status_labels || {};
    card.append(node('span', `Threads · ${labels[draft.publication_status] || '상태 확인 필요'}`,
      `publication-badge publication-${draft.publication_status || 'unknown'}`));
    for(const post of draft.posts) {card.append(node('pre', post.text)); if(post.evidence) card.append(node('p', `근거: ${post.evidence.title} · ${post.evidence.source}`));}
    for(const publication of draft.publications || []) {
      if(publication.error) card.append(node('p', '최근 발행 오류: ' + publication.error));
    }
    if(draft.publication_status === 'published') {
      const done = node('button', '✓ 발행됨', 'button publication-done');
      done.disabled = true;
      card.append(done);
      const ids = (draft.publications || []).filter(p => p.post_id).map(p => p.post_id);
      if(ids.length) card.append(node('p', `Threads 게시글 ID: ${ids.join(', ')}`));
    } else if(['draft', 'failed'].includes(draft.publication_status)) {
      const button = node('button', 'Threads에 발행', 'button');
      if(!session.publishing_enabled) {
        button.disabled = true;
        button.textContent = 'Threads 발행 비활성화';
        card.append(node('p', 'config.toml에서 Threads 채널을 활성화한 뒤 뷰어를 재시작하세요.'));
      }
      button.addEventListener('click', async () => {
        if(!window.confirm(`이 초안의 게시글 ${draft.posts.length}개를 Threads에 실제 발행할까요?`)) return;
        button.disabled = true; button.textContent = '발행 중…';
        try {
          await api('/api/drafts/publish', {method:'POST', headers:{'Content-Type':'application/json','X-Draft-Token':session.token},
            body:JSON.stringify({draft_id:draft.draft_id, confirmed:true})});
          status('Threads 발행 결과를 저장했습니다.');
        } catch(error) {status(error.message);} finally {await handle(Promise.all([loadDrafts(), refreshItemStatus()]));}
      });
      card.append(button);
    }
    for(const publication of draft.publications || []) {
      if(publication.status !== 'pending') continue;
      const recover = node('button', `항목 ${publication.post_index + 1} 발행 결과 확인`, 'button');
      recover.addEventListener('click', async () => {
        const result = window.prompt('Threads 계정에서 직접 확인하세요. 발행된 경우 게시글 숫자 ID를, 미발행을 확인했다면 미발행을 입력하세요.');
        if(result === null || !result.trim()) return;
        const postId = result.trim(), published = postId !== '미발행';
        if(published && !/^\d+$/.test(postId)) {status('게시글 숫자 ID를 확인하세요.'); return;}
        if(!window.confirm(published ? '계정에서 확인한 발행 결과를 저장할까요?' : '계정에 게시글이 없음을 확인했나요? 이후 재발행이 가능해집니다.')) return;
        recover.disabled = true;
        try {
          await api('/api/drafts/reconcile', {method:'POST', headers:{'Content-Type':'application/json','X-Draft-Token':session.token},
            body:JSON.stringify({draft_id:draft.draft_id, post_index:publication.post_index,
              status:published ? 'published' : 'failed', post_id:published ? postId : null, confirmed:true})});
          status('확인한 발행 결과를 저장했습니다.');
        } catch(error) {status(error.message);} finally {await handle(Promise.all([loadDrafts(), refreshItemStatus()]));}
      });
      card.append(recover);
    }
    el('saved-drafts').append(card);
  }
  shown += data.rows.length; el('more-drafts').hidden = shown >= data.total;
  if(!shown) el('saved-drafts').append(node('p', '조건에 맞는 초안이 없습니다.'));
}
function handle(task) {return task.catch(error => status(error.message));}
['saved-status','saved-category','saved-source'].forEach(id => el(id).addEventListener('change', () => handle(loadDrafts())));
let searchTimer;
el('saved-search').addEventListener('input', () => {clearTimeout(searchTimer); searchTimer = setTimeout(() => handle(loadDrafts()), 250);});
el('reset-saved-filters').addEventListener('click', () => {
  clearTimeout(searchTimer);
  ['saved-search','saved-status','saved-category','saved-source'].forEach(id => {el(id).value = '';});
  handle(loadDrafts());
});
el('draft-analysis').addEventListener('change', () => handle(loadItems()));
['draft-category','draft-source'].forEach(id => el(id).addEventListener('change', renderItems));
el('reload-drafts').addEventListener('click', () => handle(Promise.all([loadDrafts(), refreshItemStatus()])));
window.addEventListener('focus', () => handle(refreshItemStatus()));
el('more-drafts').addEventListener('click', () => {page++; handle(loadDrafts(false));});
el('generate-draft').addEventListener('click', async () => {
  if(busy) return;
  const payload = {analysis_id: el('draft-analysis').value, selected: [...selected]};
  setGenerating(true); status('원문을 읽고 초안을 생성하고 있습니다. 완료될 때까지 기다려 주세요.');
  try {
    await api('/api/drafts', {method:'POST', headers:{'Content-Type':'application/json','X-Draft-Token':session.token}, body:JSON.stringify(payload)});
    const refreshed = await api('/api/draft-items?id=' + encodeURIComponent(payload.analysis_id));
    items = refreshed.items;
    await loadDrafts(); status('초안을 데이터베이스에 저장했습니다. 아래에서 내용을 확인하세요.');
  } catch(error) {status(error.message);} finally {setGenerating(false);}
});
handle((async () => {
  session = await api('/api/draft-session');
  const data = await api('/api/analysis');
  el('draft-analysis').add(new Option('분석을 선택하세요', ''));
  data.rows.forEach(row => el('draft-analysis').add(new Option(`${row.created_at} · ${row.analysis_id}`, row.analysis_id)));
  if(!data.rows.length) status('저장된 분석이 없습니다. 먼저 분석을 실행하세요.');
  await loadItems(); await loadDrafts();
})());
