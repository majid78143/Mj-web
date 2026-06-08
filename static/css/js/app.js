// CodeForge — Global JS
  // Toasts auto-dismiss
  document.querySelectorAll('.toast').forEach(t => {
    setTimeout(() => t && t.remove(), 5200);
  });

  // Mobile nav close on outside click
  document.addEventListener('click', (e) => {
    const nav = document.getElementById('mobile-nav');
    const btn = document.querySelector('.header__menu-btn');
    if (nav && btn && !nav.contains(e.target) && !btn.contains(e.target)) {
      nav.classList.remove('open');
    }
  });

  // Auto-grow textareas
  document.querySelectorAll('textarea').forEach(el => {
    el.addEventListener('input', function() {
      if (this.scrollHeight > 200 && this.scrollHeight < 600) {
        this.style.height = 'auto';
        this.style.height = this.scrollHeight + 'px';
      }
    });
  });
  
