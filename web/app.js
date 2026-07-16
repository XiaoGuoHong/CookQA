const form = document.querySelector('#search-form');
const queryInput = document.querySelector('#query-input');
const searchButton = document.querySelector('#search-button');
const statusBox = document.querySelector('#status');
const resultsBox = document.querySelector('#results');
const degradationBox = document.querySelector('#degradation');
const cardTemplate = document.querySelector('#recipe-card-template');
const detailPanel = document.querySelector('#detail-panel');
const detailTitle = document.querySelector('#detail-title');
const detailContent = document.querySelector('#detail-content');
const answerQuestion = document.querySelector('#answer-question');
const answerButton = document.querySelector('#answer-button');
const answerOutput = document.querySelector('#answer-output');

let selectedRecipeId = null;
let answerController = null;

function setStatus(message) {
  statusBox.textContent = message;
}

function text(element, value) {
  element.textContent = value ?? '';
  return element;
}

function element(tag, value, className) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  return text(node, value);
}

function showDegradation(degradation) {
  const messages = [...(degradation?.warnings || [])];
  if (degradation?.unavailable_components?.length) {
    messages.unshift(`不可用组件：${degradation.unavailable_components.join('、')}`);
  }
  degradationBox.hidden = messages.length === 0;
  degradationBox.textContent = messages.join(' ');
}

async function requestJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let message = '请求失败，请稍后重试。';
    try {
      const payload = await response.json();
      message = payload.detail || message;
    } catch (_) {
      // The public message intentionally hides server internals.
    }
    throw new Error(message);
  }
  return response.json();
}

async function searchRecipes(query) {
  return requestJson('/api/v1/search', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({query}),
  });
}

function createCard(result) {
  const fragment = cardTemplate.content.cloneNode(true);
  const recipe = result.recipe;
  const button = fragment.querySelector('.recipe-card__button');
  text(fragment.querySelector('.recipe-card__category'), recipe.categories?.join(' · ') || '未分类');
  text(fragment.querySelector('.recipe-card__score'), `RRF ${Number(result.score).toFixed(3)}`);
  text(fragment.querySelector('.recipe-card__name'), recipe.name);
  const metadata = [recipe.difficulty, recipe.duration_minutes ? `${recipe.duration_minutes} 分钟` : null]
    .filter(Boolean)
    .join(' · ');
  text(fragment.querySelector('.recipe-card__meta'), metadata || '难度与耗时未确认');
  text(
    fragment.querySelector('.recipe-card__ingredients'),
    `主要食材：${recipe.ingredients.slice(0, 5).map((item) => item.name).join('、')}`,
  );
  const reasons = fragment.querySelector('.recipe-card__reasons');
  (result.reasons?.length ? result.reasons : result.retrieval_sources).forEach((reason) => {
    reasons.append(element('span', reason));
  });
  text(fragment.querySelector('.recipe-card__source'), `来源：HowToCook / ${recipe.source_path}`);
  text(
    fragment.querySelector('.recipe-card__verification'),
    result.constraints_verified ? '' : '⚠ 明确条件尚未完成图数据库验证',
  );
  button.addEventListener('click', () => openRecipe(recipe.recipe_id));
  return fragment;
}

function renderResults(payload) {
  resultsBox.replaceChildren();
  showDegradation(payload.degradation);
  const results = payload.results || [];
  results.forEach((result) => resultsBox.append(createCard(result)));
  const elapsed = Object.values(payload.timings_ms || {}).reduce((sum, value) => sum + value, 0);
  setStatus(results.length ? `找到 ${results.length} 道菜 · 检索阶段 ${elapsed.toFixed(0)} ms` : '没有找到满足条件的菜谱。');
  if (payload.query_plan?.intent === 'exact_recipe' && results.length === 1) {
    openRecipe(results[0].recipe.recipe_id);
  }
}

function renderDetail(recipe) {
  detailTitle.textContent = recipe.name;
  detailContent.replaceChildren();
  const facts = [
    recipe.categories?.length ? `分类：${recipe.categories.join('、')}` : null,
    recipe.difficulty ? `难度：${recipe.difficulty}` : '难度：未确认',
    recipe.duration_minutes ? `耗时：${recipe.duration_minutes} 分钟` : '耗时：未确认',
  ].filter(Boolean);
  detailContent.append(element('p', facts.join(' · ')));
  if (recipe.summary) detailContent.append(element('p', recipe.summary));

  detailContent.append(element('h3', '食材'));
  const ingredients = document.createElement('ul');
  recipe.ingredients.forEach((item) => ingredients.append(element('li', item.raw)));
  detailContent.append(ingredients);

  detailContent.append(element('h3', '步骤'));
  const steps = document.createElement('ol');
  recipe.steps.forEach((step) => steps.append(element('li', step)));
  detailContent.append(steps);

  const tags = element('div', '', 'detail-tags');
  (recipe.tags || []).forEach((tag) => tags.append(element('span', `${tag} · 推断标签`)));
  if (tags.childElementCount) detailContent.append(tags);
  detailContent.append(element('p', `来源：HowToCook / ${recipe.source_path}`));
  detailPanel.hidden = false;
  detailPanel.scrollIntoView({behavior: 'smooth', block: 'start'});
}

async function openRecipe(recipeId) {
  selectedRecipeId = recipeId;
  answerOutput.textContent = '';
  try {
    const recipe = await requestJson(`/api/v1/recipes/${encodeURIComponent(recipeId)}`);
    renderDetail(recipe);
  } catch (error) {
    setStatus(error.message);
  }
}

