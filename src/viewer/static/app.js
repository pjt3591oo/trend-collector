const $ = (id) => document.getElementById(id);
const state = {view:'browse', page:1, total:0, size:30, source:'', run:'', query:'', serial:0, detailSerial:0};
const names = {geeknews:'GeekNews',producthunt:'Product Hunt',hackernews:'Hacker News',reddit:'Reddit',github:'GitHub Trending',google_trends:'Google Trends',indiehackers:'Indie Hackers',disquiet:'Disquiet',huggingface:'Hugging Face',bleepingcomputer:'BleepingComputer',cisa_kev:'CISA KEV',github_advisories:'GitHub Advisories',kisa:'KISA'};
const label = (s) => names[s] || s;
const date = (v) => v ? new Date(v).toLocaleString('ko-KR',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}) : '시각 미제공';
function el(tag, cls, value){const node=document.createElement(tag);if(cls)node.className=cls;if(value!==undefined)node.textContent=value;return node;}
async function api(path, params={}){const response=await fetch(path+'?'+new URLSearchParams(params));const data=await response.json();if(!response.ok)throw new Error(data.error || '데이터를 읽지 못했습니다.');return data;}
function error(message){$('error').textContent=message;$('error').hidden=!message;}
function empty(parent,title,description){const box=el('div','empty');box.append(el('strong','',title),el('p','',description));parent.replaceChildren(box);}
function option(value,title){const node=el('option','',title);node.value=value;return node;}
function metrics(values){return Object.entries(values || {}).filter(([,v])=>v!==null&&typeof v!=='object').slice(0,3).map(([k,v])=>`${k}: ${v}`).join(' · ');}
function pagination(){const pages=Math.max(1,Math.ceil(state.total/state.size));$('page-info').textContent=`총 ${state.total.toLocaleString()}건 · ${state.page} / ${pages} 페이지`;$('prev').disabled=state.page<=1;$('next').disabled=state.page>=pages;}
async function refresh(){try{error('');const [summary,runs]=await Promise.all([api('/api/summary'),api('/api/runs',{page_size:100})]);$('stat-items').textContent=summary.items.toLocaleString();$('stat-runs').textContent=summary.runs.toLocaleString();$('stat-observations').textContent=summary.observations.toLocaleString();$('stat-sources').textContent=summary.sources.length;$('source-count').textContent=summary.sources.length;$('last-run').textContent=summary.latest_run?date(summary.latest_run.started_at):'최근 실행 없음';$('source-list').replaceChildren();$('source-filter').replaceChildren(option('','모든 소스'));for(const source of summary.sources){$('source-filter').append(option(source.source,label(source.source)));const button=el('button','source-button');button.dataset.source=source.source;button.append(el('span','dot'),el('span','',label(source.source)),el('span','count',source.count));button.onclick=()=>{state.source=source.source;$('source-filter').value=state.source;setView('browse');};$('source-list').append(button);}if(!summary.sources.some(s=>s.source===state.source))state.source='';$('source-filter').value=state.source;$('run-filter').replaceChildren(option('','최신 데이터 전체'));for(const run of runs.rows)$('run-filter').append(option(run.run_id,`${date(run.started_at)} · ${run.count}건`));if(state.run&&!runs.rows.some(r=>r.run_id===state.run))$('run-filter').append(option(state.run,state.run));$('run-filter').value=state.run;if(!summary.ready)error('아직 저장된 데이터가 없습니다. trend_collector.py로 먼저 수집해 주세요.');await load();}catch(e){error(e.message);}}
async function load(){if(state.view==='analysis'){await loadAnalysis();return;}const serial=++state.serial;const parent=state.view==='browse'?$('items'):$('runs');empty(parent,'불러오는 중…','저장된 데이터를 확인하고 있습니다.');try{const data=await api(state.view==='browse'?'/api/items':'/api/runs',{q:state.query,source:state.source,run:state.run,page:state.page,page_size:state.size});if(serial!==state.serial)return;state.total=data.total;parent.replaceChildren();if(!data.rows.length)empty(parent,'표시할 데이터가 없습니다','검색 조건을 바꾸거나 새 데이터를 수집해 주세요.');if(state.view==='browse'){for(const item of data.rows)renderItem(item,parent);$('result-count').textContent=data.total.toLocaleString();$('filter-caption').textContent=`${state.source?label(state.source):'모든 소스'} · ${state.run?'선택한 실행의 관측값':'최신 관측순'}`;}else for(const run of data.rows)renderRun(run,parent);for(const button of document.querySelectorAll('.source-button'))button.classList.toggle('selected',button.dataset.source===state.source);pagination();}catch(e){if(serial!==state.serial)return;error(e.message);empty(parent,'조회하지 못했습니다','새로고침하여 다시 시도해 주세요.');}}
function renderItem(item,parent){const row=el('article','item');const name=label(item.source);row.append(el('div','source-icon',name.split(' ').map(s=>s[0]).join('').slice(0,2).toUpperCase()));const main=el('div','item-main');const meta=el('div','item-meta');meta.append(el('strong','',name),el('span','','·'),el('span','',item.published_at?date(item.published_at):'게시 시각 미제공'));const title=el('button','item-title',item.title);title.onclick=()=>showDetail(item);main.append(meta,title);if(item.summary)main.append(el('div','item-summary',item.summary));const tags=el('div','tags');for(const tag of [...(item.tags||[]),...(item.metadata?.cve_ids||[])].slice(0,5))tags.append(el('span','tag',tag));main.append(tags);const end=el('div','item-end');end.append(el('div','',`관측 ${date(item.observed_at)}`),el('div','metrics',metrics(item.metrics)));row.append(main,end);parent.append(row);}
function renderRun(run,parent){const card=el('article','run-card');const head=el('div','run-head');const title=el('div');title.append(el('strong','',date(run.started_at)),el('div','run-id',run.run_id));const button=el('button','button',`${run.count}건 살펴보기 →`);button.onclick=()=>{state.run=run.run_id;if(!$('run-filter').querySelector(`option[value="${CSS.escape(run.run_id)}"]`))$('run-filter').append(option(run.run_id,run.run_id));$('run-filter').value=run.run_id;state.source='';$('source-filter').value='';state.query='';$('search').value='';setView('browse');};head.append(title,button);const statuses=el('div','source-status');for(const [source,status]of Object.entries(run.sources)){const badge=el('span','status'+(status.status==='ok'?'':' bad'),`${label(source)} · ${status.status} · ${status.count}`);statuses.append(badge);}card.append(head,statuses);const errors=Object.entries(run.sources).filter(([,s])=>s.message);if(errors.length)card.append(el('div','run-errors',errors.map(([name,s])=>`${label(name)}: ${s.message}`).join('\n')));parent.append(card);}
function addSection(parent,title,value){parent.append(el('div','detail-label',title));parent.append(el('pre','json',JSON.stringify(value,null,2)));}
function safeLink(url,title){try{const parsed=new URL(url);if(!['http:','https:'].includes(parsed.protocol))return null;const node=el('a','button',title);node.href=parsed.href;node.target='_blank';node.rel='noopener noreferrer';return node;}catch{return null;}}
async function showDetail(item){const serial=++state.detailSerial;const body=$('detail-body');body.replaceChildren(el('p','','상세 정보를 불러오는 중…'));if(!$('detail').open)$('detail').showModal();try{const data=await api('/api/item',{source:item.source,id:item.external_id,run:state.run});if(serial!==state.detailSerial)return;const row=data.item;body.replaceChildren(el('span','tag',label(row.source)),el('h2','detail-title',row.title));const links=el('div','detail-links');const original=safeLink(row.url,'원문 열기 ↗');if(original)links.append(original);if(row.discussion_url&&row.discussion_url!==row.url){const discussion=safeLink(row.discussion_url,'토론 열기 ↗');if(discussion)links.append(discussion);}body.append(links,el('p','detail-summary',row.summary||'제공된 요약이 없습니다.'));addSection(body,'수집 정보',{published_at:row.published_at,observed_at:row.observed_at,rank:row.rank,collection_method:row.collection_method});addSection(body,'지표',row.metrics);addSection(body,'메타데이터',row.metadata);body.append(el('div','detail-label',`최근 관측 이력 · 최대 100건 (${data.history.length}건 표시)`));for(const history of data.history){const node=el('div','history-row',`${date(history.observed_at)} · ${history.run_id}`);node.append(el('pre','json',JSON.stringify(history.metrics,null,2)));body.append(node);}}catch(e){body.replaceChildren(el('p','',e.message));}}
function setView(view){state.view=view;state.page=1;for(const name of ['browse','runs','analysis']){$(name+'-view').hidden=view!==name;$(name+'-nav').classList.toggle('active',view===name);}$('pagination').hidden=view==='analysis';const titles={browse:'수집 데이터',runs:'실행 이력',analysis:'트렌드 분석'};$('heading').textContent=$('crumb').textContent=titles[view];$('subtitle').textContent=view==='analysis'?'새로운 주제와 변화의 근거를 살펴보세요.':view==='browse'?'흩어진 소식을 한곳에서 살펴보세요.':'수집이 어떻게 진행되었는지 확인하세요.';load();}
let analysisReport=null;
async function loadAnalysis(){const serial=++state.serial;try{const data=await api('/api/analysis',{id:$('analysis-select').value});if(serial!==state.serial)return;const selected=data.report?.analysis_id||'';$('analysis-select').replaceChildren(option('','최근 분석'));for(const run of data.rows)$('analysis-select').append(option(run.analysis_id,`${date(run.created_at)} · ${run.version}`));$('analysis-select').value=selected;analysisReport=data.report;renderAnalysis();}catch(e){error(e.message);}}
function renderAnalysis(){
  const parent=$('analysis-results'), summary=$('analysis-summary');
  parent.replaceChildren();summary.replaceChildren();
  const report=analysisReport;
  if(!report){empty(parent,'아직 분석 결과가 없습니다','터미널에서 uv run trend_analyzer.py --config config.toml 을 실행해 주세요.');return;}
  const categories=report.summary.categories;
  const selectedCategory=$('category-filter').value,selectedType=$('news-type-filter').value;
  $('category-filter').replaceChildren(option('','모든 카테고리'));
  $('news-type-filter').replaceChildren(option('','모든 소식 성격'));
  for(const [category,count]of Object.entries(categories||{}))$('category-filter').append(option(category,`${category} · ${count}개 항목`));
  for(const [type,count]of Object.entries(report.summary.news_types||{}))$('news-type-filter').append(option(type,`${type} · ${count}개 항목`));
  $('category-filter').value=Object.hasOwn(categories||{},selectedCategory)?selectedCategory:'';
  $('news-type-filter').value=Object.hasOwn(report.summary.news_types||{},selectedType)?selectedType:'';
  $('category-filter').disabled=$('news-type-filter').disabled=!categories;
  const category=$('category-filter').value,newsType=$('news-type-filter').value;
  summary.append(el('p','',`${date(report.window.start)} ~ ${date(report.window.end)} · 고유 항목 ${report.summary.items}건 · 처음 관측 ${report.summary.new_items}건`));
  summary.append(el('p','',report.coverage.comparable?'공통 정상 수집 소스의 고유 항목 수로 비교합니다. 수집 빈도와 범위의 영향을 받을 수 있습니다.':'이전 비교 기간의 데이터가 부족합니다. 증가 신호를 계산하지 않았습니다.'));
  if(!categories)summary.append(el('p','','이전 분류 버전의 분석입니다. 새 카테고리로 보려면 분석을 다시 실행해 주세요.'));
  const topics=el('div','tags');
  for(const [topic,count]of Object.entries(categories||report.summary.topics)){
    if(categories){const button=el('button','tag category-chip'+(category===topic?' selected':''),`${topic} · ${count}`);button.onclick=()=>{$('category-filter').value=topic;renderAnalysis();};topics.append(button);}
    else topics.append(el('span','tag',`${topic} · ${count}`));
  }
  summary.append(topics);
  const filter=$('signal-filter').value;
  const trends=report.trends.filter(t=>(!category||t.primary_category===category)&&(!newsType||(t.news_types||[]).includes(newsType))&&(filter==='all'||filter==='new'&&t.new_items_only||filter==='multi'&&t.multi_source||filter==='increasing'&&t.increasing||filter==='security'&&t.topics.some(topic=>['보안','보안·개인정보'].includes(topic))));
  summary.append(el('p','',`${trends.length}개 묶음 · 대표 카테고리별로 한 번씩 표시합니다. 관련 분야와 소식 성격은 중복될 수 있습니다.`));
  if(!trends.length)empty(parent,'해당 조건의 묶음이 없습니다','다른 카테고리나 소식 성격을 선택해 주세요.');
  const categoryOrder=categories?Object.keys(categories):['이전 분류'];
  for(const groupCategory of categoryOrder){
    const members=trends.filter(t=>(t.primary_category||'이전 분류')===groupCategory);
    if(!members.length)continue;
    const section=el('section','analysis-category-group');
    const heading=el('h2','category-heading',groupCategory);heading.append(el('span','tag',`${members.length}개 묶음`));section.append(heading);
    for(const trend of members)section.append(renderTrendCard(trend));
    parent.append(section);
  }
  const classifications=new Map(report.classifications.map(row=>[JSON.stringify([row.source,row.external_id]),row]));
  const changes=report.metric_changes.filter(item=>{const c=classifications.get(JSON.stringify([item.source,item.external_id]));return(!category||c?.primary_category===category)&&(!newsType||c?.news_types?.includes(newsType));});
  if(changes.length){const card=el('article','run-card');card.append(el('h2','','선택 분야 항목의 관측 지표 변화'));for(const item of changes){const row=el('div','analysis-evidence');row.append(el('strong','',`${label(item.source)} · ${item.title}`));for(const [key,value]of Object.entries(item.metrics))row.append(el('p','',`${key}: ${value.before} → ${value.after} (${value.delta>0?'+':''}${value.delta})`));if(item.rank_improvement)row.append(el('p','',`순위 개선: ${item.rank_improvement}`));card.append(row);}parent.append(card);}
  const notes=el('article','run-card');notes.append(el('h2','','해석 범위'));for(const note of report.notes)notes.append(el('p','',note));parent.append(notes);
}
function renderTrendCard(trend){
  const card=el('article','run-card');card.append(el('h3','trend-title',trend.name));const badges=el('div','tags');
  for(const topic of trend.related_categories||trend.topics)badges.append(el('span','tag',`관련 · ${topic}`));
  for(const type of trend.news_types||[])badges.append(el('span','tag news-type-tag',type));
  if(trend.new_items_only)badges.append(el('span','tag','처음 관측한 항목'));
  if(trend.multi_source)badges.append(el('span','tag','여러 출처'));
  card.append(badges,el('p','analysis-count',`고유 항목 ${trend.items}건 · 출처 ${trend.sources.length}곳 · 이전 구간 ${trend.baseline_items}건${trend.comparable_item_delta===null?'':` · 공통 소스 차이 ${trend.comparable_item_delta>0?'+':''}${trend.comparable_item_delta}건`}`));
  for(const item of trend.evidence){
    const evidence=el('div','analysis-evidence'),link=safeLink(item.url,item.title+' ↗');
    if(link){link.className='evidence-link';evidence.append(link);}else evidence.append(el('strong','',item.title));
    evidence.append(el('p','',`${label(item.source)} · 관측 ${date(item.observed_at)}`));
    const signal=metrics(item.metrics);if(signal)evidence.append(el('p','',signal));
    if(item.metrics?.epss)evidence.append(el('pre','json',JSON.stringify(item.metrics.epss,null,2)));
    if(item.classification){const c=item.classification,details=el('details','classification-reasons');details.append(el('summary','',`분류 근거 · ${c.primary_category}`));for(const [field,terms]of Object.entries(c.category_reasons))details.append(el('p','',`${field}: ${terms.length?terms.join(', '):'매칭 근거 부족'}`));for(const [type,terms]of Object.entries(c.news_type_reasons))details.append(el('p','',`${type}: ${terms.join(', ')}`));evidence.append(details);}
    card.append(evidence);
  }
  return card;
}
$('category-filter').onchange=renderAnalysis;$('news-type-filter').onchange=renderAnalysis;
$('analysis-nav').onclick=()=>setView('analysis');$('analysis-select').onchange=loadAnalysis;$('signal-filter').onchange=renderAnalysis;
$('browse-nav').onclick=()=>setView('browse');$('runs-nav').onclick=()=>setView('runs');$('refresh').onclick=refresh;$('close-detail').onclick=()=>{$('detail').close();state.detailSerial++;};$('source-filter').onchange=()=>{state.source=$('source-filter').value;state.page=1;load();};$('run-filter').onchange=()=>{state.run=$('run-filter').value;state.page=1;load();};let timer;$('search').oninput=()=>{clearTimeout(timer);timer=setTimeout(()=>{state.query=$('search').value;state.page=1;load();},250);};$('prev').onclick=()=>{state.page--;load();};$('next').onclick=()=>{state.page++;load();};refresh();
