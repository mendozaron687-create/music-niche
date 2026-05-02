document.addEventListener('DOMContentLoaded', () => {
    const btn = document.getElementById('sidebarCollapse');
    if (btn) btn.addEventListener('click', () => {
        document.getElementById('sidebar').classList.toggle('collapsed');
    });
    updateActiveJobs();
    setInterval(updateActiveJobs, 10000);
});

async function updateActiveJobs() {
    try {
        const res = await fetch('/api/stats');
        const stats = await res.json();
        const el = document.getElementById('activeJobCount');
        if (el) el.textContent = stats.active_jobs;
    } catch(e) {}
}

function showToast(message, type = 'info') {
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    const colors = { success: '#28a745', danger: '#dc3545', warning: '#ffc107', info: '#17a2b8' };
    const toast = document.createElement('div');
    toast.className = 'custom-toast';
    toast.style.borderLeft = `4px solid ${colors[type] || colors.info}`;
    toast.innerHTML = message;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.3s';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

function trackJob(jobId) {
    const interval = setInterval(async () => {
        try {
            const res = await fetch(`/api/job/${jobId}`);
            const data = await res.json();
            if (data.job.status === 'complete') {
                clearInterval(interval);
                const url = data.job.result?.url;
                showToast(url
                    ? `Done! <a href="${url}" target="_blank" style="color:#28a745">View on YouTube</a>`
                    : 'Video saved locally!', 'success');
                updateActiveJobs();
                setTimeout(() => location.reload(), 3000);
            } else if (data.job.status === 'failed') {
                clearInterval(interval);
                showToast(`Failed: ${data.job.error}`, 'danger');
            }
        } catch(e) { clearInterval(interval); }
    }, 3000);
}
