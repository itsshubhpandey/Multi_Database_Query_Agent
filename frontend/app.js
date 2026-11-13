const API_BASE_URL = 'http://127.0.0.1:8000';

const elements = {
  conversation: document.getElementById('conversation'),
  conversationEnd: document.getElementById('conversationEnd'),
  welcome: document.getElementById('welcome'),
  messages: document.getElementById('messages'),
  chatForm: document.getElementById('chatForm'),
  chatInput: document.getElementById('chatInput'),
  sendButton: document.getElementById('sendButton'),
  connectionButton: document.getElementById('connectionButton'),
  connectionStatus: document.getElementById('connectionStatus'),
  connectionDialog: document.getElementById('connectionDialog'),
  connectionForm: document.getElementById('connectionForm'),
  closeConnectionButton: document.getElementById('closeConnectionButton'),
  cancelConnectionButton: document.getElementById('cancelConnectionButton'),
  testConnectionButton: document.getElementById('testConnectionButton'),
  databaseType: document.getElementById('databaseType'),
  connectionUri: document.getElementById('connectionUri'),
  databaseHost: document.getElementById('databaseHost'),
  databasePort: document.getElementById('databasePort'),
  databaseName: document.getElementById('databaseName'),
  databaseUsername: document.getElementById('databaseUsername'),
  databasePassword: document.getElementById('databasePassword'),
  mongoAuthSourceField: document.getElementById('mongoAuthSourceField'),
  mongoAuthSource: document.getElementById('mongoAuthSource'),
  mssqlDriverField: document.getElementById('mssqlDriverField'),
  mssqlDriver: document.getElementById('mssqlDriver'),
  connectionFeedback: document.getElementById('connectionFeedback'),
};

const DATABASE_OPTIONS = {
  postgresql: { label: 'PostgreSQL', port: 5432, uri: 'postgresql://user:password@host:5432/database' },
  mysql: { label: 'MySQL', port: 3306, uri: 'mysql://user:password@host:3306/database' },
  mssql: { label: 'SQL Server', port: 1433, uri: 'mssql+pyodbc://user:password@host/database' },
  mongodb: { label: 'MongoDB', port: 27017, uri: 'mongodb://user:password@host:27017/database' },
};

const state = {
  busy: false,
  currentSql: '',
  history: [],
  database: { type: 'postgresql' },
};

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function humanize(value) {
  return String(value || '')
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function remember(role, content) {
  if (!content) return;
  state.history.push({ role, content });
  state.history = state.history.slice(-20);
}

function setBusy(busy) {
  state.busy = busy;
  elements.sendButton.disabled = busy || !elements.chatInput.value.trim();
  elements.chatInput.disabled = busy;
  document.querySelectorAll('.starter').forEach((button) => {
    button.disabled = busy;
  });
}

function resizeComposer() {
  elements.chatInput.style.height = 'auto';
  elements.chatInput.style.height = `${Math.min(elements.chatInput.scrollHeight, 180)}px`;
  elements.sendButton.disabled = state.busy || !elements.chatInput.value.trim();
}

function scrollToLatest() {
  requestAnimationFrame(() => elements.conversationEnd.scrollIntoView({ behavior: 'smooth', block: 'end' }));
}

async function apiRequest(path, payload) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || data.error || `Request failed with status ${response.status}`);
  }
  return data;
}

function appendUserMessage(content) {
  const row = document.createElement('article');
  row.className = 'message-row user';
  const body = document.createElement('div');
  body.className = 'message-body';
  body.textContent = content;
  row.appendChild(body);
  elements.messages.appendChild(row);
  scrollToLatest();
  return row;
}

function appendAssistantMessage({ thinking = false } = {}) {
  const row = document.createElement('article');
  row.className = 'message-row assistant';
  row.innerHTML = `
    <div class="avatar" aria-hidden="true">✦</div>
    <div class="message-body">
      <div class="assistant-name">SQL Agent</div>
      <div class="assistant-content">
        ${thinking ? '<div class="thinking" aria-label="SQL Agent is working"><i></i><i></i><i></i></div>' : ''}
      </div>
    </div>
  `;
  elements.messages.appendChild(row);
  scrollToLatest();
  return row;
}

function renderTools(tools) {
  if (!tools?.length) return '';
  const pills = tools.map((tool) => `
    <span class="tool-pill ${tool.status === 'failed' ? 'failed' : ''}" title="${escapeHtml(tool.endpoint)}">
      ${tool.status === 'failed' ? '!' : '✓'} ${escapeHtml(humanize(tool.name))}
    </span>
  `).join('');
  return `
    <details class="tool-details">
      <summary>Used ${tools.length} tool${tools.length === 1 ? '' : 's'}</summary>
      <div class="tool-list">${pills}</div>
    </details>
  `;
}

