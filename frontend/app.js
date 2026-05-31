const API_BASE_URL = 'http://127.0.0.1:8000';

const elements = {
  status: document.getElementById('status'),
  databaseType: document.getElementById('databaseType'),
  schemaList: document.getElementById('schemaList'),
  refreshSchemaBtn: document.getElementById('refreshSchemaBtn'),
  englishInput: document.getElementById('englishInput'),
  generateBtn: document.getElementById('generateBtn'),
  sqlEditor: document.getElementById('sqlEditor'),
  fixBtn: document.getElementById('fixBtn'),
  runBtn: document.getElementById('runBtn'),
  resultMeta: document.getElementById('resultMeta'),
  resultArea: document.getElementById('resultArea'),
  suggestions: document.getElementById('suggestions'),
  chatMessages: document.getElementById('chatMessages'),
  chatInput: document.getElementById('chatInput'),
  sendChatBtn: document.getElementById('sendChatBtn'),
  confirmOverlay: document.getElementById('confirmOverlay'),
  confirmSql: document.getElementById('confirmSql'),
  confirmNotes: document.getElementById('confirmNotes'),
  confirmRunBtn: document.getElementById('confirmRunBtn'),
  cancelRunBtn: document.getElementById('cancelRunBtn'),
  mssqlConnectionPanel: document.getElementById('mssqlConnectionPanel'),
  mssqlHost: document.getElementById('mssqlHost'),
  mssqlPort: document.getElementById('mssqlPort'),
  mssqlDatabase: document.getElementById('mssqlDatabase'),
  mssqlUsername: document.getElementById('mssqlUsername'),
  mssqlPassword: document.getElementById('mssqlPassword'),
  mssqlDriver: document.getElementById('mssqlDriver'),
  mssqlTrustCert: document.getElementById('mssqlTrustCert'),
  connectMssqlBtn: document.getElementById('connectMssqlBtn'),
  mssqlConnectionStatus: document.getElementById('mssqlConnectionStatus'),
};

const sharedMemory = {
  history: [],
  generatedSql: '',
  lastQuestion: '',
  lastReview: null,
  lastResult: null,
};

let pendingExecution = null;
let mssqlConnection = null;

function setLoading(isLoading, label = 'Working...') {
  elements.status.textContent = isLoading ? label : 'Ready';
  elements.status.className = isLoading ? 'status loading' : 'status';
  elements.generateBtn.disabled = isLoading;
  elements.runBtn.disabled = isLoading;
  elements.fixBtn.disabled = isLoading;
  elements.sendChatBtn.disabled = isLoading;
}

