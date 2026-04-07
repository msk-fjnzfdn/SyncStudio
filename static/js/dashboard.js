(function () {
  const modal   = document.getElementById('modalOverlay');
  const openBtn = document.getElementById('openModal');
  const closeBtn = document.getElementById('closeModal');
  const cancelBtn = document.getElementById('cancelBtn');
  const form    = document.getElementById('createRoomForm');
  const msg     = document.getElementById('formMessage');

  if (!openBtn) return; // student — no modal

  function openModal()  { modal.classList.add('open'); }
  function closeModal() { modal.classList.remove('open'); msg.textContent = ''; }

  openBtn.addEventListener('click', openModal);
  closeBtn.addEventListener('click', closeModal);
  cancelBtn.addEventListener('click', closeModal);
  modal.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(form));
    data.max_members = parseInt(data.max_members);
    msg.textContent = '';

    const submitBtn = form.querySelector('.btn-submit');
    submitBtn.disabled = true;
    submitBtn.textContent = 'создаём...';

    try {
      const res = await fetch('/room/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
        credentials: 'include',
      });
      const json = await res.json();

      if (res.ok && json.ok) {
        msg.className = 'form-message success';
        msg.textContent = `комната создана → ${json.room_id}`;
        setTimeout(() => {
          closeModal();
          addRoomCard(json.room_id);
          form.reset();
        }, 800);
      } else {
        msg.className = 'form-message error';
        msg.textContent = json.detail || 'ошибка создания';
      }
    } catch {
      msg.className = 'form-message error';
      msg.textContent = 'сетевая ошибка';
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = 'создать →';
    }
  });

  function addRoomCard(roomId) {
    const grid = document.getElementById('roomsGrid');
    const empty = grid.querySelector('.empty-state');
    if (empty) empty.remove();

    const count = grid.querySelectorAll('.room-card').length;
    const idx = String(count).padStart(2, '0');

    const card = document.createElement('div');
    card.className = 'room-card fade-up';
    card.onclick = () => window.location = `/room/${roomId}`;
    card.innerHTML = `
      <div class="room-card-top">
        <span class="room-index">${idx}</span>
        <span class="room-status online"></span>
      </div>
      <div class="room-name">${roomId}</div>
      <div class="room-meta"><span>комната</span><span class="arrow-right">→</span></div>
    `;
    grid.appendChild(card);
  }
})();
