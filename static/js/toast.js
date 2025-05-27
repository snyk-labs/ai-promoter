export function showToast(message, type = 'info') {
    // Remove any existing toast
    const existing = document.getElementById('toast-notification');
    if (existing) existing.remove();

    // Create toast element
    const toast = document.createElement('div');
    toast.id = 'toast-notification';
    toast.textContent = message;
    toast.style.position = 'fixed';
    toast.style.bottom = '30px';
    toast.style.left = '50%';
    toast.style.transform = 'translateX(-50%)';
    toast.style.background = type === 'error' ? '#f87171' : '#4ade80';
    toast.style.color = '#fff';
    toast.style.padding = '16px 32px';
    toast.style.borderRadius = '8px';
    toast.style.boxShadow = '0 2px 8px rgba(0,0,0,0.15)';
    toast.style.zIndex = 9999;
    toast.style.fontSize = '1.1rem';
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.remove();
    }, 3000);
} 