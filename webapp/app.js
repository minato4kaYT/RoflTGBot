// ================================
// Telegram WebApp
// ================================
const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

const INIT_DATA = tg.initData;
const USER_ID = tg.initDataUnsafe?.user?.id || null;

// ================================
// THEME SYSTEM
// ================================
const THEMES = ["dark", "light", "liquid"];
let themeIndex = 0;

function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);

    const icon = document.querySelector(".theme-icon");
    if (icon) {
        icon.textContent =
            theme === "dark" ? "🌙" :
            theme === "light" ? "☀️" :
            "🫧";
    }

    if (tg.HapticFeedback) {
        tg.HapticFeedback.impactOccurred("light");
    }
}

function initTheme() {
    const saved = localStorage.getItem("theme") || "liquid";
    themeIndex = THEMES.indexOf(saved);
    if (themeIndex === -1) themeIndex = 0;
    applyTheme(THEMES[themeIndex]);
}

function toggleTheme() {
    document.body.classList.add("theme-switching");

    themeIndex = (themeIndex + 1) % THEMES.length;
    applyTheme(THEMES[themeIndex]);

    setTimeout(() => {
        document.body.classList.remove("theme-switching");
    }, 600);
}


// ================================
// STATE
// ================================
let messagesData = [];
let filteredData = [];

// ================================
// INIT
// ================================
document.addEventListener("DOMContentLoaded", async () => {
    initTheme();

    try {
        await loadData();
    } catch (e) {
        console.error("loadData failed", e);
    }

    updateStats();
    renderMessages();
    initLiveUpdates();
});

// ================================
// API LOAD
// ================================
async function loadData() {
    const res = await fetch("/api/messages", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-Telegram-Init-Data": INIT_DATA,
        },
        body: JSON.stringify({ user_id: USER_ID }),
    });

    if (!res.ok) throw new Error("API error");

    const data = await res.json();
    messagesData = data.messages || [];
    filteredData = messagesData;
}

// ================================
// LIVE UPDATES (SSE)
// ================================
function initLiveUpdates() {
    if (!USER_ID || !INIT_DATA) return;

    const es = new EventSource(
        `/api/events/stream?user_id=${USER_ID}&initData=${encodeURIComponent(INIT_DATA)}`
    );

    es.onmessage = (e) => {
        try {
            const event = JSON.parse(e.data);
            messagesData.unshift(event);
            filteredData = messagesData;
            updateStats();
            renderMessages();
        } catch (err) {
            console.error("SSE error", err);
        }
    };

    es.onerror = () => {
        es.close();
        setTimeout(initLiveUpdates, 3000);
    };
}

// ================================
// STATS
// ================================
function updateStats() {
    document.getElementById("totalMessages").textContent = messagesData.length;
    document.getElementById("editedMessages").textContent =
        messagesData.filter(m => m.type === "edited").length;
    document.getElementById("deletedMessages").textContent =
        messagesData.filter(m => m.type === "deleted").length;
}

// ================================
// RENDER
// ================================
function renderMessages() {
    const el = document.getElementById("messagesContainer");

    if (!filteredData.length) {
        el.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">📭</div>
                <p>Нет данных</p>
            </div>`;
        return;
    }

    el.innerHTML = filteredData.map(msg => {
        const date = new Date(msg.timestamp * 1000).toLocaleString("ru-RU");
        const label = msg.type === "edited" ? "✏️ Изменено" : "🗑️ Удалено";
        const cls = msg.type === "edited" ? "edited" : "deleted";

        return `
        <div class="message-item glass">
            <div class="message-header">
                <span class="message-type ${cls}">${label}</span>
                <span class="message-date">${date}</span>
            </div>
            <div class="message-content">
                <b>${escapeHtml(msg.author)}</b><br>
                ${msg.content ? escapeHtml(msg.content) : "<em>Нет текста</em>"}
            </div>
        </div>`;
    }).join("");
}

// ================================
// UTILS
// ================================
function escapeHtml(text) {
    const d = document.createElement("div");
    d.textContent = text;
    return d.innerHTML;
}


// Export data
function exportData(format) {
    const data = filteredData.length > 0 ? filteredData : messagesData;
    
    let content = '';
    let filename = '';
    let mimeType = '';
    
    switch (format) {
        case 'csv':
            content = exportToCSV(data);
            filename = `eternalmod_export_${Date.now()}.csv`;
            mimeType = 'text/csv';
            break;
        case 'json':
            content = JSON.stringify(data, null, 2);
            filename = `eternalmod_export_${Date.now()}.json`;
            mimeType = 'application/json';
            break;
        case 'txt':
            content = exportToTXT(data);
            filename = `eternalmodexport_${Date.now()}.txt`;
            mimeType = 'text/plain';
            break;
    }
    
    downloadFile(content, filename, mimeType);
    tg.HapticFeedback.notificationOccurred('success');
}

function exportToCSV(data) {
    const headers = ['Дата', 'Тип', 'Автор', 'Содержание'];
    const rows = data.map(msg => {
        const date = new Date(msg.timestamp * 1000).toLocaleString('ru-RU');
        const type = msg.type === 'edited' ? 'Изменено' : 'Удалено';
        const content = (msg.content || '').replace(/"/g, '""');
        return `"${date}","${type}","${msg.author}","${content}"`;
    });
    
    return headers.join(',') + '\n' + rows.join('\n');
}

function exportToTXT(data) {
    return data.map(msg => {
        const date = new Date(msg.timestamp * 1000).toLocaleString('ru-RU');
        const type = msg.type === 'edited' ? 'Изменено' : 'Удалено';
        return `[${date}] ${type}\nАвтор: ${msg.author}\nСодержание: ${msg.content || 'Нет текста'}\n${'='.repeat(50)}`;
    }).join('\n\n');
}

function downloadFile(content, filename, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

