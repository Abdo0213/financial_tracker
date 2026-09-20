const API_URL = 'http://localhost:8000/api';

async function fetchDashboardData() {
    try {
        const response = await fetch(`${API_URL}/data`);
        if (!response.ok) throw new Error('Network response was not ok');
        const data = await response.json();
        
        updateBudget(data.budget);
        updateGoals(data.goals);
        updateTransactions(data.transactions);
    } catch (error) {
        console.error('Error fetching data:', error);
        // Fallback for UI if backend is not running
        document.getElementById('total-balance').textContent = 'Backend Error';
    }
}

function updateBudget(budget) {
    const remaining = budget.total - budget.spent;
    const progressPercent = (budget.spent / budget.total) * 100;
    
    document.getElementById('total-balance').textContent = `${budget.currency}${remaining.toFixed(2)}`;
    document.getElementById('spent-amount').textContent = `${budget.currency}${budget.spent.toFixed(2)}`;
    document.getElementById('budget-amount').textContent = `${budget.currency}${budget.total.toFixed(2)}`;
    
    // Animate progress bar
    setTimeout(() => {
        document.getElementById('budget-progress').style.width = `${progressPercent}%`;
    }, 100);
}

function updateGoals(goals) {
    const goalsContainer = document.getElementById('goals-list');
    goalsContainer.innerHTML = '';
    
    goals.forEach(goal => {
        const progressPercent = (goal.current / goal.target) * 100;
        
        const goalEl = document.createElement('div');
        goalEl.className = 'goal-card';
        goalEl.innerHTML = `
            <div class="goal-header">
                <span class="goal-title">${goal.name}</span>
                <span class="goal-amounts">$${goal.current} / $${goal.target}</span>
            </div>
            <div class="progress-bar-bg">
                <div class="progress-bar-fill" style="width: ${progressPercent}%; background: linear-gradient(90deg, #10b981, #34d399);"></div>
            </div>
        `;
        goalsContainer.appendChild(goalEl);
    });
}

function getIconForCategory(category) {
    switch (category.toLowerCase()) {
        case 'food': return '🍔';
        case 'transportation': return '🚗';
        case 'entertainment': return '🎬';
        default: return '💰';
    }
}

function updateTransactions(transactions) {
    const txContainer = document.getElementById('transaction-list');
    txContainer.innerHTML = '';
    
    transactions.forEach(tx => {
        const date = new Date(tx.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        const icon = getIconForCategory(tx.category);
        
        const txEl = document.createElement('div');
        txEl.className = 'transaction-item';
        txEl.innerHTML = `
            <div class="transaction-info">
                <div class="transaction-icon">${icon}</div>
                <div class="transaction-details">
                    <h4>${tx.title}</h4>
                    <p>${tx.category} • ${date}</p>
                </div>
            </div>
            <div class="transaction-amount">-$${tx.amount.toFixed(2)}</div>
        `;
        txContainer.appendChild(txEl);
    });
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    fetchDashboardData();
    setupVoiceRecording();
});

// Voice Recording Logic
const COLAB_ENDPOINT = 'YOUR_COLAB_ENDPOINT_URL_HERE'; // Replace with your actual Colab URL

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
            
            // If user released the button while we were waiting for permissions (first time)
            if (!isButtonPressed) {
                return;
            }

            mediaRecorder = new MediaRecorder(persistentStream);
            audioChunks = [];

            mediaRecorder.addEventListener('dataavailable', event => {
                audioChunks.push(event.data);
            });

            mediaRecorder.addEventListener('stop', async () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                const recordingDuration = Date.now() - recordingStartTime;
                
                // Only send if the recording is longer than 500ms 
                // to prevent accidental clicks from sending empty files
                if (audioChunks.length > 0 && recordingDuration > 500) {
                    await sendAudioToColab(audioBlob);
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
            alert('Could not access microphone. Please check permissions.');
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
    
    // Handle touch events for mobile devices
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

async function sendAudioToColab(audioBlob) {
    try {
        console.log("Sending audio to Colab endpoint...");
        
        const formData = new FormData();
        // Append the file (most python endpoints expect 'file' as the form field)
        formData.append('file', audioBlob, 'voice_input.webm');

        const response = await fetch(COLAB_ENDPOINT, {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            throw new Error('Failed to send audio to Colab');
        }

        const data = await response.json();
        console.log('Received text from Colab:', data.text);
        alert('Extracted Text: ' + data.text);
        
        // NEXT STEPS: send 'data.text' to your FastAPI backend 
        // to categorize and save it to data.json
        
    } catch (error) {
        console.error('Error sending audio (endpoint might be down):', error);
        alert('Colab endpoint unreachable. Saving the audio locally instead.');
        saveAudioLocally(audioBlob);
    }
}

function saveAudioLocally(audioBlob) {
    const url = URL.createObjectURL(audioBlob);
    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = url;
    // Generate a unique filename using the current timestamp
    a.download = `voice_input_${new Date().getTime()}.webm`;
    
    document.body.appendChild(a);
    a.click();
    
    // Cleanup
    setTimeout(() => {
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
    }, 100);
}
