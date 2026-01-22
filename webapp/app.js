// Telegram WebApp API
const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

// Оптимизация размеров для Telegram WebApp
if (tg && tg.viewportHeight) {
    document.documentElement.style.setProperty('--tg-viewport-height', `${tg.viewportHeight}px`);
    tg.onEvent('viewportChanged', () => {
        document.documentElement.style.setProperty('--tg-viewport-height', `${tg.viewportHeight}px`);
    });
}

// Устанавливаем цвет фона в соответствии с темой Telegram
if (tg && tg.colorScheme) {
    const isDark = tg.colorScheme === 'dark';
    if (isDark) {
        document.documentElement.setAttribute('data-theme', 'dark');
    } else {
        document.documentElement.setAttribute('data-theme', 'light');
    }
    updateThemeIcon(isDark ? 'dark' : 'light');
}

// State
let messagesData = [];
let filteredData = [];

// Theme management
function initTheme() {
    const savedTheme = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeIcon(savedTheme);
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    updateThemeIcon(newTheme);
    
    // Haptic feedback
    if (tg && tg.HapticFeedback) {
        tg.HapticFeedback.impactOccurred('light');
    }
}

function updateThemeIcon(theme) {
    const icon = document.querySelector('.theme-icon');
    if (icon) {
        icon.textContent = theme === 'dark' ? '☀️' : '🌙';
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    initTheme();
    await loadData();
    updateStats();
    renderMessages();
});

// Load data from bot API
async function loadData() {
    try {
        // Используем относительный URL для API (будет работать через прокси или на том же домене)
        const apiUrl = window.location.origin + '/api/messages';
        const response = await fetch(apiUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                user_id: tg.initDataUnsafe?.user?.id || null,
            }),
        });
        
        if (!response.ok) {
            throw new Error('Failed to load data');
        }
        
        const data = await response.json();
        messagesData = data.messages || [];
        filteredData = messagesData;
        
        document.getElementById('loading').style.display = 'none';
    } catch (error) {
        console.error('Error loading data:', error);
        document.getElementById('loading').textContent = 'Ошибка загрузки данных';
    }
}

// Update statistics
function updateStats() {
    const total = messagesData.length;
    const edited = messagesData.filter(m => m.type === 'edited').length;
    const deleted = messagesData.filter(m => m.type === 'deleted').length;
    
    document.getElementById('totalMessages').textContent = total;
    document.getElementById('editedMessages').textContent = edited;
    document.getElementById('deletedMessages').textContent = deleted;
}

// Apply filters
function applyFilters() {
    const period = document.getElementById('periodFilter').value;
    const type = document.getElementById('typeFilter').value;
    
    filteredData = messagesData.filter(msg => {
        // Period filter
        if (period !== 'all') {
            const msgDate = new Date(msg.timestamp * 1000);
            const now = new Date();
            const diff = now - msgDate;
            
            switch (period) {
                case 'today':
                    if (diff > 24 * 60 * 60 * 1000) return false;
                    break;
                case 'week':
                    if (diff > 7 * 24 * 60 * 60 * 1000) return false;
                    break;
                case 'month':
                    if (diff > 30 * 24 * 60 * 60 * 1000) return false;
                    break;
            }
        }
        
        // Type filter
        if (type !== 'all' && msg.type !== type) {
            return false;
        }
        
        return true;
    });
    
    renderMessages();
}

// Render messages
function renderMessages() {
    const container = document.getElementById('messagesContainer');
    
    if (filteredData.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">📭</div>
                <p>Нет данных для отображения</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = filteredData.map(msg => {
        const date = new Date(msg.timestamp * 1000).toLocaleString('ru-RU');
        const typeClass = msg.type === 'edited' ? 'edited' : 'deleted';
        const typeText = msg.type === 'edited' ? '✏️ Изменено' : '🗑️ Удалено';
        
        return `
            <div class="message-item">
                <div class="message-header">
                    <span class="message-type ${typeClass}">${typeText}</span>
                    <span class="message-date">${date}</span>
                </div>
                <div class="message-content">
                    <span class="message-author">${msg.author}</span><br>
                    ${msg.content ? escapeHtml(msg.content) : '<em>Нет текста</em>'}
                </div>
            </div>
        `;
    }).join('');
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
            filename = `rofl_bot_export_${Date.now()}.csv`;
            mimeType = 'text/csv';
            break;
        case 'json':
            content = JSON.stringify(data, null, 2);
            filename = `rofl_bot_export_${Date.now()}.json`;
            mimeType = 'application/json';
            break;
        case 'txt':
            content = exportToTXT(data);
            filename = `rofl_bot_export_${Date.now()}.txt`;
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

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
