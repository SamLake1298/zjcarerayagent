'use strict';
const $ = id => document.getElementById(id);
let catalog, busy = false;
const selections = new Map();
const rowElements = new Map();
function solutionLabel(supplier) {
  const title = supplier.file.replace(/\.docx$/i, '').replace(/（框架整理版）|框架整理版/g, '').split('-').slice(1).join('-');
  return `${supplier.label} · ${title || '建设方案'}`;
}
function el(tag, text, className) { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (className) node.className = className; return node; }
function toast(message) { $('toast').textContent = message; $('toast').hidden = false; setTimeout(() => $('toast').hidden = true, 3500); }
function updateSummary() {
  $('selectedCount').textContent = selections.size;
  $('selectedList').replaceChildren();
  for (const m of catalog.modules) for (const s of m.sections) if (selections.has(s.id)) {
    const item = el('div', undefined, 'selection-chip'); item.append(el('span', `${s.id} ${s.title}`));
    const remove = el('button', '×'); remove.setAttribute('aria-label', `移除${s.title}`); remove.disabled = busy;
    remove.onclick = () => { selections.delete(s.id); syncRows(); }; item.append(remove); $('selectedList').append(item);
  }
  if (!selections.size) $('selectedList').append(el('p', '从左侧选择本次建设内容'));
  $('generateBtn').disabled = busy || !selections.size;
  $('generateBtn').textContent = busy ? '正在生成…' : '开始生成 →';
}
function syncRows() {
  for (const [id, r] of rowElements) {
    r.checkbox.checked = selections.has(id); r.control.hidden = !selections.has(id);
    if (selections.has(id)) r.select.value = selections.get(id);
    const supplier = catalog.suppliers.find(p => p.id === r.select.value);
    r.file.textContent = supplier ? `来源：${supplier.file}` : '暂无可用方案';
  }
  for (const m of catalog.modules) {
    const count = m.sections.filter(s => selections.has(s.id)).length;
    document.querySelector(`[data-count="${m.id}"]`).textContent = count ? `${count} / ${m.sections.length} 已选` : `${m.sections.length} 个子节`;
  }
  updateSummary();
}
function buildModules() {
  for (const [index, m] of catalog.modules.entries()) {
    const nav = el('button'); nav.append(el('span', m.id), document.createTextNode(m.title));
    nav.onclick = () => { $('search').value = ''; filterModules(); const target = $(m.id); target.open = true; target.scrollIntoView({behavior:'smooth',block:'start'}); }; $('moduleNav').append(nav);
    const details = el('details', undefined, 'module'); details.id = m.id; details.open = index === 3;
    const summary = el('summary'); const count = el('span', `${m.sections.length} 个子节`, 'count'); count.dataset.count = m.id;
    summary.append(el('span', m.id, 'number'), el('span', m.title), count); details.append(summary);
    const body = el('div', undefined, 'module-body'), tools = el('div', undefined, 'module-tools');
    tools.append(el('span', '按子节选择建设内容与方案'));
    const all = el('button', '选择本模块', 'text-button'); all.onclick = () => { for (const s of m.sections) if (!selections.has(s.id) && rowElements.get(s.id).select.value) selections.set(s.id, rowElements.get(s.id).select.value); syncRows(); }; tools.append(all); body.append(tools);
    for (const s of m.sections) {
      const row = el('div', undefined, 'section-row'); row.dataset.search = `${m.title} ${s.title}`;
      const label = el('label', undefined, 'check-label'), checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.dataset.section = s.id;
      const text = el('span', `${s.id} ${s.title}`); if (s.headings.length) text.append(el('small', s.headings.join(' · ')));
      label.append(checkbox, text); row.append(label);
      const control = el('div', undefined, 'solution-control'); control.hidden = true;
      const select = document.createElement('select'); select.setAttribute('aria-label', `${s.title}的参考方案`);
      for (const id of s.supplier_ids) { const p = catalog.suppliers.find(x => x.id === id); const option = el('option', solutionLabel(p)); option.value = id; select.append(option); }
      const supplier = catalog.suppliers.find(p => p.id === select.value);
      const file = el('div', supplier ? `来源：${supplier.file}` : '暂无可用方案', 'solution-file');
      if (!s.supplier_ids.length) { checkbox.disabled = true; checkbox.dataset.unavailable = 'true'; text.append(el('small', '暂无可用方案，待补充材料')); }
      select.onchange = () => { selections.set(s.id, select.value); syncRows(); };
      checkbox.onchange = () => { if (checkbox.checked) selections.set(s.id, select.value); else selections.delete(s.id); syncRows(); };
      control.append(select, file); row.append(control); body.append(row); rowElements.set(s.id, {checkbox, control, select, row, file});
    }
    details.append(body); $('modules').append(details);
  }
}
function filterModules() {
  const query = $('search').value.trim().toLowerCase();
  for (const m of catalog.modules) { let matches = 0; for (const s of m.sections) { const row = rowElements.get(s.id).row; row.hidden = !row.dataset.search.toLowerCase().includes(query); if (!row.hidden) matches++; } $(m.id).hidden = !matches; if (query && matches) $(m.id).open = true; }
}
function setBusy(value) { busy = value; for (const node of document.querySelectorAll('.module input,.module select,.module button,#mode,#clearBtn,.project-card input,.project-card textarea')) node.disabled = value || node.dataset.unavailable === 'true'; updateSummary(); }
function renderResult(result) {
  $('preview').replaceChildren(el('h2', '第四章 项目建设内容与设计方案'));
  let lastModule;
  for (const s of result.sections) { if (s.module_id !== lastModule) { $('preview').append(el('h3', `${s.module_id} ${s.module_title}`)); lastModule = s.module_id; }
    $('preview').append(el('h4', `${s.id} ${s.title}`));
    s.blocks.forEach((b,index) => { if (b.title) $('preview').append(el('h5', `${s.id}.${index} ${b.title}`)); for (const p of b.paragraphs) $('preview').append(el('p', p)); });
  }
  $('resultMeta').textContent = result.mode === 'demo' ? '演示文件：未调用大模型，未融合所选供应商方案。以下正文仅为流程验证用占位示例。' : 'DeepSeek生成初稿。请复核建设内容、品牌用语及待补充参数，确认后用于正式编制。';
  $('downloadBtn').href = `/api/jobs/${result.id}/download`; $('downloadBtn').hidden = false;
}
async function poll(id) {
  try {
    const response = await fetch(`/api/jobs/${id}`); const job = await response.json(); if (!response.ok) throw Error(job.error || '读取任务失败');
    $('progress').value = job.completed / job.total * 100;
    $('progressText').textContent = `${job.completed} / ${job.total} 个子节 · ${job.current}`;
    if (job.status === 'done') { $('resultTitle').textContent = '第四章初稿已生成'; renderResult(job.result); setBusy(false); }
    else if (job.status === 'error') { throw Error(job.error); }
    else setTimeout(() => poll(id), 1200);
  } catch (error) { $('errorBox').textContent = `${error.message}。已选配置保留，可重新生成。`; $('errorBox').hidden = false; $('resultTitle').textContent = '生成未完成'; setBusy(false); }
}
async function generate() {
  if (!selections.size || busy) return;
  setBusy(true); $('resultPanel').hidden = false; $('resultTitle').textContent = '正在编制第四章'; $('progressText').textContent = '准备材料…'; $('errorBox').hidden = true; $('downloadBtn').hidden = true; $('preview').replaceChildren(); $('resultMeta').textContent = ''; $('progress').value = 0;
  $('resultPanel').scrollIntoView({behavior:'smooth',block:'start'});
  const payload = {mode:$('mode').value, model:$('model').value.trim(), api_key:$('apiKey').value.trim(), project:{name:$('projectName').value.trim(),region:$('region').value.trim(),owner:$('owner').value.trim(),facts:$('facts').value.trim()}, selections:[...selections].map(([id,supplier])=>({id,supplier}))};
  try { const response = await fetch('/api/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}); const result = await response.json(); if (!response.ok) throw Error(result.error || '生成请求失败'); poll(result.id); }
  catch (error) { $('errorBox').textContent = error.message; $('errorBox').hidden = false; $('resultTitle').textContent = '暂时无法开始生成'; setBusy(false); }
}
async function init() {
  try { const response = await fetch('/api/catalog'); if (!response.ok) throw Error('材料加载失败'); catalog = await response.json(); buildModules();
    $('sourceStats').textContent = `1 份建议书模板 · ${catalog.suppliers.length} 份方案 · ${catalog.modules.length} 个模块`;
    $('moduleCount').textContent = catalog.modules.length; updateSummary();
  } catch(error) { $('modules').append(el('div', `${error.message}，请确认本地服务和data/catalog.json正常。`, 'error')); }
}
$('settingsBtn').onclick = () => $('settings').showModal();
$('workspaceBtn').onclick = () => window.scrollTo({top:0,behavior:'smooth'});
$('clearBtn').onclick = () => { selections.clear(); syncRows(); };
$('search').oninput = filterModules;
function updateModeNote() { $('modeNote').textContent = $('mode').value === 'demo' ? '仅验证流程，使用占位示例，不调用模型、不融合供应商方案。' : '按所选材料逐节调用DeepSeek，可能需要数分钟，并产生API费用。'; }
$('mode').onchange = () => { updateModeNote(); if ($('mode').value === 'deepseek' && !$('apiKey').value.trim()) $('settings').showModal(); };
$('settings').querySelector('form').addEventListener('submit', event => {
  if (!event.submitter?.classList.contains('close-button') && $('apiKey').value.trim() && !busy) {
    $('mode').value = 'deepseek'; updateModeNote(); toast('已切换到DeepSeek生成');
  }
});
$('generateBtn').onclick = generate;
init();