function setStatus(label, kind = '') {
  elements.status.textContent = label;
  elements.status.className = `status ${kind}`.trim();
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function parsePossibleJson(value) {
  const text = String(value || '').trim();
  if (!text) return null;
  const fenced = text.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
  const candidate = fenced ? fenced[1].trim() : text;
  if (!candidate.startsWith('{') && !candidate.startsWith('[')) return null;
  try {
    return JSON.parse(candidate);
  } catch {
    return null;
  }
}

function humanizeKey(key) {
  return String(key)
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function renderStructuredValue(value) {
  if (value == null || value === '') return '';
  if (Array.isArray(value)) {
    return `<ul>${value.map((item) => `<li>${renderStructuredValue(item)}</li>`).join('')}</ul>`;
  }
  if (typeof value === 'object') {
    return Object.entries(value)
      .map(([key, item]) => `
        <section class="json-card">
          <h4>${escapeHtml(humanizeKey(key))}</h4>
          ${renderStructuredValue(item)}
        </section>
      `)
      .join('');
  }
  return `<span>${escapeHtml(value)}</span>`;
}

function formatAssistantMessage(rawText) {
  const parsed = parsePossibleJson(rawText);
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return escapeHtml(rawText);
  }

  const title = parsed.title || parsed.topic || '';
  const answer = parsed.answer ? `<p>${escapeHtml(parsed.answer)}</p>` : '';
  const examples = Array.isArray(parsed.examples) && parsed.examples.length
    ? `
      <section class="structured-section">
        <h3>Examples</h3>
        ${parsed.examples.map((example, index) => `
          <article class="example-card">
            <h4>${escapeHtml(example.scenario || `Example ${index + 1}`)}</h4>
            ${Object.entries(example)
              .filter(([key]) => key !== 'scenario')
              .map(([key, value]) => `<p><strong>${escapeHtml(humanizeKey(key))}:</strong> ${renderStructuredValue(value)}</p>`)
              .join('')}
          </article>
        `).join('')}
      </section>
    `
    : '';
  const rest = Object.entries(parsed)
    .filter(([key]) => !['title', 'topic', 'answer', 'examples'].includes(key))
    .map(([key, value]) => `
      <section class="structured-section">
        <h3>${escapeHtml(humanizeKey(key))}</h3>
        ${renderStructuredValue(value)}
      </section>
    `)
    .join('');

  return `
    <div class="structured-message">
      ${title ? `<h3>${escapeHtml(title)}</h3>` : ''}
      ${answer}
      ${examples}
      ${rest}
    </div>
  `;
}

async function apiRequest(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json().catch(async () => ({ error: await response.text().catch(() => '') }));
  if (!response.ok) {
    throw new Error(payload.detail || payload.error || `Request failed with status ${response.status}`);
  }
  return payload;
}

function selectedDatabase() {
  if (elements.databaseType.value !== 'mssql') return { type: 'postgresql' };
  return mssqlConnection || { type: 'mssql' };
}

function readMssqlConnection() {
  return {
    type: 'mssql',
    host: elements.mssqlHost.value.trim(),
    port: elements.mssqlPort.value ? Number(elements.mssqlPort.value) : null,
    database: elements.mssqlDatabase.value.trim(),
    username: elements.mssqlUsername.value.trim(),
    password: elements.mssqlPassword.value,
    driver: elements.mssqlDriver.value.trim() || 'ODBC Driver 17 for SQL Server',
    trust_server_certificate: elements.mssqlTrustCert.checked,
  };
}

function hasMssqlConnection(connection = selectedDatabase()) {
  return connection.type === 'mssql' && connection.host && connection.database && connection.username && connection.password;
}

function updateDatabaseUi() {
  const isMssql = elements.databaseType.value === 'mssql';
  elements.mssqlConnectionPanel.classList.toggle('hidden', !isMssql);
  if (isMssql && !hasMssqlConnection()) {
    elements.mssqlConnectionStatus.textContent = 'Enter SQL Server details, then click Connect MSSQL.';
  }
}

function requireMssqlConnection() {
  if (elements.databaseType.value !== 'mssql' || hasMssqlConnection()) return true;
  setStatus('Connect MSSQL first', 'error');
  elements.mssqlConnectionStatus.textContent = 'MSSQL selected: host, database, user ID, and password are required.';
  return false;
}

function remember(role, content) {
  if (!content) return;
  sharedMemory.history.push({ role, content });
  sharedMemory.history = sharedMemory.history.slice(-16);
}

function memoryContext(message) {
  const context = [
    sharedMemory.lastQuestion ? `Last English request: ${sharedMemory.lastQuestion}` : '',
    sharedMemory.generatedSql ? `Current SQL pad:
${sharedMemory.generatedSql}` : '',
    sharedMemory.lastResult ? `Last result: ${sharedMemory.lastResult}` : '',
    message,
  ].filter(Boolean).join('\n\n');
  return context;
}

async function loadSchema(forceRefresh = false) {
  try {
    setLoading(true, 'Loading schema...');
    if (!requireMssqlConnection()) return;
    const dbType = elements.databaseType.value;
    const schema = dbType === 'mssql'
      ? await apiRequest('/api/schema', {
          method: 'POST',
          body: JSON.stringify({ database: selectedDatabase(), force_refresh: forceRefresh }),
        })
      : await apiRequest(`/api/schema?database_type=${dbType}&force_refresh=${forceRefresh}`);
    renderSchema(schema);
    setStatus('Schema loaded', 'success');
  } catch (error) {
    elements.schemaList.innerHTML = `<div class="result-error">${escapeHtml(error.message)}</div>`;
    setStatus('Schema failed', 'error');
  } finally {
    setLoading(false);
  }
}

function renderSchema(schema) {
  const tables = schema.tables || [];
  if (!tables.length) {
    elements.schemaList.textContent = elements.databaseType.value === 'mssql'
      ? 'No schema found. Check the MSSQL connection details.'
      : 'No schema found. Check POSTGRES_URL and the PostgreSQL connection.';
    return;
  }
  elements.schemaList.innerHTML = tables
    .map((table) => `
      <details class="schema-table">
        <summary>${escapeHtml(table.schema_name)}.${escapeHtml(table.table_name)}</summary>
        <ul>
          ${(table.columns || []).map((column) => `<li>${escapeHtml(column.name)} <span>${escapeHtml(column.type)}</span></li>`).join('')}
        </ul>
      </details>
    `)
    .join('');
}

async function generateSql() {
  const question = elements.englishInput.value.trim();
  if (!question) return setStatus('Enter a question', 'error');
  if (!requireMssqlConnection()) return;
  try {
    setLoading(true, 'Generating SQL...');
    const payload = await apiRequest('/api/query/generate', {
      method: 'POST',
      body: JSON.stringify({ question, execute: false, database: selectedDatabase() }),
    });
    const generatedSql = payload.generated_sql || payload.sql || '';
    elements.sqlEditor.value = generatedSql || elements.sqlEditor.value;
    sharedMemory.lastQuestion = question;
    sharedMemory.generatedSql = elements.sqlEditor.value.trim();
    remember('user', question);
    remember('assistant', generatedSql || payload.explanation || 'SQL generated.');
    appendMessage('assistant', `I drafted SQL from your request and placed it in the SQL pad. Review it, then use Verify & Run.\n\n${generatedSql}`);
    renderSuggestions({ generatedSql, explanation: payload.explanation });
    setStatus('SQL generated', 'success');
  } catch (error) {
    renderSuggestions({ error: error.message });
    setStatus('Generation failed', 'error');
  } finally {
    setLoading(false);
  }
}

async function reviewSql(error = null) {
  const query = elements.sqlEditor.value.trim();
  if (!query) return setStatus('Enter SQL first', 'error');
  if (!requireMssqlConnection()) return;
  try {
    setLoading(true, 'Reviewing SQL...');
    const review = await apiRequest('/api/query/review', {
      method: 'POST',
      body: JSON.stringify({ query, error, database: selectedDatabase() }),
    });
    if (review.corrected_sql) elements.sqlEditor.value = review.corrected_sql;
    sharedMemory.lastReview = review;
    sharedMemory.generatedSql = elements.sqlEditor.value.trim();
    renderSuggestions(review);
    setStatus('Review complete', 'success');
    return review;
  } catch (requestError) {
    renderSuggestions({ error: requestError.message });
    setStatus('Review failed', 'error');
    return null;
  } finally {
    setLoading(false);
  }
}

async function runSql() {
  const query = elements.sqlEditor.value.trim();
  if (!query) return setStatus('Enter SQL first', 'error');
  if (!requireMssqlConnection()) return;
  try {
    setLoading(true, 'Verifying SQL...');
    const review = await apiRequest('/api/query/review', {
      method: 'POST',
      body: JSON.stringify({ query, error: null, database: selectedDatabase() }),
    });
    if (review.corrected_sql) elements.sqlEditor.value = review.corrected_sql;
    sharedMemory.lastReview = review;
    sharedMemory.generatedSql = elements.sqlEditor.value.trim();
    renderSuggestions(review);
    openExecutionConfirm(elements.sqlEditor.value.trim(), review);
    setStatus('Awaiting approval', 'loading');
  } catch (error) {
    renderSuggestions({ error: error.message });
    setStatus('Verification failed', 'error');
  } finally {
    setLoading(false);
  }
}

function openExecutionConfirm(query, review = {}) {
  pendingExecution = query;
  const issues = (review.issues || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('');
  const tips = (review.optimization_tips || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('');
  elements.confirmSql.textContent = query;
  elements.confirmNotes.innerHTML = `${issues ? `<p>Issues</p><ul>${issues}</ul>` : '<p>No blocking issues reported by the agent.</p>'}${tips ? `<p>Optimization tips</p><ul>${tips}</ul>` : ''}`;
  elements.confirmOverlay.classList.remove('hidden');
  elements.confirmOverlay.setAttribute('aria-hidden', 'false');
}

function closeExecutionConfirm() {
  pendingExecution = null;
  elements.confirmOverlay.classList.add('hidden');
  elements.confirmOverlay.setAttribute('aria-hidden', 'true');
}

async function executeApprovedSql() {
  const query = pendingExecution;
  if (!query) return closeExecutionConfirm();
  if (!requireMssqlConnection()) return;
  closeExecutionConfirm();
  try {
    setLoading(true, 'Running approved query...');
    const result = await apiRequest('/api/query/execute', {
      method: 'POST',
      body: JSON.stringify({ query, database: selectedDatabase() }),
    });
    renderResult(result);
    sharedMemory.lastResult = result.success
      ? `${result.row_count || 0} row(s) returned in ${result.execution_time || 0}s`
      : `Execution failed: ${result.error || 'Unknown error'}`;
    remember('assistant', sharedMemory.lastResult);
    if (!result.success) await reviewSql(result.error);
    setStatus(result.success ? 'Query complete' : 'Query failed', result.success ? 'success' : 'error');
  } catch (error) {
    renderResult({ success: false, error: error.message });
    sharedMemory.lastResult = `Execution failed: ${error.message}`;
    setStatus('Query failed', 'error');
  } finally {
    setLoading(false);
  }
}

function renderResult(result) {
  if (!result.success) {
    elements.resultMeta.textContent = 'Execution failed';
    elements.resultArea.innerHTML = `<div class="result-error">${escapeHtml(result.error || 'Unknown error')}</div>`;
    return;
  }

  elements.resultMeta.textContent = `${result.row_count || 0} row(s) · ${result.execution_time || 0}s`;
  const columns = result.columns || [];
  const rows = result.data || [];
  if (!columns.length || !rows.length) {
    elements.resultArea.innerHTML = '<div class="empty-state">Query completed with no result rows.</div>';
    return;
  }

  elements.resultArea.innerHTML = `
    <div class="table-wrap">
      <table>
        <thead><tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join('')}</tr></thead>
        <tbody>
          ${rows.map((row) => `<tr>${columns.map((column) => `<td>${escapeHtml(row[column])}</td>`).join('')}</tr>`).join('')}
        </tbody>
      </table>
    </div>
  `;
}

function renderSuggestions(data) {
  if (data.error) {
    elements.suggestions.innerHTML = `<div class="result-error">${escapeHtml(data.error)}</div>`;
    return;
  }
  const generated = data.generatedSql ? `<p class="muted">Generated SQL</p><pre>${escapeHtml(data.generatedSql)}</pre>` : '';
  const corrected = data.corrected_sql ? `<p class="muted">Corrected SQL</p><pre>${escapeHtml(data.corrected_sql)}</pre>` : '';
  const explanation = data.explanation ? `<p>${escapeHtml(data.explanation)}</p>` : '';
  const issues = (data.issues || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('');
  const tips = (data.optimization_tips || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('');
  elements.suggestions.innerHTML = `
    ${generated}${corrected}${explanation}
    ${issues ? `<p class="muted">Issues</p><ul>${issues}</ul>` : ''}
    ${tips ? `<p class="muted">Optimization Tips</p><ul>${tips}</ul>` : ''}
  ` || 'No suggestions.';
}

async function sendChat() {
  const message = elements.chatInput.value.trim();
  if (!message) return;
  if (!requireMssqlConnection()) return;
  elements.chatInput.value = '';
  appendMessage('user', message);
  remember('user', message);
  const assistantNode = appendMessage('assistant', '');

  try {
    setLoading(true, 'AI is replying...');
    const response = await fetch(`${API_BASE_URL}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: memoryContext(message), history: sharedMemory.history, stream: true, database: selectedDatabase() }),
    });
    if (!response.ok || !response.body) throw new Error('Chat request failed');

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let fullText = '';
    let streamBuffer = '';
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      streamBuffer += decoder.decode(value, { stream: true });
      const lines = streamBuffer.split('\n');
      streamBuffer = lines.pop() || '';
      lines.forEach((line) => {
        if (!line.startsWith('data: ')) return;
        const raw = line.replace('data: ', '').trim();
        if (!raw || raw === '[DONE]') return;
        const parsed = JSON.parse(raw);
        if (parsed.error) {
          fullText = parsed.error;
          assistantNode.classList.add('error');
          assistantNode.textContent = fullText;
          setStatus('Chat failed', 'error');
          return;
        }
        fullText += parsed.token || '';
        assistantNode.textContent = fullText;
      });
    }
    if (!fullText) {
      fullText = 'No response received from the agent.';
      assistantNode.classList.add('error');
      assistantNode.textContent = fullText;
      setStatus('Chat failed', 'error');
      return;
    }
    remember('assistant', fullText);
    assistantNode.innerHTML = formatAssistantMessage(fullText);
    if (!assistantNode.classList.contains('error')) setStatus('Ready');
  } catch (error) {
    assistantNode.classList.add('error');
    assistantNode.textContent = error.message;
    setStatus('Chat failed', 'error');
  } finally {
    setLoading(false);
  }
}

function appendMessage(role, content) {
  const node = document.createElement('div');
  node.className = `message ${role}`;
  if (role === 'assistant') {
    node.innerHTML = formatAssistantMessage(content);
  } else {
    node.textContent = content;
  }
  elements.chatMessages.appendChild(node);
  elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
  return node;
}

elements.refreshSchemaBtn.addEventListener('click', () => loadSchema(true));
elements.databaseType.addEventListener('change', () => {
  updateDatabaseUi();
  remember('assistant', `Switched database to ${elements.databaseType.options[elements.databaseType.selectedIndex].text}.`);
  renderSuggestions({ generatedSql: '', explanation: `Switched to ${elements.databaseType.options[elements.databaseType.selectedIndex].text}.` });
  loadSchema(true);
});
elements.connectMssqlBtn.addEventListener('click', () => {
  const connection = readMssqlConnection();
  if (!hasMssqlConnection(connection)) {
    elements.mssqlConnectionStatus.textContent = 'Host, database, user ID, and password are required.';
    setStatus('Missing MSSQL details', 'error');
    return;
  }
  mssqlConnection = connection;
  elements.mssqlConnectionStatus.textContent = `Connected config ready for ${connection.username}@${connection.host}/${connection.database}.`;
  setStatus('MSSQL config ready', 'success');
  loadSchema(true);
});
elements.generateBtn.addEventListener('click', generateSql);
elements.fixBtn.addEventListener('click', () => reviewSql());
elements.runBtn.addEventListener('click', runSql);
elements.confirmRunBtn.addEventListener('click', executeApprovedSql);
elements.cancelRunBtn.addEventListener('click', () => {
  closeExecutionConfirm();
  setStatus('Execution cancelled');
});
elements.confirmOverlay.addEventListener('click', (event) => {
  if (event.target === elements.confirmOverlay) {
    closeExecutionConfirm();
    setStatus('Execution cancelled');
  }
});
elements.sendChatBtn.addEventListener('click', sendChat);
elements.chatInput.addEventListener('keydown', (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') sendChat();
});
elements.sqlEditor.addEventListener('keydown', (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') runSql();
});

updateDatabaseUi();
loadSchema(false);
