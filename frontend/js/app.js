/**
 * ExamGuard DNS - Professor Dashboard Application Logic
 */

// Application State
const state = {
  ws: null,
  session: null,
  mode: 'whitelist',
  students: new Map(), // ip -> student object
  logs: [],
  maxLogs: 150,
  filterTab: 'all', // 'all', 'checked_in', 'unregistered', 'violations'
  searchQuery: '',
  statusFilter: 'ALL',
  isScrollPaused: false,
  timerInterval: null,
  sessionSeconds: 0,
};

// Initialize Application
document.addEventListener('DOMContentLoaded', () => {
  setupUIEventListeners();
  initSoundButton();
  connectWebSocket();
  loadInitialData();
  startClock();
});

// Clock in Header
function startClock() {
  const clockEl = document.getElementById('live-clock');
  function update() {
    if (clockEl) {
      const now = new Date();
      clockEl.textContent = now.toLocaleTimeString('hr-HR');
    }
  }
  update();
  setInterval(update, 1000);
}

// UI Event Listeners
function setupUIEventListeners() {
  // Mode Buttons
  document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const mode = btn.dataset.mode;
      switchSessionMode(mode);
    });
  });

  // Filter Tabs
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.filterTab = btn.dataset.tab;
      renderClassroomGrid();
    });
  });

  // Table Search and Filter
  const searchInput = document.getElementById('search-logs');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      state.searchQuery = e.target.value.toLowerCase().trim();
      filterQueryLogs();
    });
  }

  const statusSelect = document.getElementById('filter-status');
  if (statusSelect) {
    statusSelect.addEventListener('change', (e) => {
      state.statusFilter = e.target.value;
      filterQueryLogs();
    });
  }

  // Pause Table Scroll Toggle
  const pauseScrollBtn = document.getElementById('btn-pause-scroll');
  if (pauseScrollBtn) {
    pauseScrollBtn.addEventListener('click', () => {
      state.isScrollPaused = !state.isScrollPaused;
      pauseScrollBtn.classList.toggle('active', state.isScrollPaused);
      pauseScrollBtn.title = state.isScrollPaused ? "Nastavi primanje upita" : "Pauziraj primanje upita";
      showToast(state.isScrollPaused ? "Strujanje upita pauzirano" : "Strujanje upita nastavljeno", "info");
    });
  }

  // Action Buttons: Check-in, Start Exam, Stop Exam, Reset Classroom
  const startCheckinBtn = document.getElementById('btn-start-checkin');
  if (startCheckinBtn) {
    startCheckinBtn.addEventListener('click', async () => {
      try {
        const resp = await fetch('/api/session/start-checkin', { method: 'POST' });
        if (resp.ok) {
          showToast("Faza prijave otvorena! Studenti imaju 2 minute za prijavu.", "info");
        }
      } catch (err) {
        showToast("Greška pri pokretanju faze prijave", "danger");
      }
    });
  }

  const startExamBtn = document.getElementById('btn-start-exam');
  if (startExamBtn) {
    startExamBtn.addEventListener('click', async () => {
      try {
        const resp = await fetch('/api/session/start-exam', { method: 'POST' });
        if (resp.ok) {
          showToast("Ispit je započeo! Mrežni nadzor je aktivan.", "success");
        }
      } catch (err) {
        showToast("Greška pri pokretanju ispita", "danger");
      }
    });
  }

  const stopExamBtn = document.getElementById('btn-stop-exam');
  if (stopExamBtn) {
    stopExamBtn.addEventListener('click', async () => {
      try {
        const resp = await fetch('/api/session/stop-exam', { method: 'POST' });
        if (resp.ok) {
          showToast("Ispit je zaustavljen.", "info");
        }
      } catch (err) {
        showToast("Greška pri zaustavljanju ispita", "danger");
      }
    });
  }

  const resetClassroomBtn = document.getElementById('btn-reset-classroom');
  if (resetClassroomBtn) {
    resetClassroomBtn.addEventListener('click', async () => {
      const confirmed = confirm("Jeste li sigurni da želite očistiti sve studente i pripremiti učionicu za NOVI ispit?\n\nSvi dosadašnji prijavljeni studenti bit će uklonjeni iz radne memorije.");
      if (!confirmed) return;

      try {
        const resp = await fetch('/api/session/reset-classroom', { method: 'POST' });
        if (resp.ok) {
          state.students.clear();
          state.logs = [];
          renderClassroomGrid();
          renderQueryLogTable();
          await loadInitialData();
          showToast("Učionica uspješno očišćena! Spremno za novi ispit.", "success");
        }
      } catch (err) {
        showToast("Greška pri resetiranju učionice", "danger");
      }
    });
  }

  // Export CSV Button
  const exportBtn = document.getElementById('btn-export-csv');
  if (exportBtn) {
    exportBtn.addEventListener('click', () => {
      window.location.href = '/api/logs/export';
      showToast("Preuzimanje CSV izvještaja pokrenuto...", "success");
    });
  }

  // Rules Modal
  const rulesBtn = document.getElementById('btn-rules-modal');
  const modalOverlay = document.getElementById('rules-modal');
  const modalCloseBtn = document.getElementById('modal-close-btn');

  if (rulesBtn && modalOverlay) {
    rulesBtn.addEventListener('click', () => {
      modalOverlay.classList.add('open');
      loadRules();
    });
  }

  if (modalCloseBtn && modalOverlay) {
    modalCloseBtn.addEventListener('click', () => {
      modalOverlay.classList.remove('open');
    });
  }

  if (modalOverlay) {
    modalOverlay.addEventListener('click', (e) => {
      if (e.target === modalOverlay) modalOverlay.classList.remove('open');
    });
  }

  // Add Rule Form
  const addRuleForm = document.getElementById('add-rule-form');
  if (addRuleForm) {
    addRuleForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const domainInput = document.getElementById('new-rule-domain');
      const typeSelect = document.getElementById('new-rule-type');
      if (!domainInput.value) return;

      try {
        const resp = await fetch('/api/rules', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            domain: domainInput.value.trim(),
            rule_type: typeSelect.value,
            category: 'custom'
          })
        });
        if (resp.ok) {
          showToast(`Pravilo za ${domainInput.value} dodano!`, "success");
          domainInput.value = '';
          loadRules();
        }
      } catch (err) {
        showToast("Greška pri dodavanju pravila", "danger");
      }
    });
  }
}

