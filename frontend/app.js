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
document.addEventListener('DOMContentLoaded', fetchDashboardData);
