// Configuration
const BACKEND_URL = 'http://localhost:8000';

const API_URL = `${BACKEND_URL}/api`;
const AUDIO_ENDPOINT = `${API_URL}/process_audio`;
const TEXT_ENDPOINT  = `${API_URL}/process_text`;

let currentCurrency = 'EGP';

/**
 * Currency formatting helper.
 * Formats EGP as "EGP 150.00" and $ as "$150.00".
 */
function formatCurrency(amount, currency = currentCurrency) {
    const num = Number(amount) || 0;
    if (currency === '$') {
        return `$${num.toFixed(2)}`;
    }
    return `${currency} ${num.toFixed(2)}`;
}

// ---------------------------------------------------------------------------
// Dashboard Data Fetching & Rendering
// ---------------------------------------------------------------------------

async function fetchDashboardData() {
    try {
        const response = await fetch(`${API_URL}/data`);
        if (!response.ok) throw new Error('Network response was not ok');
        const data = await response.json();
        
        if (data.budget) {
            updateBudget(data.budget);
        }
        if (Array.isArray(data.goals)) {
            updateGoals(data.goals);
        }
        if (Array.isArray(data.transactions)) {
            updateTransactions(data.transactions);
        }
    } catch (error) {
        console.error('Error fetching data:', error);
        // Fallback for UI if backend is not running
        const balanceEl = document.getElementById('total-balance');
        if (balanceEl) balanceEl.textContent = 'Backend Error';
    }
}

function updateBudget(budget) {
    if (!budget) return;
    
    currentCurrency = budget.currency || 'EGP';
    const total = Number(budget.total) || 0;
    const spent = Number(budget.spent) || 0;
    const remaining = total - spent;
    const progressPercent = total > 0 ? (spent / total) * 100 : 0;
    
    const balanceEl = document.getElementById('total-balance');
    const spentEl = document.getElementById('spent-amount');
    const budgetEl = document.getElementById('budget-amount');
    const progressEl = document.getElementById('budget-progress');

    if (balanceEl) balanceEl.textContent = formatCurrency(remaining, currentCurrency);
    if (spentEl) spentEl.textContent = formatCurrency(spent, currentCurrency);
    if (budgetEl) budgetEl.textContent = formatCurrency(total, currentCurrency);
    
    // Animate progress bar with overflow protection
    if (progressEl) {
        const displayPercent = Math.min(Math.max(progressPercent, 0), 100);
        setTimeout(() => {
            progressEl.style.width = `${displayPercent}%`;
            if (spent > total) {
                progressEl.classList.add('over-budget');
            } else {
                progressEl.classList.remove('over-budget');
            }
        }, 100);
    }
}

function updateGoals(goals) {
    const goalsContainer = document.getElementById('goals-list');
    if (!goalsContainer) return;
    goalsContainer.innerHTML = '';
    
    goals.forEach(goal => {
        const target = Number(goal.target) || 1;
        const current = Number(goal.current) || 0;
        const progressPercent = Math.min(Math.max((current / target) * 100, 0), 100);
        
        const goalEl = document.createElement('div');
        goalEl.className = 'goal-card';
        goalEl.innerHTML = `
            <div class="goal-header">
                <span class="goal-title">${goal.name}</span>
                <span class="goal-amounts">${formatCurrency(current, currentCurrency)} / ${formatCurrency(target, currentCurrency)}</span>
            </div>
            <div class="progress-bar-bg">
                <div class="progress-bar-fill" style="width: ${progressPercent}%; background: linear-gradient(90deg, #10b981, #34d399);"></div>
            </div>
        `;
        goalsContainer.appendChild(goalEl);
    });
}

/**
 * Maps all categories to relevant emojis.
 */
function getIconForCategory(category) {
    if (!category) return '💰';
    switch (category.toLowerCase().trim()) {
        case 'food': return '🍔';
        case 'transportation': return '🚗';
        case 'shopping': return '🛍️';
        case 'education': return '📚';
        case 'healthcare': return '💊';
        case 'entertainment': return '🎬';
        case 'bills': return '⚡';
        case 'housing': return '🏠';
        case 'income': return '💵';
        case 'other': return '📦';
        default: return '💰';
    }
}

