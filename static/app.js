let currentUser = null;
let selectedSlot = null;

function navigateTo(viewId) {
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
    
    const target = document.getElementById(viewId);
    if(target) target.classList.add('active');
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
}

async function loadHospitals() {
    const res = await fetch('/api/hospitals');
    const hospitals = await res.json();
    
    const grid = document.getElementById('home-hospitals-grid');
    if(!grid) return;
    
    grid.innerHTML = hospitals.map(h => `
        <div class="card">
            <h3>${h.name}</h3>
            <p><i class="fa-solid fa-location-dot"></i> ${h.city}</p>
            <p>⭐ ${h.rating}</p>
            <button class="btn btn-outline w-100" style="margin-top:1rem" onclick="navigateTo('patient-portal')">Book Appointment</button>
        </div>
    `).join('');
}

function openLoginModal() { document.getElementById('login-modal').classList.remove('hidden'); }
function closeModal(id) { document.getElementById(id).classList.add('hidden'); }

async function handleLogin(e) {
    e.preventDefault();
    const role = document.getElementById('login-role').value;
    const email = document.getElementById('login-email').value;
    const password = document.getElementById('login-password').value;

    const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ role, email, password })
    });
    
    const data = await res.json();
    if(data.success) {
        currentUser = data.user;
        closeModal('login-modal');
        alert("Login successful!");
        location.reload();
    } else {
        alert(data.message);
    }
}

function toggleChatbot() {
    document.getElementById('chatbot-drawer').classList.toggle('hidden');
}

async function sendChatMessage() {
    const input = document.getElementById('chat-input');
    const query = input.value;
    if(!query) return;

    const body = document.getElementById('chat-messages');
    body.innerHTML += `<div style="margin-bottom:0.5rem; text-align:right"><b>You:</b> ${query}</div>`;
    input.value = '';

    const res = await fetch('/api/chatbot', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ query })
    });
    
    const data = await res.json();
    body.innerHTML += `<div style="margin-bottom:0.5rem; color:var(--primary)"><b>AI:</b> ${data.message}</div>`;
    body.scrollTop = body.scrollHeight;
}

window.onload = () => {
    loadHospitals();
};