function renderSql(sql) {
  if (!sql) return '';
  return `
    <section class="artifact sql-artifact">
      <header class="artifact-header">
        <span class="artifact-label">Database query</span>
        <button class="copy-button" type="button">Copy</button>
      </header>
      <pre class="sql-code">${escapeHtml(sql)}</pre>
    </section>
  `;
}

function displayValue(value) {
  if (value == null) return 'NULL';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function renderResult(result) {
  if (!result) return '';
  if (!result.success) {
    return `
      <section class="artifact">
        <header class="artifact-header"><span class="artifact-label">Query error</span></header>
        <div class="result-error">${escapeHtml(result.error || 'The query failed.')}</div>
      </section>
    `;
  }

  const columns = result.columns || [];
  const rows = result.data || [];
  const table = columns.length && rows.length
    ? `
      <div class="result-wrap">
        <table class="result-table">
          <thead><tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join('')}</tr></thead>
          <tbody>${rows.map((row) => `<tr>${columns.map((column) => `<td>${escapeHtml(displayValue(row[column]))}</td>`).join('')}</tr>`).join('')}</tbody>
        </table>
      </div>
    `
    : '<div class="result-empty">The query completed with no result rows.</div>';

  return `
    <section class="artifact">
      <header class="artifact-header"><span class="artifact-label">Query result</span></header>
      <div class="result-meta">${result.row_count || 0} row(s) · ${result.execution_time || 0}s</div>
      ${table}
    </section>
  `;
}

function renderSchema(schema) {
  if (!schema) return '';
  const tables = schema.tables || [];
  if (!tables.length) {
    return '<section class="artifact"><div class="result-empty">No user tables were found.</div></section>';
  }
  return `
    <section class="artifact">
      <header class="artifact-header"><span class="artifact-label">Database schema · ${tables.length} table${tables.length === 1 ? '' : 's'}</span></header>
      <div class="schema-grid">
        ${tables.map((table) => `
          <details class="schema-table">
            <summary>${escapeHtml(table.schema_name)}.${escapeHtml(table.table_name)}</summary>
            <ul>${(table.columns || []).map((column) => `<li><span>${escapeHtml(column.name)}</span><span>${escapeHtml(column.type)}</span></li>`).join('')}</ul>
          </details>
        `).join('')}
      </div>
    </section>
  `;
}

function renderResponse(row, response, originalQuestion) {
  if (!response.success) row.classList.add('error');
  const content = row.querySelector('.assistant-content');
  const actions = response.approval_required && response.sql
    ? `
      <div class="action-row">
        <button class="action-button approve-button" type="button">Run query <span aria-hidden="true">→</span></button>
        <button class="action-button secondary cancel-button" type="button">Cancel</button>
      </div>
      <div class="action-note">Execution requires your approval.</div>
    `
    : '';

  content.innerHTML = `
    <div class="assistant-answer">${escapeHtml(response.message || 'Done.')}</div>
    ${renderTools(response.tools)}
    ${renderSql(response.sql)}
    ${renderResult(response.result)}
    ${renderSchema(response.database_schema)}
    ${actions}
  `;

  if (response.sql) state.currentSql = response.sql;

  content.querySelector('.copy-button')?.addEventListener('click', async (event) => {
    try {
      await navigator.clipboard.writeText(response.sql);
      event.currentTarget.textContent = 'Copied';
    } catch {
      event.currentTarget.textContent = 'Copy failed';
    }
  });

  const approveButton = content.querySelector('.approve-button');
  const cancelButton = content.querySelector('.cancel-button');
  approveButton?.addEventListener('click', () => {
    approveButton.disabled = true;
    if (cancelButton) cancelButton.disabled = true;
    const note = content.querySelector('.action-note');
    if (note) note.textContent = 'Approved. Running query…';
    executeApprovedSql(response.sql, originalQuestion);
  });
  cancelButton?.addEventListener('click', () => {
    if (approveButton) approveButton.disabled = true;
    cancelButton.disabled = true;
    const note = content.querySelector('.action-note');
    if (note) note.textContent = 'Execution cancelled.';
  });
  scrollToLatest();
}

function renderRequestError(row, error) {
  renderResponse(row, {
    success: false,
    intent: 'error',
    message: error.message || 'I could not reach the agent. Check that the backend is running.',
    tools: [],
  }, '');
  elements.connectionStatus.classList.add('error');
  elements.connectionStatus.innerHTML = '<i></i> Disconnected';
}

function setConnectionStatus({ error = false } = {}) {
  const option = DATABASE_OPTIONS[state.database.type] || DATABASE_OPTIONS.postgresql;
  elements.connectionStatus.classList.toggle('error', error);
  elements.connectionStatus.innerHTML = `<i></i> ${error ? 'Connection error' : escapeHtml(option.label)}`;
}

function updateConnectionFields() {
  const type = elements.databaseType.value;
  const option = DATABASE_OPTIONS[type];
  elements.databasePort.placeholder = String(option.port);
  elements.connectionUri.placeholder = option.uri;
  elements.mongoAuthSourceField.classList.toggle('hidden', type !== 'mongodb');
  elements.mssqlDriverField.classList.toggle('hidden', type !== 'mssql');
  elements.connectionFeedback.textContent = '';
  elements.connectionFeedback.className = 'connection-feedback';
}

function readConnectionForm() {
  const type = elements.databaseType.value;
  return {
    type,
    connection_uri: elements.connectionUri.value.trim(),
    host: elements.databaseHost.value.trim(),
    port: elements.databasePort.value ? Number(elements.databasePort.value) : DATABASE_OPTIONS[type].port,
    database: elements.databaseName.value.trim(),
    username: elements.databaseUsername.value.trim(),
    password: elements.databasePassword.value,
    auth_source: elements.mongoAuthSource.value.trim() || 'admin',
    driver: elements.mssqlDriver.value.trim() || 'ODBC Driver 17 for SQL Server',
    trust_server_certificate: true,
  };
}

async function connectDatabase(event) {
  event.preventDefault();
  const database = readConnectionForm();
  elements.testConnectionButton.disabled = true;
  elements.testConnectionButton.textContent = 'Connecting…';
  elements.connectionFeedback.textContent = 'Testing the database connection…';
  elements.connectionFeedback.className = 'connection-feedback';
  try {
    const response = await apiRequest('/api/connection/test', { database, force_refresh: true });
    state.database = database;
    state.currentSql = '';
    setConnectionStatus();
    const objectName = database.type === 'mongodb' ? 'collection' : 'table';
    elements.connectionFeedback.textContent = `${response.message} Found ${response.table_count} ${objectName}${response.table_count === 1 ? '' : 's'}.`;
    elements.connectionFeedback.className = 'connection-feedback success';
    setTimeout(() => elements.connectionDialog.close(), 550);
  } catch (error) {
    elements.connectionFeedback.textContent = error.message;
    elements.connectionFeedback.className = 'connection-feedback error';
    setConnectionStatus({ error: true });
  } finally {
    elements.testConnectionButton.disabled = false;
    elements.testConnectionButton.textContent = 'Connect';
  }
}

async function submitMessage(prefilledMessage = '') {
  const message = (prefilledMessage || elements.chatInput.value).trim();
  if (!message || state.busy) return;

  elements.welcome.classList.add('hidden');
  elements.chatInput.value = '';
  resizeComposer();
  appendUserMessage(message);
  remember('user', message);
  const assistantRow = appendAssistantMessage({ thinking: true });
  setBusy(true);

  try {
    const response = await apiRequest('/api/chat', {
      message,
      history: state.history,
      current_sql: state.currentSql,
      stream: false,
      database: state.database,
    });
    renderResponse(assistantRow, response, message);
    remember('assistant', response.message);
    setConnectionStatus();
  } catch (error) {
    renderRequestError(assistantRow, error);
  } finally {
    setBusy(false);
    elements.chatInput.focus();
  }
}

async function executeApprovedSql(sql, originalQuestion) {
  if (state.busy) return;
  appendUserMessage('Run the approved query.');
  remember('user', 'Run the approved query.');
  const assistantRow = appendAssistantMessage({ thinking: true });
  setBusy(true);

  try {
    const response = await apiRequest('/api/chat', {
      message: originalQuestion || 'Execute this query and summarize the result.',
      history: state.history,
      current_sql: sql,
      approved_sql: sql,
      stream: false,
      database: state.database,
    });
    renderResponse(assistantRow, response, originalQuestion);
    remember('assistant', response.message);
    setConnectionStatus();
  } catch (error) {
    renderRequestError(assistantRow, error);
  } finally {
    setBusy(false);
    elements.chatInput.focus();
  }
}

elements.chatForm.addEventListener('submit', (event) => {
  event.preventDefault();
  submitMessage();
});

elements.chatInput.addEventListener('input', resizeComposer);
elements.chatInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    submitMessage();
  }
});

document.querySelectorAll('.starter').forEach((button) => {
  button.addEventListener('click', () => submitMessage(button.dataset.prompt || ''));
});

elements.connectionButton.addEventListener('click', () => {
  elements.databaseType.value = state.database.type;
  elements.connectionDialog.showModal();
  updateConnectionFields();
});
elements.closeConnectionButton.addEventListener('click', () => elements.connectionDialog.close());
elements.cancelConnectionButton.addEventListener('click', () => elements.connectionDialog.close());
elements.databaseType.addEventListener('change', () => {
  elements.connectionUri.value = '';
  elements.databasePort.value = '';
  updateConnectionFields();
});
elements.connectionForm.addEventListener('submit', connectDatabase);
elements.connectionDialog.addEventListener('click', (event) => {
  if (event.target === elements.connectionDialog) elements.connectionDialog.close();
});

resizeComposer();
setConnectionStatus();
elements.chatInput.focus();
