/**
 * admin.js — Полная версия управления панелью администратора
 */

// ── Состояние приложения ──
let users = [];
let searchQuery = '';
let roleFilter = 'all';
let deleteTargetId = null;
let roleChangeTarget = null;

// ── DOM Элементы ──
const tbody = document.getElementById('users-tbody');
const tableEmpty = document.getElementById('table-empty');
const searchInput = document.getElementById('search-input');
const filterBtns = document.querySelectorAll('.filter-btn');
const toast = document.getElementById('toast');

// Элементы статистики
const statTotal = document.getElementById('stat-total');
const statAdmins = document.getElementById('stat-admins');
const statStaff = document.getElementById('stat-staff');
const statUsers = document.getElementById('stat-users');

// Модальные окна
const deleteModal = document.getElementById('delete-modal');
const roleModal = document.getElementById('role-modal');

/**
 * 1. Загрузка пользователей с сервера
 */
async function loadUsers() {
  try {
    const response = await fetch('/all_users');
    if (!response.ok) throw new Error('Failed to fetch');
    const data = await response.json();

    // Преобразуем данные в массив
    users = Object.values(data).map((u, index) => ({
      id: u.id !== undefined ? u.id : index,
      name: u.username || u.name || 'Anonymous',
      email: u.email || '—',
      role: u.role || 'user',
      joined: u.created_at || u.joined
    }));

    updateStats();
    render();
  } catch (err) {
    console.error("Ошибка загрузки:", err);
    showToast("Не удалось загрузить список пользователей", "error");
  }
}

/**
 * 2. Рендеринг таблицы
 */
function render() {
  const filtered = users.filter(u => {
    const matchRole = roleFilter === 'all' || u.role === roleFilter;
    const matchSearch = !searchQuery ||
        u.name.toLowerCase().includes(searchQuery) ||
        u.email.toLowerCase().includes(searchQuery);
    return matchRole && matchSearch;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = '';
    tableEmpty.style.display = 'block';
    return;
  }

  tableEmpty.style.display = 'none';
  tbody.innerHTML = filtered.map((u, idx) => `
        <tr style="animation-delay: ${idx * 0.03}s">
            <td class="td-idx">${String(idx + 1).padStart(2, '0')}</td>
            <td>
                <div class="user-cell">
                    <div class="user-avatar">${getInitials(u.name)}</div>
                    <span class="user-name">${esc(u.name)}</span>
                </div>
            </td>
            <td class="td-email">${esc(u.email)}</td>
            <td>
                <div class="role-select-wrap">
                    <select class="role-select role-${u.role}" data-id="${u.id}">
                        <option value="admin" ${u.role === 'admin' ? 'selected' : ''}>admin</option>
                        <option value="staff" ${u.role === 'staff' ? 'selected' : ''}>staff</option>
                        <option value="user" ${u.role === 'user' ? 'selected' : ''}>user</option>
                    </select>
                    <span class="select-arrow">▼</span>
                </div>
            </td>
            <td class="td-date">${formatDate(u.joined)}</td>
            <td class="actions-cell">
                <button class="btn-delete" data-id="${u.id}">удалить</button>
            </td>
        </tr>
    `).join('');
}

/**
 * 3. Делегирование событий для таблицы (исправляет проблему появления модалок)
 */
tbody.addEventListener('change', (e) => {
  if (e.target.classList.contains('role-select')) {
    const select = e.target;
    const id = parseInt(select.dataset.id);
    const newRole = select.value;
    const user = users.find(u => u.id === id);

    if (!user || user.role === newRole) return;

    roleChangeTarget = { id, newRole, select, oldRole: user.role };
    document.getElementById('role-modal-preview').textContent = `${user.name}: ${user.role} → ${newRole}`;
    roleModal.classList.add('open');
  }
});

tbody.addEventListener('click', (e) => {
  const btn = e.target.closest('.btn-delete');
  if (btn) {
    const id = parseInt(btn.dataset.id);
    const user = users.find(u => u.id === id);
    if (user) {
      deleteTargetId = id;
      document.getElementById('modal-user-name').textContent = `${user.name} (${user.email})`;
      deleteModal.classList.add('open');
    }
  }
});

/**
 * 4. Логика подтверждения изменений (API)
 */
async function confirmRoleChange() {
  if (!roleChangeTarget) return;
  const { id, newRole, select, oldRole } = roleChangeTarget;

  try {
    const response = await fetch(`/change_user_role?target=${id}&role=${newRole}`, {
      method: 'PATCH'
    });

    if (response.ok) {
      const user = users.find(u => u.id === id);
      if (user) user.role = newRole;
      select.className = `role-select role-${newRole}`;
      updateStats();
      showToast(`Роль успешно изменена`);
    } else {
      select.value = oldRole;
      showToast("Ошибка при смене роли", "error");
    }
  } catch (err) {
    select.value = oldRole;
    showToast("Ошибка сети", "error");
  }
  roleModal.classList.remove('open');
  roleChangeTarget = null;
}

async function confirmDelete() {
  if (deleteTargetId === null) return;

  try {
    const response = await fetch(`/delete_user?target=${deleteTargetId}`, {
      method: 'DELETE'
    });

    if (response.ok) {
      users = users.filter(u => u.id !== deleteTargetId);
      render();
      updateStats();
      showToast("Пользователь удален", "error");
    } else {
      showToast("Не удалось удалить пользователя", "error");
    }
  } catch (err) {
    showToast("Ошибка сети", "error");
  }
  deleteModal.classList.remove('open');
  deleteTargetId = null;
}

function closeRoleModal() {
  if (roleChangeTarget) {
    roleChangeTarget.select.value = roleChangeTarget.oldRole;
  }
  roleModal.classList.remove('open');
  roleChangeTarget = null;
}

/**
 * 5. Вспомогательные функции
 */
function updateStats() {
  if (statTotal) statTotal.textContent = users.length;
  if (statAdmins) statAdmins.textContent = users.filter(u => u.role === 'admin').length;
  if (statStaff) statStaff.textContent = users.filter(u => u.role === 'staff').length;
  if (statUsers) statUsers.textContent = users.filter(u => u.role === 'user').length;
}

function getInitials(name) {
  return name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
}

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('ru-RU');
}

function showToast(msg, type = 'success') {
  toast.textContent = msg;
  toast.className = `toast ${type} show`;
  setTimeout(() => toast.classList.remove('show'), 3000);
}

function esc(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

/**
 * 6. Инициализация фильтров и кнопок модалок
 */
searchInput.addEventListener('input', e => {
  searchQuery = e.target.value.toLowerCase().trim();
  render();
});

filterBtns.forEach(btn => {
  btn.addEventListener('click', () => {
    filterBtns.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    roleFilter = btn.dataset.role;
    render();
  });
});

// Кнопки управления модальными окнами
document.getElementById('role-modal-confirm').onclick = confirmRoleChange;
document.getElementById('role-modal-cancel').onclick = closeRoleModal;
document.getElementById('role-modal-close').onclick = closeRoleModal;

document.getElementById('modal-confirm-btn').onclick = confirmDelete;
document.getElementById('modal-cancel-btn').onclick = () => deleteModal.classList.remove('open');
document.getElementById('modal-close-btn').onclick = () => deleteModal.classList.remove('open');

// Стартовый запуск
loadUsers();