// Sound Button
function initSoundButton() {
  const soundBtn = document.getElementById('btn-sound-toggle');
  if (!soundBtn) return;
  
  function updateIcon() {
    soundBtn.innerHTML = window.soundManager.isMuted 
      ? `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 5L6 9H2v6h4l5 4V5z"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/></svg>`
      : `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>`;
    soundBtn.classList.toggle('active', !window.soundManager.isMuted);
  }

  updateIcon();
  soundBtn.addEventListener('click', () => {
    window.soundManager.toggleMute();
    updateIcon();
    showToast(window.soundManager.isMuted ? "Zvučni alarmi isključeni" : "Zvučni alarmi uključeni", "info");
  });
}

// WebSocket Connection
function connectWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws`;
  
  const statusPill = document.getElementById('connection-status-pill');
  const pulseDot = statusPill ? statusPill.querySelector('.pulse-dot') : null;
  const statusText = document.getElementById('connection-status-text');

  state.ws = new WebSocket(wsUrl);

  state.ws.onopen = () => {
    if (pulseDot) { pulseDot.className = 'pulse-dot online'; }
    if (statusText) statusText.textContent = 'MREŽA AKTIVNA';
  };

  state.ws.onclose = () => {
    if (pulseDot) { pulseDot.className = 'pulse-dot offline'; }
    if (statusText) statusText.textContent = 'ODSPOJENO';
    setTimeout(connectWebSocket, 3000);
  };

  state.ws.onerror = (e) => {
    console.error("WebSocket greška:", e);
  };

  state.ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleWebSocketMessage(msg);
    } catch (e) {
      console.error("Neuspjelo parsiranje WebSocket poruke:", e);
    }
  };
}

function handleWebSocketMessage(msg) {
  switch (msg.type) {
    case 'initial_state':
      if (msg.students) {
        msg.students.forEach(s => state.students.set(s.ip_address, s));
        renderClassroomGrid();
      }
      if (msg.stats) updateMetrics(msg.stats);
      break;

    case 'dns_query':
      handleIncomingDNSQuery(msg.data);
      break;

    case 'violation_alert':
      handleViolationAlert(msg.data);
      break;

    case 'student_registered':
    case 'student_checked_in':
    case 'student_updated':
      state.students.set(msg.student.ip_address, msg.student);
      renderClassroomGrid();
      if (msg.type === 'student_checked_in') {
        window.soundManager.playSuccessCheckin();
        showToast(`Učenik ${msg.student.full_name} prijavio se na ${msg.student.workstation_name}`, "success");
      }
      break;

    case 'session_update':
      state.session = msg.session;
      if (msg.session) state.mode = msg.session.mode || state.mode;
      updateSessionBanner();
      break;

    case 'checkin_tick':
      const remaining = msg.remaining_seconds;
      const formatted = formatTime(remaining);
      const checkinBtnText = document.getElementById('checkin-btn-text');
      const phaseBadge = document.getElementById('session-phase-badge');
      if (checkinBtnText) {
        checkinBtnText.textContent = `Prijava otvorena (${formatted})`;
      }
      if (phaseBadge) {
        phaseBadge.style.background = 'rgba(245, 158, 11, 0.25)';
        phaseBadge.style.color = 'var(--accent-amber)';
        phaseBadge.textContent = `PRIJAVA U TIJEKU (${formatted})`;
      }
      break;

    case 'exam_started':
      window.soundManager.playViolationAlarm();
      showToast(msg.message, "danger");
      if (state.session) {
        state.session.phase = 'active';
        state.session.is_active = 1;
      }
      updateSessionBanner();
      break;

    case 'classroom_reset':
      state.students.clear();
      state.logs = [];
      renderClassroomGrid();
      renderQueryLogTable();
      updateMetrics({ total_queries: 0, allowed_queries: 0, blocked_queries: 0, checked_in_count: 0, active_students_count: 0 });
      break;
  }
}

function formatTime(sec) {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

// Initial Data Loading
async function loadInitialData() {
  try {
    // 1. Session Info
    const sessResp = await fetch('/api/session');
    if (sessResp.ok) {
      const data = await sessResp.json();
      state.session = data.session;
      state.mode = data.mode;
      updateSessionBanner();
    }

    // 2. Students
    const studResp = await fetch('/api/students');
    if (studResp.ok) {
      const students = await studResp.json();
      students.forEach(s => state.students.set(s.ip_address, s));
      renderClassroomGrid();
    }

    // 3. Stats
    const statsResp = await fetch('/api/stats');
    if (statsResp.ok) {
      const stats = await statsResp.json();
      updateMetrics(stats);
    }

    // 4. Initial Logs
    const logsResp = await fetch('/api/logs?limit=50');
    if (logsResp.ok) {
      const logs = await logsResp.json();
      state.logs = logs;
      renderQueryLogTable();
    }
  } catch (err) {
    console.error("Greška pri dohvaćanju početnih podataka:", err);
  }
}

// Update Session Banner
function updateSessionBanner() {
  const titleEl = document.getElementById('exam-session-title');
  const statusBadge = document.getElementById('session-status-badge');
  const phaseBadge = document.getElementById('session-phase-badge');
  const checkinBtnText = document.getElementById('checkin-btn-text');

  if (titleEl && state.session) {
    titleEl.textContent = state.session.title || "Ispit";
  }

  const phase = state.session ? (state.session.phase || 'idle') : 'idle';
  const isActive = Boolean(state.session && state.session.is_active);

  if (statusBadge) {
    if (isActive) {
      statusBadge.className = 'session-badge badge-active';
      statusBadge.textContent = 'AKTIVNO';
    } else {
      statusBadge.className = 'session-badge badge-paused';
      statusBadge.textContent = 'ZAUSTAVLJENO';
    }
  }

  if (phaseBadge) {
    if (phase === 'checkin') {
      phaseBadge.style.background = 'rgba(245, 158, 11, 0.2)';
      phaseBadge.style.color = 'var(--accent-amber)';
      phaseBadge.textContent = 'PRIJAVA U TIJEKU';
    } else if (phase === 'active') {
      phaseBadge.style.background = 'rgba(16, 185, 129, 0.2)';
      phaseBadge.style.color = 'var(--accent-emerald)';
      phaseBadge.textContent = 'ISPIT U TIJEKU (Nadzor aktivan)';
      if (checkinBtnText) checkinBtnText.textContent = 'Otvori prijavu studenata (2 min)';
    } else if (phase === 'finished') {
      phaseBadge.style.background = 'rgba(148, 163, 184, 0.2)';
      phaseBadge.style.color = 'var(--text-muted)';
      phaseBadge.textContent = 'ISPIT ZAVRŠEN';
    } else {
      phaseBadge.style.background = 'rgba(99, 102, 241, 0.2)';
      phaseBadge.style.color = 'var(--accent-indigo)';
      phaseBadge.textContent = 'ČEKANJE POČETKA';
    }
  }

  // Update mode buttons
  document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.mode === state.mode);
  });
}

// Switch Session Mode
async function switchSessionMode(newMode) {
  try {
    const resp = await fetch('/api/session/mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: newMode })
    });
    if (resp.ok) {
      state.mode = newMode;
      updateSessionBanner();
      showToast(`Način rada promijenjen: ${newMode.toUpperCase()}`, "info");
    }
  } catch (e) {
    showToast("Greška pri promjeni načina rada", "danger");
  }
}

// Metrics Update
function updateMetrics(stats) {
  document.getElementById('metric-total-queries').textContent = stats.total_queries ?? 0;
  document.getElementById('metric-allowed-queries').textContent = stats.allowed_queries ?? 0;
  document.getElementById('metric-blocked-queries').textContent = stats.blocked_queries ?? 0;
  
  const checkedIn = stats.checked_in_count ?? 0;
  const totalStudents = stats.active_students_count ?? 0;
  document.getElementById('metric-students-count').textContent = `${checkedIn} / ${totalStudents}`;
}

// Render Classroom Grid
function renderClassroomGrid() {
  const container = document.getElementById('classroom-grid');
  if (!container) return;

  const studentsList = Array.from(state.students.values());

  // Filter students based on active tab
  const filtered = studentsList.filter(s => {
    if (state.filterTab === 'checked_in') return s.is_checked_in;
    if (state.filterTab === 'unregistered') return !s.is_checked_in;
    if (state.filterTab === 'violations') return (s.violations_count || 0) > 0;
    return true; // 'all'
  });

  if (filtered.length === 0) {
    container.innerHTML = `
      <div style="grid-column: 1 / -1; padding: 2.5rem; text-align: center; color: var(--text-muted); background: var(--bg-card); border-radius: var(--radius-lg); border: 1px dashed var(--border-subtle);">
        <p style="font-size: 1.125rem; font-weight: 600;">Nema radnih stanica za prikaz</p>
        <p style="font-size: 0.875rem; margin-top: 0.25rem;">Čim se učenik spoji na mrežu ili pošalje upit, stanica će se automatski pojaviti.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = filtered.map(s => {
    const isCheckedIn = Boolean(s.is_checked_in);
    const violations = s.violations_count || 0;
    let cardStateClass = isCheckedIn ? 'state-safe' : 'state-unregistered';
    if (violations > 0) cardStateClass = 'state-violation';

    const avatarInitial = isCheckedIn && s.full_name ? s.full_name.charAt(0).toUpperCase() : '?';
    const displayName = isCheckedIn ? escapeHtml(s.full_name) : 'Neprijavljen student';
    const subText = isCheckedIn ? `ID: ${escapeHtml(s.student_id || '-')}` : 'Čeka se prijava na portal';

    return `
      <div class="station-card ${cardStateClass}" id="station-${s.ip_address.replace(/[\.:]/g, '_')}">
        <div class="station-header">
          <div class="station-name-wrap">
            <span class="station-name">${escapeHtml(s.workstation_name)}</span>
          </div>
          <span class="station-ip">${escapeHtml(s.ip_address)}</span>
        </div>

        <div class="student-identity-box">
          <div class="student-avatar ${isCheckedIn ? '' : 'unregistered'}">${avatarInitial}</div>
          <div class="student-details">
            <span class="student-full-name">${displayName}</span>
            <span class="student-sub">${subText}</span>
          </div>
        </div>

        <div class="station-stats-row">
          <div class="station-stat-item">
            <span>Upiti:</span>
            <span class="badge-count badge-normal">${s.total_queries || 0}</span>
          </div>
          <div class="station-stat-item">
            <span>Prekršaji:</span>
            <span class="badge-count ${violations > 0 ? 'badge-violations' : 'badge-normal'}">${violations}</span>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

// Handle Incoming DNS Query Event
function handleIncomingDNSQuery(query) {
  // Update student query counter
  const student = state.students.get(query.client_ip);
  if (student) {
    student.total_queries = (student.total_queries || 0) + 1;
    if (query.is_violation) {
      student.violations_count = (student.violations_count || 0) + 1;
    }
    // Update workstation card UI in-place if exists
    const cardEl = document.getElementById(`station-${query.client_ip.replace(/[\.:]/g, '_')}`);
    if (cardEl) {
      const counts = cardEl.querySelectorAll('.badge-count');
      if (counts.length >= 2) {
        counts[0].textContent = student.total_queries;
        counts[1].textContent = student.violations_count;
        if (student.violations_count > 0) {
          cardEl.className = 'station-card state-violation';
          counts[1].className = 'badge-count badge-violations';
        }
      }
    }
  }

  // Update Metrics
  const totalEl = document.getElementById('metric-total-queries');
  const allowedEl = document.getElementById('metric-allowed-queries');
  const blockedEl = document.getElementById('metric-blocked-queries');

  if (totalEl) totalEl.textContent = parseInt(totalEl.textContent || 0) + 1;
  if (query.status === 'ALLOWED' && allowedEl) {
    allowedEl.textContent = parseInt(allowedEl.textContent || 0) + 1;
  } else if (query.status === 'BLOCKED' && blockedEl) {
    blockedEl.textContent = parseInt(blockedEl.textContent || 0) + 1;
  }

  // Add to logs array
  if (!state.isScrollPaused) {
    state.logs.unshift(query);
    if (state.logs.length > state.maxLogs) state.logs.pop();
    prependQueryLogRow(query);
  }
}

// Handle Violation Alert
function handleViolationAlert(data) {
  window.soundManager.playViolationAlarm();
  
  const studentName = data.student_name || data.workstation_name;
  showToast(`⛔ Pokušaj varanja! [${studentName}] zatražio: ${data.domain}`, "danger");

  // Highlight card with shake/glow effect
  const cardEl = document.getElementById(`station-${data.client_ip.replace(/[\.:]/g, '_')}`);
  if (cardEl) {
    cardEl.classList.add('state-violation');
    cardEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
}

// Render Query Log Table
function renderQueryLogTable() {
  const tbody = document.getElementById('dns-log-tbody');
  if (!tbody) return;

  const filteredLogs = filterLogsData(state.logs);
  tbody.innerHTML = filteredLogs.map(log => createLogRowHTML(log)).join('');
}

function prependQueryLogRow(log) {
  const tbody = document.getElementById('dns-log-tbody');
  if (!tbody) return;

  // Check if matches active filters
  if (!matchesFilter(log)) return;

  const rowHTML = createLogRowHTML(log);
  tbody.insertAdjacentHTML('afterbegin', rowHTML);

  // Trim excess rows from DOM
  while (tbody.children.length > state.maxLogs) {
    tbody.removeChild(tbody.lastChild);
  }
}

function createLogRowHTML(log) {
  const isViolation = log.is_violation || log.status === 'BLOCKED';
  const rowClass = isViolation ? 'row-violation' : '';

  let badgeHTML = '';
  if (log.category === 'ai_cheat') {
    badgeHTML = `<span class="badge badge-ai">🤖 AI VARANJE</span>`;
  } else if (log.status === 'BLOCKED') {
    badgeHTML = `<span class="badge badge-blocked">BLOKIRANO</span>`;
  } else {
    badgeHTML = `<span class="badge badge-allowed">DOZVOLJENO</span>`;
  }

  const timeFormatted = new Date(log.timestamp).toLocaleTimeString('hr-HR');
  const studentDisplay = log.student_name 
    ? `<strong>${escapeHtml(log.student_name)}</strong>` 
    : `<span style="color: var(--accent-amber);">Neprijavljen</span>`;

  return `
    <tr class="${rowClass}">
      <td class="time-text">${timeFormatted}</td>
      <td><strong>${escapeHtml(log.workstation_name)}</strong></td>
      <td>${studentDisplay}</td>
      <td><span class="domain-text">${escapeHtml(log.domain)}</span></td>
      <td><span style="font-family: var(--font-mono); color: var(--text-muted);">${log.query_type}</span></td>
      <td>${badgeHTML}</td>
      <td style="color: var(--text-muted); font-size: 0.8125rem;">${escapeHtml(log.reason || '-')}</td>
    </tr>
  `;
}

function filterLogsData(logs) {
  return logs.filter(matchesFilter);
}

function matchesFilter(log) {
  if (state.statusFilter !== 'ALL' && log.status !== state.statusFilter) {
    return false;
  }
  if (state.searchQuery) {
    const q = state.searchQuery;
    const matchDomain = (log.domain || '').toLowerCase().includes(q);
    const matchIp = (log.client_ip || '').toLowerCase().includes(q);
    const matchStation = (log.workstation_name || '').toLowerCase().includes(q);
    const matchStudent = (log.student_name || '').toLowerCase().includes(q);
    if (!matchDomain && !matchIp && !matchStation && !matchStudent) return false;
  }
  return true;
}

function filterQueryLogs() {
  renderQueryLogTable();
}

// Rules Manager
async function loadRules() {
  const whitelistContainer = document.getElementById('modal-whitelist-items');
  const blacklistContainer = document.getElementById('modal-blacklist-items');
  if (!whitelistContainer || !blacklistContainer) return;

  try {
    const resp = await fetch('/api/rules');
    if (!resp.ok) return;
    const rules = await resp.json();

    const whitelists = rules.filter(r => r.rule_type === 'whitelist');
    const blacklists = rules.filter(r => r.rule_type === 'blacklist');

    whitelistContainer.innerHTML = whitelists.map(r => `
      <div style="display: flex; align-items: center; justify-content: space-between; padding: 0.5rem 0.75rem; background: rgba(0,0,0,0.3); border-radius: var(--radius-sm); border: 1px solid var(--border-subtle);">
        <span style="font-family: var(--font-mono); font-size: 0.875rem;">${escapeHtml(r.domain)}</span>
        <button onclick="deleteRule(${r.id})" style="background: none; border: none; color: var(--accent-rose); cursor: pointer;">&times;</button>
      </div>
    `).join('') || '<p style="color: var(--text-muted); font-size: 0.8125rem;">Nema definiranih whitelist pravila.</p>';

    blacklistContainer.innerHTML = blacklists.map(r => `
      <div style="display: flex; align-items: center; justify-content: space-between; padding: 0.5rem 0.75rem; background: rgba(0,0,0,0.3); border-radius: var(--radius-sm); border: 1px solid var(--border-subtle);">
        <div>
          <span style="font-family: var(--font-mono); font-size: 0.875rem;">${escapeHtml(r.domain)}</span>
          <span style="font-size: 0.75rem; color: var(--text-muted); margin-left: 0.5rem;">(${r.category})</span>
        </div>
        <button onclick="deleteRule(${r.id})" style="background: none; border: none; color: var(--accent-rose); cursor: pointer;">&times;</button>
      </div>
    `).join('') || '<p style="color: var(--text-muted); font-size: 0.8125rem;">Nema definiranih blacklist pravila.</p>';
  } catch (e) {
    console.error("Greška pri učitavanju pravila:", e);
  }
}

window.deleteRule = async function(ruleId) {
  try {
    const resp = await fetch(`/api/rules/${ruleId}`, { method: 'DELETE' });
    if (resp.ok) {
      showToast("Pravilo uklonjeno", "info");
      loadRules();
    }
  } catch (e) {
    showToast("Greška pri brisanju pravila", "danger");
  }
};

// Toast Notifications
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <div style="flex: 1; font-size: 0.875rem; font-weight: 500;">${escapeHtml(message)}</div>
  `;

  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(100%)';
    setTimeout(() => toast.remove(), 300);
  }, 4500);
}

// Utility: Escape HTML
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