async function streamAnswer() {
  if (!selectedRecipeId) return;
  answerButton.disabled = true;
  answerController = new AbortController();
  document.querySelector('#stop-answer')?.toggleAttribute('disabled', false);
  answerOutput.textContent = '正在连接本地模型…';
  try {
    const response = await fetch(
      `/api/v1/recipes/${encodeURIComponent(selectedRecipeId)}/answer/stream`,
      {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({question: answerQuestion.value.trim() || null}),
        signal: answerController?.signal,
      },
    );
    if (!response.ok || !response.body) throw new Error('本地模型暂时不可用。');
    answerOutput.textContent = '';
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
      const {value, done} = await reader.read();
      if (done) break;
      answerOutput.textContent += decoder.decode(value, {stream: true});
    }
  } catch (error) {
    answerOutput.textContent = error.message;
  } finally {
    answerButton.disabled = false;
  }
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const query = queryInput.value.trim();
  if (!query) return;
  searchButton.disabled = true;
  resultsBox.replaceChildren();
  degradationBox.hidden = true;
  setStatus('正在并行检索本地索引…');
  try {
    renderResults(await searchRecipes(query));
  } catch (error) {
    setStatus(error.message);
  } finally {
    searchButton.disabled = false;
  }
});

document.querySelectorAll('[data-query]').forEach((button) => {
  button.addEventListener('click', () => {
    queryInput.value = button.dataset.query;
    form.requestSubmit();
  });
});

document.querySelector('#close-detail').addEventListener('click', () => {
  detailPanel.hidden = true;
  selectedRecipeId = null;
});
answerButton.addEventListener('click', streamAnswer);

const pantryForm = document.querySelector('#pantry-form');
const pantrySearchButton = document.querySelector('#pantry-search-button');
const searchModeForm = document.querySelector('#search-form');

function splitIngredients(value) {
  return value.split(/[，,、\n]/).map((item) => item.trim()).filter(Boolean);
}

function renderPantry(payload) {
  resultsBox.replaceChildren();
  showDegradation({warnings: payload.warnings});
  for (const [group, label] of [['ready', '可以直接做'], ['near', '还差 1-2 种主要食材'], ['related', '其他相关建议']]) {
    const matches = payload[group] || [];
    if (!matches.length) continue;
    resultsBox.append(element('h3', label, 'results__group-title'));
    matches.forEach((match) => {
      const card = element('article', '', 'recipe-card');
      const button = element('button', '', 'recipe-card__button');
      button.type = 'button';
      button.append(element('strong', match.recipe.name));
      button.append(element('p', `覆盖率 ${(match.coverage * 100).toFixed(0)}% · 已有：${match.available_ingredients.join('、') || '无'}`));
      button.append(element('p', `缺少：${match.missing_ingredients.join('、') || '无'} · 可选：${match.optional_ingredients.join('、') || '无'}`));
      button.append(element('p', (match.reasons || []).join(' · ')));
      button.addEventListener('click', () => openRecipe(match.recipe.recipe_id));
      card.append(button);
      resultsBox.append(card);
    });
  }
  const count = ['ready', 'near', 'related'].reduce((sum, key) => sum + (payload[key] || []).length, 0);
  setStatus(count ? `找到 ${count} 道匹配菜谱` : '没有找到匹配菜谱，请减少限制条件');
}

async function searchPantry() {
  const existing = splitIngredients(document.querySelector('#existing-ingredients').value);
  if (!existing.length) return;
  const excluded = splitIngredients(document.querySelector('#excluded-ingredients').value);
  const max = document.querySelector('#max-minutes').value;
  pantrySearchButton.disabled = true;
  setStatus('正在按现有食材匹配菜谱…');
  try {
    const payload = await requestJson('/api/v1/pantry/search', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        existing_ingredients: existing,
        excluded_ingredients: excluded,
        max_minutes: max ? Number(max) : null,
        no_spicy: document.querySelector('#no-spicy').checked,
        use_pantry_staples: document.querySelector('#use-staples').checked,
      }),
    });
    renderPantry(payload);
  } catch (error) {
    setStatus(error.message);
  } finally {
    pantrySearchButton.disabled = false;
  }
}

pantryForm?.addEventListener('submit', (event) => {
  event.preventDefault();
  searchPantry();
});
document.querySelectorAll('[data-mode]').forEach((button) => {
  button.addEventListener('click', () => {
    const pantry = button.dataset.mode === 'pantry';
    document.querySelectorAll('[data-mode]').forEach((item) => {
      const active = item === button;
      item.classList.toggle('is-active', active);
      item.setAttribute('aria-selected', String(active));
    });
    searchModeForm.hidden = pantry;
    pantryForm.hidden = !pantry;
  });
});
document.querySelectorAll('[data-question]').forEach((button) => {
  button.addEventListener('click', () => {
    answerQuestion.value = button.dataset.question;
    streamAnswer();
  });
});
document.querySelector('#stop-answer')?.addEventListener('click', () => {
  answerController?.abort();
  answerOutput.textContent += '\n已停止生成。';
});
document.querySelector('#retry-answer')?.addEventListener('click', streamAnswer);
document.querySelector('#copy-answer')?.addEventListener('click', async () => {
  if (answerOutput.textContent) await navigator.clipboard.writeText(answerOutput.textContent);
});