function updateTransactions(transactions) {
    const txContainer = document.getElementById('transaction-list');
    if (!txContainer) return;
    txContainer.innerHTML = '';
    
    transactions.forEach(tx => {
        let dateStr = 'Recent';
        if (tx.date) {
            const parsed = new Date(tx.date);
            if (!isNaN(parsed.getTime())) {
                dateStr = parsed.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
            }
        }
        
        const icon = getIconForCategory(tx.category);
        const isIncome = (tx.transaction_type === 'income');
        const sign = isIncome ? '+' : '-';
        const amountClass = isIncome ? 'income-amount' : 'expense-amount';
        const txCurrency = tx.currency || currentCurrency;
        const formattedAmount = `${sign}${formatCurrency(tx.amount, txCurrency)}`;
        
        const txEl = document.createElement('div');
        txEl.className = 'transaction-item';
        txEl.innerHTML = `
            <div class="transaction-info">
                <div class="transaction-icon">${icon}</div>
                <div class="transaction-details">
                    <h4>${tx.title}</h4>
                    <p>${tx.category} • ${dateStr}</p>
                </div>
            </div>
            <div class="transaction-amount ${amountClass}">${formattedAmount}</div>
        `;
        txContainer.appendChild(txEl);
    });
}

// ---------------------------------------------------------------------------
// Text Input Handling
// ---------------------------------------------------------------------------

function setupTextInput() {
    const form = document.getElementById('text-input-form');
    const input = document.getElementById('text-input');
    const sendBtn = document.getElementById('send-text-btn');
    if (!form || !input) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const text = input.value.trim();
        if (!text) return;

        input.disabled = true;
        if (sendBtn) sendBtn.disabled = true;
        try {
            await sendTextToBackend(text);
            input.value = '';
        } finally {
            input.disabled = false;
            if (sendBtn) sendBtn.disabled = false;
            input.focus();
        }
    });
}

// ---------------------------------------------------------------------------
// Voice Recording Logic
// ---------------------------------------------------------------------------

function getSupportedAudioMimeType() {
    const candidateTypes = [
        'audio/webm;codecs=opus',
        'audio/webm',
        'audio/ogg;codecs=opus',
        'audio/ogg',
        'audio/mp4'
    ];
    for (const type of candidateTypes) {
        if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(type)) {
            return type;
        }
    }
    return '';
}

function setupVoiceRecording() {
    const recordBtn = document.getElementById('record-btn');
    if (!recordBtn) return;

    let mediaRecorder;
    let audioChunks = [];
    let isRecording = false;
    let isButtonPressed = false; // Track physical button state
    let persistentStream = null; // Keep the mic active to avoid re-prompting

    // Check for browser support
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        console.warn('MediaDevices API not supported.');
        return;
    }

    let recordingStartTime = 0;

    const startRecording = async () => {
        if (isButtonPressed) return; // Prevent double triggers
        isButtonPressed = true;

        try {
            if (!persistentStream) {
                persistentStream = await navigator.mediaDevices.getUserMedia({ audio: true });
            }
            
            // If user released the button while we were waiting for permissions
            if (!isButtonPressed) {
                return;
            }

            const preferredMime = getSupportedAudioMimeType();
            const options = preferredMime ? { mimeType: preferredMime } : {};
            mediaRecorder = new MediaRecorder(persistentStream, options);
            audioChunks = [];

            mediaRecorder.addEventListener('dataavailable', event => {
                audioChunks.push(event.data);
            });

            mediaRecorder.addEventListener('stop', async () => {
                const actualMime = mediaRecorder.mimeType || preferredMime || 'audio/ogg';
                const audioBlob = new Blob(audioChunks, { type: actualMime });
                const recordingDuration = Date.now() - recordingStartTime;
                
                // Determine appropriate extension from MIME type (handles Firefox ogg/ogx & Chrome webm)
                let ext = 'webm';
                if (actualMime.includes('ogg') || actualMime.includes('ogx') || actualMime.includes('opus')) {
                    ext = 'ogg';
                } else if (actualMime.includes('mp4')) {
                    ext = 'mp4';
                } else if (actualMime.includes('wav')) {
                    ext = 'wav';
                }
                const filename = `voice_input.${ext}`;

                // Only send if recording is longer than 500ms to prevent accidental clicks
                if (audioChunks.length > 0 && recordingDuration > 500) {
                    await sendAudioToColab(audioBlob, filename);
                } else {
                    console.log("Recording too short, discarding.");
                }
            });

            mediaRecorder.start();
            recordingStartTime = Date.now();
            isRecording = true;
            recordBtn.classList.add('recording');
        } catch (err) {
            console.error('Error accessing microphone:', err);
            showToast('⚠️ Could not access microphone. Please check permissions.', 'error');
            isButtonPressed = false;
            persistentStream = null;
        }
    };

    const stopRecording = () => {
        isButtonPressed = false;
        if (isRecording && mediaRecorder && mediaRecorder.state !== 'inactive') {
            mediaRecorder.stop();
            isRecording = false;
            recordBtn.classList.remove('recording');
        }
    };

    // Mouse events
    recordBtn.addEventListener('mousedown', startRecording);
    recordBtn.addEventListener('mouseup', stopRecording);
    recordBtn.addEventListener('mouseleave', stopRecording); // Stop if cursor leaves button
    
    // Touch events for mobile devices
    recordBtn.addEventListener('touchstart', (e) => {
        e.preventDefault();
        startRecording();
    });
    
    recordBtn.addEventListener('touchend', (e) => {
        e.preventDefault();
        stopRecording();
    });
    
    recordBtn.addEventListener('touchcancel', (e) => {
        e.preventDefault();
        stopRecording();
    });
}

