(function () {
  const modal   = document.getElementById('modalOverlay');
  const openBtn = document.getElementById('openModal');
  const closeBtn = document.getElementById('closeModal');
  const cancelBtn = document.getElementById('cancelBtn');
  const form    = document.getElementById('createRoomForm');
  const msg     = document.getElementById('formMessage');

  if (!openBtn) return;

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
        msg.textContent = `комната создана → ${json.room_name}`;
        setTimeout(() => {
          closeModal();
          addRoomCard(json.room_id, json.room_name, 1, data.max_members);
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

  function addRoomCard(roomId, roomName, currentCount = 1, maxMembers = 20) {
    const grid = document.getElementById('roomsGrid');
    const empty = grid.querySelector('.empty-state');
    if (empty) empty.remove();

    const count = grid.querySelectorAll('.room-card').length;
    const idx = String(count).padStart(2, '0');

    // Расчет класса цвета
    const ratio = currentCount / maxMembers;
    let capClass = 'cap-green';
    if (ratio >= 0.9) capClass = 'cap-red';
    else if (ratio >= 0.5) capClass = 'cap-yellow';

    const card = document.createElement('div');
    card.className = 'room-card fade-up';
    card.onclick = () => window.location = `/room/${roomId}`;

    card.innerHTML = `
      <div class="room-card-top">
        <span class="room-index">${idx}</span>
        <span class="room-status online"></span>
      </div>
      <div class="room-name">${roomName}</div>
      <div class="room-meta">
        <div class="room-meta-left">
          <span>комната</span>
          <span class="room-capacity-tag ${capClass}">
            <span class="count-value">${currentCount}</span> / ${maxMembers}
          </span>
        </div>
        <span class="arrow-right">→</span>
      </div>
    `;

    grid.appendChild(card);
  }
})();