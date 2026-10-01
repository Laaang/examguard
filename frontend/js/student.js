/**
 * ExamGuard DNS - Student Check-in Portal Logic
 */

let ws = null;
let isStudentCheckedIn = false;

document.addEventListener('DOMContentLoaded', () => {
  loadStudentInfo();
  setupFormHandler();
  connectStudentWebSocket();
});

function connectStudentWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws`;

  ws = new WebSocket(wsUrl);

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleStudentWSMessage(msg);
    } catch (e) {
      console.error("WS error:", e);
    }
  };

  ws.onclose = () => {
    setTimeout(connectStudentWebSocket, 3000);
  };
}

function handleStudentWSMessage(msg) {
  const timerNotice = document.getElementById('checkin-timer-notice');
  const timerDisplay = document.getElementById('student-timer-display');

  if (msg.type === 'checkin_tick') {
    if (timerNotice) timerNotice.style.display = 'block';
    if (timerDisplay) timerDisplay.textContent = formatStudentTime(msg.remaining_seconds);
  } else if (msg.type === 'exam_started') {
    if (timerNotice) timerNotice.style.display = 'none';
    if (!isStudentCheckedIn) {
      const submitBtn = document.getElementById('submit-btn');
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = "Vrijeme za prijavu je isteklo!";
        submitBtn.style.background = "#64748b";
      }
      alert("Vrijeme za prijavu je isteklo! Javite se profesoru kako bi vas ručno prijavio.");
    }
  } else if (msg.type === 'classroom_reset') {
    // Resetiraj na početno stanje
    isStudentCheckedIn = false;
    const formContainer = document.getElementById('form-container');
    const successContainer = document.getElementById('success-container');
    const form = document.getElementById('student-checkin-form');
    if (form) form.reset();
    if (formContainer) formContainer.style.display = 'block';
    if (successContainer) successContainer.style.display = 'none';
    if (timerNotice) timerNotice.style.display = 'none';
    const submitBtn = document.getElementById('submit-btn');
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = "Potvrdi prijavu na ispit";
      submitBtn.style.background = "";
    }
    loadStudentInfo();
  }
}

function formatStudentTime(sec) {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

async function loadStudentInfo() {
  const stationTitleEl = document.getElementById('detected-station-title');
  const stationIpEl = document.getElementById('detected-station-ip');
  const examTitleEl = document.getElementById('portal-exam-title');
  const timerNotice = document.getElementById('checkin-timer-notice');
  const timerDisplay = document.getElementById('student-timer-display');

  try {
    const resp = await fetch('/api/student/me');
    if (!resp.ok) return;
    const data = await resp.json();

    if (stationTitleEl) stationTitleEl.textContent = data.workstation_name;
    if (stationIpEl) stationIpEl.textContent = data.ip_address;
    if (examTitleEl && data.session) {
      examTitleEl.textContent = data.session.title || "Digitalni Ispit";
    }

    if (data.session && data.session.phase === 'checkin' && data.session.checkin_remaining > 0) {
      if (timerNotice) timerNotice.style.display = 'block';
      if (timerDisplay) timerDisplay.textContent = formatStudentTime(data.session.checkin_remaining);
    }

    // Ako je student već prijavljen s ove stanice, prikaži uspješno stanje
    if (data.is_checked_in && data.full_name) {
      isStudentCheckedIn = true;
      showCheckedInState(data.full_name, data.student_id, data.workstation_name);
    }
  } catch (err) {
    console.error("Greška pri dohvaćanju podataka o stanici:", err);
  }
}

function setupFormHandler() {
  const form = document.getElementById('student-checkin-form');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const nameInput = document.getElementById('student-name');
    const idInput = document.getElementById('student-id');
    const submitBtn = document.getElementById('submit-btn');

    const fullName = nameInput.value.trim();
    const studentId = idInput.value.trim();

    if (!fullName || !studentId) {
      alert("Molimo unesite vaše ime, prezime i broj indeksa / JMBAG.");
      return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = "Prijava u tijeku...";

    try {
      const resp = await fetch('/api/student/checkin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          full_name: fullName,
          student_id: studentId
        })
      });

      if (!resp.ok) {
        throw new Error("Neuspjela prijava");
      }

      const resData = await resp.json();
      isStudentCheckedIn = true;
      const stationName = resData.student ? resData.student.workstation_name : 'Radna stanica';
      showCheckedInState(fullName, studentId, stationName);
    } catch (err) {
      alert("Došlo je do greške prilikom prijave. Molimo obratite se profesoru.");
      submitBtn.disabled = false;
      submitBtn.textContent = "Potvrdi prijavu na ispit";
    }
  });
}

function showCheckedInState(fullName, studentId, workstationName) {
  const formContainer = document.getElementById('form-container');
  const successContainer = document.getElementById('success-container');
  const confirmedNameEl = document.getElementById('confirmed-student-name');
  const confirmedStationEl = document.getElementById('confirmed-station-name');

  if (confirmedNameEl) confirmedNameEl.textContent = fullName;
  if (confirmedStationEl) confirmedStationEl.textContent = `${workstationName} (${studentId})`;

  if (formContainer) formContainer.style.display = 'none';
  if (successContainer) successContainer.style.display = 'flex';
}