async function sendAudioToColab(audioBlob, filename = 'voice_input.webm') {
    try {
        console.log(`Sending audio (${filename}) to backend...`);
        showToast('🎙️ Uploading and transcribing audio…', 'info');

        const formData = new FormData();
        formData.append('file', audioBlob, filename);

        const response = await fetch(AUDIO_ENDPOINT, {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            const errBody = await response.json().catch(() => ({}));
            throw new Error(errBody.detail || `Backend error ${response.status}`);
        }

        const data = await response.json();
        console.log('Backend response:', data);
        _handleWorkflowResponse(data);

    } catch (error) {
        console.error('Error sending audio (endpoint might be down):', error);
        showToast('⚠️ ' + error.message, 'error');
        saveAudioLocally(audioBlob, filename);
    }
}

// Send typed text directly through the agentic pipeline
async function sendTextToBackend(text) {
    try {
        showToast('⏳ Processing…', 'info');
        const response = await fetch(TEXT_ENDPOINT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text }),
        });

        if (!response.ok) {
            const errBody = await response.json().catch(() => ({}));
            throw new Error(errBody.detail || `Backend error ${response.status}`);
        }

        const data = await response.json();
        console.log('Backend response:', data);
        _handleWorkflowResponse(data);

    } catch (error) {
        console.error('Error sending text:', error);
        showToast('⚠️ ' + error.message, 'error');
    }
}

// Shared handler for both audio and text workflow responses
function _handleWorkflowResponse(data) {
    const intent  = data.intent  || 'UNKNOWN';
    const transcript = data.transcript || '';
    const message = data.message  || '';
    const transactions = data.transactions || [];

    if (intent === 'ADD_TRANSACTION' && transactions.length > 0) {
        // Refresh dashboard so new transactions and budget appear immediately
        fetchDashboardData();
        showToast(`✅ Saved ${transactions.length} transaction(s) — "${transcript}"`, 'success');
    } else if (intent === 'QUERY_TRANSACTIONS') {
        showToast(`ℹ️ ${message}`, 'info');
    } else if (message) {
        showToast(`ℹ️ ${message}`, 'info');
    } else {
        showToast(`✅ Intent: ${intent}`, 'success');
    }
}

// Simple toast notification (non-blocking replacement for alert())
function showToast(msg, type = 'info') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.style.cssText = [
            'position:fixed', 'bottom:24px', 'right:24px',
            'display:flex', 'flex-direction:column', 'gap:10px', 'z-index:9999'
        ].join(';');
        document.body.appendChild(container);
    }

    const colors = { success: '#22c55e', error: '#ef4444', info: '#6366f1' };
    const toast = document.createElement('div');
    toast.style.cssText = [
        `background:${colors[type] || colors.info}`,
        'color:#fff', 'padding:12px 20px', 'border-radius:12px',
        'font-size:14px', 'max-width:340px', 'box-shadow:0 4px 20px rgba(0,0,0,0.3)',
        'opacity:0', 'transition:opacity 0.3s'
    ].join(';');
    toast.textContent = msg;
    container.appendChild(toast);
    requestAnimationFrame(() => { toast.style.opacity = '1'; });
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 350);
    }, 4000);
}

function saveAudioLocally(audioBlob, filename = 'voice_input.ogg') {
    const url = URL.createObjectURL(audioBlob);
    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = url;
    a.download = filename || `voice_input_${new Date().getTime()}.ogg`;
    
    document.body.appendChild(a);
    a.click();
    
    // Cleanup
    setTimeout(() => {
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
    }, 100);
}

// ---------------------------------------------------------------------------
// Initialization
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
    fetchDashboardData();
    setupVoiceRecording();
    setupTextInput();
});
