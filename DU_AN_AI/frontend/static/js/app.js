/**
 * HỆ THỐNG QUẢN LÝ BÁN HÀNG TÍCH HỢP AI • ICTU 2026
 * Frontend Application Core Logic
 */

// Tự động nhận diện Backend API (tương thích cả khi mở bằng VS Code Live Server 5500 hoặc cổng 5000)
const API_BASE = (window.location.protocol === 'file:' || (window.location.port && window.location.port !== '5000')) 
    ? 'http://127.0.0.1:5000' 
    : '';

async function apiFetch(endpoint, options = {}) {
    const url = endpoint.startsWith('http') ? endpoint : `${API_BASE}${endpoint}`;
    try {
        const res = await fetch(url, { ...options, credentials: 'include' });
        return res;
    } catch (err) {
        console.error(`[API ERROR] Không thể gọi tới ${url}:`, err);
        showToast(`⚠️ Không thể kết nối tới Backend Flask tại ${API_BASE || 'cổng 5000'}. Hãy đảm bảo bạn đã chạy 'python app.py' hoặc tệp 'run.bat'!`, 'error');
        throw err;
    }
}

// ================= GLOBAL STATE =================
const state = {
    currentRole: 'Admin',
    currentUser: {
        id: 1,
        name: 'Nguyễn Đình Bằng',
        role: 'Admin',
        avatar: 'B'
    },
    cart: [],
    categories: [],
    products: [],
    customers: [],
    dailyChartInstance: null,
    categoryChartInstance: null,
    selectedBrand: 'all',
    brands: [],
    posPage: 1,
    posPageSize: 10,
};

// ================= INITIALIZATION =================
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    checkAuthOnLoad();
    setupEventListeners();
    setupContactFieldValidation();
    initTheme();
});

// ================= THEME SWITCHER (Sáng / Tối) =================
/**
 * Khởi tạo theme từ localStorage khi tải trang
 */
function initTheme() {
    const savedTheme = localStorage.getItem('app-theme') || 'dark';
    if (savedTheme === 'light') {
        document.body.classList.add('light-theme');
    } else {
        document.body.classList.remove('light-theme');
    }
}

/**
 * Chuyển đổi giữa Dark Theme và Light Theme
 */
function toggleTheme() {
    const body = document.body;
    const isLight = body.classList.toggle('light-theme');
    localStorage.setItem('app-theme', isLight ? 'light' : 'dark');

    // Hiện thông báo nhỏ
    const msg = isLight
        ? '🌤️ Đã chuyển sang giao diện Ban ngày'
        : '🌙 Đã chuyển sang giao diện Ban đêm';
    showToast(msg, 'info');

    // Cập nhật lại màu các biểu đồ Chart.js nếu đang hiển thị
    updateChartsForTheme(isLight);
}

/**
 * Cập nhật màu chữ cho Chart.js khi đổi theme
 */
function updateChartsForTheme(isLight) {
    const textColor = isLight ? '#64748b' : '#94a3b8';
    const gridColor = isLight ? 'rgba(30,64,120,0.07)' : 'rgba(255,255,255,0.05)';
    if (Chart && Chart.defaults) {
        Chart.defaults.color = textColor;
        Chart.defaults.borderColor = gridColor;
    }
    // Cập nhật các instance biểu đồ hiện tại
    [state.dailyChartInstance, state.categoryChartInstance].forEach(chart => {
        if (!chart) return;
        if (chart.options.scales) {
            ['x', 'y'].forEach(axis => {
                if (chart.options.scales[axis]) {
                    if (chart.options.scales[axis].ticks) chart.options.scales[axis].ticks.color = textColor;
                    if (chart.options.scales[axis].grid) chart.options.scales[axis].grid.color = gridColor;
                }
            });
        }
        if (chart.options.plugins?.legend?.labels) {
            chart.options.plugins.legend.labels.color = textColor;
        }
        chart.update('none');
    });
}


// ================= AUTHENTICATION LOGIC (UC01: ĐĂNG NHẬP / ĐĂNG KÝ) =================
function checkAuthOnLoad() {
    showAuthScreen();
    apiFetch('/api/auth/session')
        .then(async res => {
            if (!res.ok) return;
            const data = await res.json();
            if (data.success && data.user) applyUserLogin(data.user, false);
        })
        .catch(() => {});
}

function showAuthScreen() {
    const authScreen = document.getElementById('authScreen');
    const appContainer = document.getElementById('appContainer');
    if (authScreen) authScreen.style.display = 'flex';
    if (appContainer) appContainer.style.display = 'none';

    if (API_BASE) {
        const notice = document.getElementById('authNotice');
        if (notice) notice.style.display = 'block';
    }
}

function switchAuthTab(tab) {
    const loginBtn = document.getElementById('tabLoginBtn');
    const registerBtn = document.getElementById('tabRegisterBtn');
    const loginForm = document.getElementById('loginForm');
    const registerForm = document.getElementById('registerForm');

    if (tab === 'login') {
        loginBtn.classList.add('active');
        registerBtn.classList.remove('active');
        loginForm.classList.add('active');
        registerForm.classList.remove('active');
    } else {
        registerBtn.classList.add('active');
        loginBtn.classList.remove('active');
        registerForm.classList.add('active');
        loginForm.classList.remove('active');
    }
}

function fillQuickLogin(username, password) {
    document.getElementById('loginUsername').value = username;
    document.getElementById('loginPassword').value = password;
    performLogin(username, password);
}

async function performLogin(username, password) {
    const btn = document.getElementById('btnLoginSubmit');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Đang xác thực...`;
    }

    try {
        const res = await apiFetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        const data = await res.json();
        if (!data.success) {
            showToast(data.message, 'error');
            return;
        }

        applyUserLogin(data.user, true);
    } catch (e) {
        showToast("Lỗi kết nối tới máy chủ khi đăng nhập!", 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<i class="fa-solid fa-right-to-bracket"></i> ĐĂNG NHẬP VÀO HỆ THỐNG`;
        }
    }
}

function handleLoginSubmit(e) {
    e.preventDefault();
    const u = document.getElementById('loginUsername').value.trim();
    const p = document.getElementById('loginPassword').value.trim();
    if (!u || !p) {
        showToast("Vui lòng nhập đầy đủ tên đăng nhập và mật khẩu!", 'warning');
        return;
    }
    performLogin(u, p);
}

async function handleRegisterSubmit(e) {
    e.preventDefault();
    const fullnameInput = document.getElementById('regFullname');
    const phoneInput = document.getElementById('regPhone');
    const emailInput = document.getElementById('regEmail');
    const addressInput = document.getElementById('regAddress');
    const usernameInput = document.getElementById('regUsername');
    const passwordInput = document.getElementById('regPassword');
    const confirmPasswordInput = document.getElementById('regConfirmPassword');

    const fullname = fullnameInput ? fullnameInput.value.trim() : '';
    const phone = phoneInput ? phoneInput.value.trim() : '';
    const email = emailInput ? emailInput.value.trim() : '';
    const address = addressInput ? addressInput.value.trim() : '';
    const username = usernameInput ? usernameInput.value.trim() : '';
    const password = passwordInput ? passwordInput.value : '';
    const confirmPassword = confirmPasswordInput ? confirmPasswordInput.value : '';

    // Xóa trạng thái cảnh báo cũ
    [fullnameInput, phoneInput, emailInput, addressInput, usernameInput, passwordInput, confirmPasswordInput].forEach(el => {
        if (el) el.classList.remove('is-invalid');
    });

    const markError = (inputEl, message) => {
        if (inputEl) {
            inputEl.classList.add('is-invalid');
            inputEl.focus();
        }
        showToast(message, 'warning');
    };

    // 1. Ràng buộc Họ và tên: không để trống, tối thiểu 5 ký tự, chữ cái và khoảng trắng
    if (!fullname) {
        return markError(fullnameInput, "Vui lòng nhập họ và tên!");
    }
    if (fullname.length < 5) {
        return markError(fullnameInput, "Họ và tên phải có tối thiểu 5 ký tự!");
    }
    const nameRegex = /^[\p{L}\s]{5,100}$/u;
    if (!nameRegex.test(fullname)) {
        return markError(fullnameInput, "Họ và tên chỉ được chứa chữ cái và khoảng trắng, không chứa số hoặc ký tự đặc biệt!");
    }

    // 2. Ràng buộc Số điện thoại: không để trống, đúng 10 số, bắt đầu bằng 0
    if (!phone) {
        return markError(phoneInput, "Vui lòng nhập số điện thoại!");
    }
    const phoneRegex = /^0\d{9}$/;
    if (!phoneRegex.test(phone)) {
        return markError(phoneInput, "Số điện thoại phải gồm đúng 10 chữ số và bắt đầu bằng số 0 (VD: 0987654321)!");
    }

    // 3. Ràng buộc Email: không để trống, đúng định dạng
    if (!email) {
        return markError(emailInput, "Vui lòng nhập địa chỉ email!");
    }
    const emailRegex = /^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$/;
    if (!emailRegex.test(email)) {
        return markError(emailInput, "Email không đúng định dạng (VD: example@gmail.com)!");
    }

    // 4. Ràng buộc Địa chỉ: không để trống, tối thiểu 5 ký tự
    if (!address) {
        return markError(addressInput, "Vui lòng nhập địa chỉ nhận hàng!");
    }
    if (address.length < 5) {
        return markError(addressInput, "Địa chỉ phải có tối thiểu 5 ký tự (VD: Số 123 đường ABC, Hà Nội)!");
    }

    // 5. Ràng buộc Tên đăng nhập: bắt buộc nhập, tối thiểu 5 ký tự, phải có dấu, được cách
    if (!username) {
        return markError(usernameInput, "Vui lòng nhập tên đăng nhập!");
    }
    const cleanUsername = username.replace(/\s+/g, ' ');
    if (cleanUsername.length < 5) {
        return markError(usernameInput, "Tên đăng nhập phải có tối thiểu 5 ký tự!");
    }
    if (cleanUsername.length > 50) {
        return markError(usernameInput, "Tên đăng nhập không được vượt quá 50 ký tự!");
    }
    const usernameValidChars = /^[\p{L}\p{N}_\s]+$/u;
    if (!usernameValidChars.test(cleanUsername)) {
        return markError(usernameInput, "Tên đăng nhập chỉ gồm chữ cái tiếng Việt, chữ số, khoảng trắng và dấu gạch dưới (_), không chứa ký tự đặc biệt!");
    }
    const vietnameseAccentRegex = /[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴĐ\u0300-\u036f]/;
    if (!vietnameseAccentRegex.test(cleanUsername.normalize('NFC'))) {
        return markError(usernameInput, "Tên đăng nhập phải có dấu tiếng Việt (ví dụ: Nguyễn Văn A, Bằng 206, Anh Tuấn...)!");
    }

    // 6. Ràng buộc Mật khẩu: không để trống, tối thiểu 6 ký tự, không khoảng trắng
    if (!password) {
        return markError(passwordInput, "Vui lòng nhập mật khẩu!");
    }
    if (password.length < 6) {
        return markError(passwordInput, "Mật khẩu phải có ít nhất 6 ký tự!");
    }
    if (/\s/.test(password)) {
        return markError(passwordInput, "Mật khẩu không được chứa khoảng trắng!");
    }

    // 7. Ràng buộc Xác thực lại mật khẩu: không để trống, trùng khớp với mật khẩu
    if (!confirmPassword) {
        return markError(confirmPasswordInput, "Vui lòng xác thực lại mật khẩu!");
    }
    if (confirmPassword !== password) {
        return markError(confirmPasswordInput, "Mật khẩu xác thực lại không trùng khớp với mật khẩu đã nhập!");
    }

    const btn = document.getElementById('btnRegisterSubmit');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Đang tạo tài khoản...`;
    }

    try {
        const res = await apiFetch('/api/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                fullname,
                phone,
                email,
                address,
                username: cleanUsername,
                password,
                confirm_password: confirmPassword
            })
        });
        const data = await res.json();
        if (!data.success) {
            showToast(data.message, 'error');
            return;
        }

        showToast(data.message || "Đăng ký thành công! Đang tự động đăng nhập...", 'success');
        applyUserLogin(data.user, true);
    } catch (e) {
        showToast("Lỗi kết nối khi đăng ký tài khoản!", 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<i class="fa-solid fa-user-plus"></i> ĐĂNG KÝ TÀI KHOẢN MỚI`;
        }
    }
}

function applyUserLogin(user, showWelcome = false) {
    state.currentUser = {
        id: user.UserID,
        name: user.FullName,
        role: user.Role,
        avatar: user.FullName ? user.FullName[0].toUpperCase() : 'U'
    };
    state.currentRole = user.Role;

    // Hide auth screen, show main app
    const authScreen = document.getElementById('authScreen');
    const appContainer = document.getElementById('appContainer');
    if (authScreen) authScreen.style.display = 'none';
    if (appContainer) appContainer.style.display = 'flex';

    // Update Topbar & Sidebar info
    document.getElementById('sidebarRoleText').textContent = user.Role;
    document.getElementById('topbarUserName').textContent = user.FullName;
    document.getElementById('topbarUserRole').textContent = `${user.Role} (UserID: #${user.UserID})`;
    document.getElementById('topbarAvatar').textContent = state.currentUser.avatar;

    const roleSelect = document.getElementById('roleSelect');
    if (roleSelect) roleSelect.value = user.Role;

    applyRolePermissions(user.Role);

    // Load only data allowed for the authenticated role.
    const allowedPages = {
        Admin: ['dashboard', 'pos', 'products', 'customers', 'imports', 'invoices', 'reports', 'users'],
        Manager: ['dashboard', 'pos', 'products', 'customers', 'imports', 'invoices', 'reports', 'ai-hub'],
        Staff: ['products', 'customers', 'pos', 'imports', 'invoices', 'ai-hub'],
        Customer: ['products', 'pos', 'ai-hub']
    }[user.Role] || [];
    if (allowedPages.includes('dashboard')) loadDashboardData();
    loadCategories();
    if (allowedPages.includes('products')) loadProducts();
    if (allowedPages.includes('customers')) loadCustomers();
    if (allowedPages.includes('invoices')) loadInvoices();
    if (allowedPages.includes('imports')) loadImports();
    if (user.Role === 'Admin') loadSettingsStatus();

    if (showWelcome) {
        showToast(`Xin chào ${user.FullName}! Bạn đã đăng nhập với vai trò ${user.Role}.`, 'success');
    }
}

async function handleLogout() {
    if (!confirm("Bạn có chắc chắn muốn đăng xuất khỏi hệ thống?")) return;
    try {
        await apiFetch('/api/auth/logout', { method: 'POST' });
    } catch (e) {
        // Still clear the local UI when the backend is unavailable.
    }
    state.currentUser = null;
    state.currentRole = null;
    clearCart();

    const authScreen = document.getElementById('authScreen');
    const appContainer = document.getElementById('appContainer');
    if (authScreen) authScreen.style.display = 'flex';
    if (appContainer) appContainer.style.display = 'none';

    // Clear form fields
    document.getElementById('loginUsername').value = '';
    document.getElementById('loginPassword').value = '';
    switchAuthTab('login');

    showToast("Đã đăng xuất khỏi hệ thống thành công!", 'info');
}

// ================= UTILITIES =================
function formatVND(amount) {
    return new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(amount || 0);
}

function validateContactInputs(phone, email, phoneRequired = false, emailRequired = false) {
    if (phoneRequired && !phone) return 'Vui lòng nhập số điện thoại.';
    if (emailRequired && !email) return 'Vui lòng nhập email.';
    if (phone && !/^\d{10}$/.test(phone)) return 'Số điện thoại phải gồm đúng 10 chữ số.';
    if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return 'Email không đúng định dạng, ví dụ: example@gmail.com.';
    return '';
}

function setupContactFieldValidation() {
    ['regPhone', 'cFormPhone', 'userFormPhone'].forEach(id => {
        const input = document.getElementById(id);
        if (!input) return;
        input.addEventListener('input', () => {
            input.value = input.value.replace(/\D/g, '').slice(0, 10);
            const isValid = input.value.length === 10 && input.value.startsWith('0');
            input.setCustomValidity(input.value && !isValid ? 'Số điện thoại phải gồm đúng 10 chữ số và bắt đầu bằng số 0.' : '');
            if (isValid) input.classList.remove('is-invalid');
        });
    });

    ['regEmail', 'cFormEmail', 'userFormEmail'].forEach(id => {
        const input = document.getElementById(id);
        if (!input) return;
        input.addEventListener('input', () => {
            const isValid = /^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$/.test(input.value.trim());
            input.setCustomValidity(input.value && !isValid ? 'Email không đúng định dạng.' : '');
            if (isValid) input.classList.remove('is-invalid');
        });
    });

    // Real-time validation & gỡ bỏ viền lỗi khi người dùng chỉnh sửa thông tin đăng ký
    const regFullname = document.getElementById('regFullname');
    if (regFullname) {
        regFullname.addEventListener('input', () => {
            if (regFullname.value.trim().length >= 5 && /^[\p{L}\s]{5,100}$/u.test(regFullname.value.trim())) {
                regFullname.classList.remove('is-invalid');
            }
        });
    }

    const regAddress = document.getElementById('regAddress');
    if (regAddress) {
        regAddress.addEventListener('input', () => {
            if (regAddress.value.trim().length >= 5) {
                regAddress.classList.remove('is-invalid');
            }
        });
    }

    const regUsername = document.getElementById('regUsername');
    if (regUsername) {
        regUsername.addEventListener('input', () => {
            const val = regUsername.value.trim().replace(/\s+/g, ' ');
            const hasAccent = /[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴĐ\u0300-\u036f]/.test(val.normalize('NFC'));
            const isValidChars = /^[\p{L}\p{N}_\s]{5,50}$/u.test(val);
            if (val.length >= 5 && hasAccent && isValidChars) {
                regUsername.classList.remove('is-invalid');
            }
        });
    }

    const regPassword = document.getElementById('regPassword');
    const regConfirmPassword = document.getElementById('regConfirmPassword');

    if (regPassword) {
        regPassword.addEventListener('input', () => {
            if (regPassword.value.length >= 6 && !/\s/.test(regPassword.value)) {
                regPassword.classList.remove('is-invalid');
            }
            if (regConfirmPassword && regConfirmPassword.value) {
                if (regConfirmPassword.value === regPassword.value) {
                    regConfirmPassword.classList.remove('is-invalid');
                }
            }
        });
    }

    if (regConfirmPassword) {
        regConfirmPassword.addEventListener('input', () => {
            if (regPassword && regConfirmPassword.value === regPassword.value) {
                regConfirmPassword.classList.remove('is-invalid');
            }
        });
    }
}

function showToast(message, type = 'success') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    const icon = type === 'success' ? 'fa-circle-check' : (type === 'error' ? 'fa-triangle-exclamation' : 'fa-circle-info');
    toast.innerHTML = `<i class="fa-solid ${icon}"></i> <span>${message}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}

function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.classList.add('active');
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.classList.remove('active');
}

function togglePasswordVisibility(inputId, button) {
    const input = document.getElementById(inputId);
    if (!input) return;
    const isPassword = input.type === 'password';
    input.type = isPassword ? 'text' : 'password';
    const icon = button.querySelector('i');
    if (icon) icon.className = `fa-solid ${isPassword ? 'fa-eye-slash' : 'fa-eye'}`;
}

// ================= ROLE PERMISSIONS (UC01, UC12) =================
function applyRolePermissions(role) {
    const pageAccess = {
        Admin: ['dashboard', 'pos', 'products', 'customers', 'imports', 'invoices', 'reports', 'users'],
        Manager: ['dashboard', 'pos', 'products', 'customers', 'imports', 'invoices', 'reports', 'ai-hub'],
        Staff: ['products', 'customers', 'pos', 'imports', 'invoices', 'ai-hub'],
        Customer: ['products', 'pos', 'ai-hub']
    };
    const allowedPages = pageAccess[role] || [];
    document.querySelectorAll('.sidebar-nav .nav-item').forEach(item => {
        item.style.display = allowedPages.includes(item.dataset.page) ? '' : 'none';
    });
    document.querySelectorAll('.page-view').forEach(page => {
        const pageId = page.id.replace('page-', '');
        page.style.display = allowedPages.includes(pageId) ? '' : 'none';
    });
    document.querySelectorAll('.admin-only').forEach(el => {
        el.style.display = role === 'Admin' ? '' : 'none';
    });
    document.querySelectorAll('.manager-only').forEach(el => {
        el.style.display = role === 'Manager' ? '' : 'none';
    });
    ['btn-tab-revenue', 'tab-revenue', 'btn-tab-qa', 'tab-qa'].forEach(id => {
        const element = document.getElementById(id);
        if (element) element.style.display = role === 'Manager' ? '' : 'none';
    });

    const advisorAllowed = ['Manager', 'Staff', 'Customer'].includes(role);
    ['btn-tab-advisor', 'tab-advisor', 'nav-ai-hub'].forEach(id => {
        const element = document.getElementById(id);
        if (element) element.style.display = advisorAllowed ? '' : 'none';
    });
    const productWriteAccess = ['Admin', 'Manager', 'Staff'].includes(role);
    const customerWriteAccess = ['Admin', 'Manager'].includes(role);
    const addProductButton = document.getElementById('addProductBtn');
    const addCustomerButton = document.getElementById('addCustomerBtn');
    if (addProductButton) addProductButton.style.display = productWriteAccess ? '' : 'none';
    if (addCustomerButton) addCustomerButton.style.display = customerWriteAccess ? '' : 'none';
    const addImport = document.getElementById('addImportBtn');
    if (addImport) addImport.style.display = ['Admin', 'Manager', 'Staff'].includes(role) ? '' : 'none';
    const dashboardExport = document.getElementById('dashboardExportCsv');
    if (dashboardExport) dashboardExport.style.display = ['Admin', 'Manager'].includes(role) ? '' : 'none';
    const dashboardAi = document.getElementById('dashboardAiRevenue');
    if (dashboardAi) dashboardAi.style.display = role === 'Manager' ? '' : 'none';
    const customerMode = role === 'Customer';
    const customerSelector = document.getElementById('cartCustomerSelector');
    const discountRow = document.getElementById('cartDiscountRow');
    const checkoutButton = document.getElementById('posCheckoutBtn');
    if (customerSelector) customerSelector.style.display = customerMode ? 'none' : '';
    if (discountRow) discountRow.style.display = customerMode ? 'none' : '';
    if (checkoutButton && customerMode) {
        checkoutButton.innerHTML = '<i class="fa-solid fa-bag-shopping"></i> MUA HÀNG & THANH TOÁN';
    }
    const productsTitle = document.getElementById('productsPageTitle');
    const productsSubtitle = document.getElementById('productsPageSubtitle');
    const productCostHeader = document.getElementById('productCostHeader');
    const productActionHeader = document.getElementById('productActionHeader');
    if (productsTitle) productsTitle.textContent = customerMode ? 'Sản phẩm & Tồn kho đang bán' : 'Quản lý Danh mục & Sản phẩm Laptop';
    if (productsSubtitle) productsSubtitle.textContent = customerMode ? 'Tra cứu cấu hình, giá bán và số lượng sản phẩm hiện có để lựa chọn mua hàng.' : 'Theo dõi thông số kỹ thuật, giá thành, cấu hình và số lượng tồn kho thực tế.';
    if (productCostHeader) productCostHeader.style.display = customerMode ? 'none' : '';
    if (productActionHeader) productActionHeader.style.display = customerMode ? 'none' : '';

    const activePage = document.querySelector('.page-view.active')?.id.replace('page-', '');
    if (!allowedPages.includes(activePage)) switchPage(allowedPages[0] || 'products');
}

// ================= NAVIGATION =================
function initNavigation() {
    const navItems = document.querySelectorAll('.sidebar-nav .nav-item');
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const pageId = item.getAttribute('data-page');
            switchPage(pageId);
        });
    });

    // Mobile menu toggle
    const sidebar = document.getElementById('sidebar');
    const appContainer = document.getElementById('appContainer');
    const toggleButtons = document.querySelectorAll('#menuToggleBtn, #sidebarToggleBtn');
    if (toggleButtons.length && sidebar) {
        const toggleSidebar = () => {
            if (window.matchMedia('(max-width: 1024px)').matches) {
                sidebar.classList.toggle('active');
            } else if (appContainer) {
                appContainer.classList.toggle('sidebar-collapsed');
            }
        };
        toggleButtons.forEach(button => button.addEventListener('click', toggleSidebar));
    }
}

function switchPage(pageId, subTabId = null) {
    const allowedPages = {
        Admin: ['dashboard', 'pos', 'products', 'customers', 'imports', 'invoices', 'reports', 'users'],
        Manager: ['dashboard', 'pos', 'products', 'customers', 'imports', 'invoices', 'reports', 'ai-hub'],
        Staff: ['products', 'customers', 'pos', 'imports', 'invoices', 'ai-hub'],
        Customer: ['products', 'pos', 'ai-hub']
    }[state.currentRole] || [];
    if (!allowedPages.includes(pageId)) {
        showToast('Bạn không có quyền truy cập chức năng này.', 'error');
        return;
    }
    document.querySelectorAll('.page-view').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.sidebar-nav .nav-item').forEach(n => n.classList.remove('active'));

    const targetPage = document.getElementById(`page-${pageId}`);
    const targetNav = document.getElementById(`nav-${pageId}`);

    if (targetPage) targetPage.classList.add('active');
    if (targetNav) targetNav.classList.add('active');

    // Update breadcrumb
    const pageNames = {
        'dashboard': 'Tổng quan (KPI)',
        'pos': 'Bán hàng POS Counter',
        'products': 'Quản lý Sản phẩm & Kho',
        'customers': 'Quản lý Khách hàng',
        'imports': 'Nhập hàng & Nhà cung cấp',
        'invoices': 'Lịch sử Hóa đơn',
        'reports': 'Thống kê & Báo cáo',
        'ai-hub': 'Trợ lý AI Bán hàng',
        'users': 'Quản trị Người dùng & Phân quyền'
    };
    document.getElementById('breadcrumbCurrent').textContent = pageNames[pageId] || pageId;

    if (pageId === 'dashboard') loadDashboardData();
    if (pageId === 'pos') renderPosProducts();
    if (pageId === 'products') loadProducts();
    if (pageId === 'customers') loadCustomers();
    if (pageId === 'invoices') loadInvoices();
    if (pageId === 'reports') loadReportData();
    if (pageId === 'imports') loadImports();
    if (pageId === 'users') loadUsers();

    if (pageId === 'ai-hub' && subTabId) {
        switchAiTab(subTabId);
    }
}

function initializeReportFilters() {
    const today = new Date().toISOString().slice(0, 10);
    const dateInput = document.getElementById('reportDate');
    if (dateInput && !dateInput.value) dateInput.value = today;
    const fromInput = document.getElementById('reportFrom');
    const toInput = document.getElementById('reportTo');
    if (fromInput && !fromInput.value) fromInput.value = `${today.slice(0, 8)}01`;
    if (toInput && !toInput.value) toInput.value = today;
    updateCustomReportDates();
}

function updateCustomReportDates() {
    const period = document.getElementById('reportPeriod');
    document.querySelectorAll('.report-custom-date').forEach(input => {
        input.style.display = period && period.value === 'custom' ? 'flex' : 'none';
    });
}

function getReportQueryString() {
    initializeReportFilters();
    const params = new URLSearchParams({
        period: document.getElementById('reportPeriod')?.value || 'month',
        date: document.getElementById('reportDate')?.value || ''
    });
    if (params.get('period') === 'custom') {
        params.set('from', document.getElementById('reportFrom')?.value || '');
        params.set('to', document.getElementById('reportTo')?.value || '');
    }
    return params.toString();
}

async function loadReportData() {
    initializeReportFilters();
    updateCustomReportDates();
    try {
        const res = await apiFetch(`/api/reports/data?${getReportQueryString()}`);
        const data = await res.json();
        if (!data.success) throw new Error(data.message || 'Không tải được báo cáo');
        document.getElementById('reportRevenue').textContent = formatVND(data.summary.Revenue);
        document.getElementById('reportInvoiceCount').textContent = `${data.summary.InvoiceCount} đơn`;
        document.getElementById('reportProductCount').textContent = `${data.invoices.reduce((sum, row) => sum + Number(row.TotalItems || 0), 0)} món`;
        document.getElementById('reportRowCount').textContent = `${data.invoices.length} giao dịch`;
        document.getElementById('reportPeriodLabel').textContent = data.from ? `${data.from} đến ${data.to}` : 'Toàn bộ thời gian';
        renderReportInvoices(data.invoices);
    } catch (err) {
        console.error('Lỗi tải báo cáo:', err);
        showToast('Không thể tải dữ liệu thống kê!', 'error');
    }
}

function renderReportInvoices(invoices) {
    const tbody = document.getElementById('reportInvoicesTableBody');
    if (!tbody) return;
    if (!invoices.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center py-4 text-muted">Không có giao dịch trong kỳ này</td></tr>';
        return;
    }
    tbody.innerHTML = invoices.map(row => `
        <tr>
            <td><strong>${row.InvoiceCode}</strong></td>
            <td>${row.InvoiceDate}</td>
            <td>${row.CustomerName}</td>
            <td>${row.StaffName}</td>
            <td>${row.TotalItems} món</td>
            <td><strong class="text-success">${formatVND(row.TotalAmount)}</strong></td>
            <td><span class="badge-pill">${row.PaymentMethod || 'Khác'}</span></td>
        </tr>
    `).join('');
}

function exportReportFile(format) {
    const query = getReportQueryString();
    window.location.href = `${API_BASE}/api/reports/export/${format}?${query}`;
    showToast(`Đang tạo báo cáo ${format.toUpperCase()}...`, 'info');
}

// ================= DASHBOARD & CHARTS (UC07) =================
async function loadDashboardData() {
    try {
        const res = await apiFetch('/api/reports/dashboard');
        const data = await res.json();
        if (!data.success) return;

        const kpis = data.kpis;
        document.getElementById('kpiTotalRevenue').textContent = formatVND(kpis.totalRevenue);
        document.getElementById('kpiTotalInvoices').textContent = `${kpis.totalInvoices} đơn`;
        document.getElementById('kpiTotalProducts').textContent = `${kpis.totalProducts} máy`;
        document.getElementById('kpiLowStock').textContent = `${kpis.lowStockCount} mặt hàng`;
        document.getElementById('lowStockBadge').textContent = kpis.lowStockCount;

        // Daily Revenue Chart
        renderDailyChart(data.dailyChart);

        // Category Doughnut Chart
        renderCategoryChart(data.categoryChart);

        // Top Sellers Table
        renderTopSellersTable(data.topSellers);
    } catch (err) {
        console.error("Lỗi tải dữ liệu Dashboard:", err);
    }
}

function renderDailyChart(chartData) {
    const ctx = document.getElementById('dailyRevenueChart').getContext('2d');
    if (state.dailyChartInstance) state.dailyChartInstance.destroy();

    state.dailyChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: chartData.labels,
            datasets: [{
                label: 'Doanh thu (VNĐ)',
                data: chartData.values,
                borderColor: '#3b82f6',
                backgroundColor: 'rgba(59, 130, 246, 0.15)',
                borderWidth: 3,
                tension: 0.35,
                fill: true,
                pointBackgroundColor: '#60a5fa',
                pointRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (context) => `Doanh thu: ${formatVND(context.parsed.y)}`
                    }
                }
            },
            scales: {
                x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8' } },
                y: {
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: {
                        color: '#94a3b8',
                        callback: (val) => (val / 1000000).toFixed(0) + 'M'
                    }
                }
            }
        }
    });
}

const REVENUE_PERIOD_TITLES = {
    '7days': 'Biểu đồ Doanh thu 7 ngày gần nhất',
    'week':  'Biểu đồ Doanh thu theo Tuần (8 tuần gần nhất)',
    'month': 'Biểu đồ Doanh thu theo Tháng (12 tháng gần nhất)',
    'quarter': 'Biểu đồ Doanh thu theo Quý (8 quý gần nhất)',
    'year':  'Biểu đồ Doanh thu theo Năm (5 năm gần nhất)'
};

async function switchRevenuePeriod(period, btnEl) {
    // Cập nhật trạng thái active của nút
    document.querySelectorAll('.rev-tab-btn').forEach(b => b.classList.remove('active'));
    btnEl.classList.add('active');

    // Cập nhật tiêu đề
    const titleEl = document.getElementById('revenueChartTitle');
    if (titleEl) titleEl.textContent = REVENUE_PERIOD_TITLES[period] || 'Biểu đồ Doanh thu';

    try {
        const res = await apiFetch(`/api/reports/revenue-chart?period=${period}`);
        const data = await res.json();
        if (data.success) {
            renderDailyChart({ labels: data.labels, values: data.values });
        }
    } catch (err) {
        console.error('Lỗi tải biểu đồ doanh thu:', err);
    }
}


function renderCategoryChart(chartData) {
    const ctx = document.getElementById('categoryChart').getContext('2d');
    if (state.categoryChartInstance) state.categoryChartInstance.destroy();

    state.categoryChartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: chartData.labels,
            datasets: [{
                data: chartData.values,
                backgroundColor: chartData.labels.map(brand => getBrandColor(brand, chartData.labels)),
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: '#e2e8f0', boxWidth: 12, padding: 12, font: { size: 11 } }
                },
                tooltip: {
                    callbacks: {
                        label: (context) => {
                            const values = context.dataset.data;
                            const total = values.reduce((sum, value) => sum + value, 0);
                            const quantity = context.parsed;
                            const percentage = total ? ((quantity / total) * 100).toFixed(1) : 0;
                            return `${context.label}: ${quantity} máy (${percentage}%)`;
                        }
                    }
                }
            },
            cutout: '70%'
        }
    });
}

function getBrandColor(brand, extraBrands = []) {
    const brands = [...new Set([
        ...state.products.map(product => product.Brand),
        ...extraBrands
    ].filter(Boolean))].sort((a, b) => a.localeCompare(b));
    const brandIndex = brands.indexOf(brand);
    const hue = ((brandIndex < 0 ? brands.length : brandIndex) * 137.508) % 360;
    return `hsl(${hue.toFixed(1)} 78% 58%)`;
}

function renderTopSellersTable(topSellers) {
    const tbody = document.getElementById('topSellersTableBody');
    if (!topSellers || topSellers.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-muted">Chưa có giao dịch bán hàng</td></tr>`;
        return;
    }
    tbody.innerHTML = topSellers.map(p => `
        <tr>
            <td>
                <div style="display:flex;align-items:center;gap:12px;">
                    <img src="${p.ImageURL || 'https://images.unsplash.com/photo-1593642632823-8f785ba67e45?w=100'}" style="width:40px;height:40px;border-radius:6px;object-fit:cover;">
                    <strong>${p.ProductName}</strong>
                </div>
            </td>
            <td><span class="badge-pill">${p.Brand}</span></td>
            <td><strong class="text-success">${p.QtySold} máy</strong></td>
            <td><strong>${formatVND(p.Revenue)}</strong></td>
            <td><span class="badge-status in-stock"><i class="fa-solid fa-check"></i> Đang bán</span></td>
        </tr>
    `).join('');
}

// ================= POS COUNTER LOGIC (UC04) =================
async function loadCategories() {
    try {
        const res = await apiFetch('/api/categories');
        const data = await res.json();
        if (data.success) {
            state.categories = data.categories;
            renderCategoryFilters();
        }
    } catch (e) {
        console.error("Lỗi tải danh mục:", e);
    }
}

function renderCategoryFilters() {
    const pillsContainer = document.getElementById('posCategoryPills');
    pillsContainer.innerHTML = `<button class="pill active" data-cat="all">Tất cả</button>` +
        state.categories.map(c => `<button class="pill" data-cat="${c.CategoryID}">${c.CategoryName}</button>`).join('');

    pillsContainer.querySelectorAll('.pill').forEach(btn => {
        btn.addEventListener('click', () => {
            pillsContainer.querySelectorAll('.pill').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            state.posPage = 1;
            renderPosProducts(btn.getAttribute('data-cat'));
        });
    });

    // Populate dropdowns in modals
    const prodCatSelect = document.getElementById('pFormCategory');
    const filterCatSelect = document.getElementById('productCategoryFilter');
    if (prodCatSelect) {
        prodCatSelect.innerHTML = state.categories.map(c => `<option value="${c.CategoryID}">${c.CategoryName}</option>`).join('');
    }
    if (filterCatSelect) {
        filterCatSelect.innerHTML = `<option value="all">Tất cả danh mục</option>` +
            state.categories.map(c => `<option value="${c.CategoryID}">${c.CategoryName}</option>`).join('');
    }
}

function renderBrandFilter() {
    const brandFilter = document.getElementById('productBrandFilter');
    if (!brandFilter) return;

    const brands = [...new Set(state.products.map(product => product.Brand).filter(Boolean))].sort();
    brandFilter.innerHTML = `<option value="all">Tất cả hãng máy</option>` +
        brands.map(brand => `<option value="${brand}">${brand}</option>`).join('');
}

async function loadProducts() {
    try {
        const res = await apiFetch('/api/products');
        const data = await res.json();
        if (data.success) {
            state.products = data.products;
            renderBrandFilter();
            renderPosProducts();
            renderProductsTable();
        }
    } catch (e) {
        console.error("Lỗi tải sản phẩm:", e);
    }
}

function renderPosProducts(categoryFilter = 'all', searchQuery = '') {
    const grid = document.getElementById('posProductGrid');
    let filtered = state.products.filter(p => p.Status === 1);

    if (categoryFilter !== 'all') {
        filtered = filtered.filter(p => p.CategoryID == categoryFilter);
    }

    if (searchQuery) {
        const q = searchQuery.toLowerCase();
        filtered = filtered.filter(p =>
            p.ProductName.toLowerCase().includes(q) ||
            p.ProductCode.toLowerCase().includes(q) ||
            p.Brand.toLowerCase().includes(q) ||
            (p.CPU && p.CPU.toLowerCase().includes(q))
        );
    }

    const productCount = document.getElementById('posProductCount');
    if (productCount) productCount.textContent = `${filtered.length} sản phẩm`;

    const totalPages = Math.max(1, Math.ceil(filtered.length / state.posPageSize));
    state.posPage = Math.min(state.posPage, totalPages);
    const startIndex = (state.posPage - 1) * state.posPageSize;
    const visibleProducts = filtered.slice(startIndex, startIndex + state.posPageSize);

    if (filtered.length === 0) {
        grid.innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:50px;color:var(--text-muted);">
            <i class="fa-solid fa-box-open" style="font-size:40px;margin-bottom:12px;opacity:0.4;"></i>
            <p>Không tìm thấy laptop phù hợp trong kho</p>
        </div>`;
        renderPosPagination(0);
        return;
    }

    grid.innerHTML = visibleProducts.map(p => {
        const isOutOfStock = p.StockQuantity <= 0;
        const isLowStock = p.StockQuantity > 0 && p.StockQuantity <= p.MinThreshold;
        const stockBadgeClass = isOutOfStock ? 'out-of-stock' : (isLowStock ? 'low-stock' : 'in-stock');
        const stockText = isOutOfStock ? 'Hết hàng' : `Còn: ${p.StockQuantity}`;

        return `
        <div class="product-item-card" style="--brand-color: ${getBrandColor(p.Brand)};">
            <div class="prod-img-wrap">
                <img src="${p.ImageURL || 'https://images.unsplash.com/photo-1593642632823-8f785ba67e45?w=500'}" alt="${p.ProductName}" loading="lazy">
                <span class="prod-stock-badge badge-status ${stockBadgeClass}">${stockText}</span>
            </div>
            <div class="prod-info">
                <span class="prod-brand">${p.Brand}</span>
                <div class="prod-name" title="${p.ProductName}">${p.ProductName}</div>
                <div class="prod-detail-list">
                    <div><b>CPU:</b> ${p.CPU || 'Đang cập nhật'}</div>
                    <div><b>RAM:</b> ${p.RAM || 'Đang cập nhật'}</div>
                    <div><b>Ổ lưu trữ:</b> ${p.Storage || 'Đang cập nhật'}</div>
                    <div><b>GPU:</b> ${p.GPU || 'Đang cập nhật'}</div>
                    <div><b>Màn hình:</b> ${p.Screen || 'Đang cập nhật'}</div>
                    <div><b>Mô tả:</b> ${p.Description || 'Chưa có mô tả'}</div>
                </div>
                <div class="prod-price"><span>Giá bán</span> ${formatVND(p.Price)}</div>
                <button class="btn-add-pos" ${isOutOfStock ? 'disabled style="opacity:0.5;cursor:not-allowed;"' : ''} onclick="addToCart(${p.ProductID})">
                    <i class="fa-solid ${isOutOfStock ? 'fa-ban' : 'fa-cart-plus'}"></i> ${isOutOfStock ? 'Hết hàng' : 'Thêm vào giỏ'}
                </button>
            </div>
        </div>
        `;
    }).join('');
    renderPosPagination(totalPages);
}

function renderPosPagination(totalPages) {
    const pagination = document.getElementById('posPagination');
    if (!pagination) return;

    if (totalPages <= 1) {
        pagination.innerHTML = '';
        return;
    }

    const firstItem = ((state.posPage - 1) * state.posPageSize) + 1;
    const lastItem = Math.min(state.posPage * state.posPageSize, Number(document.getElementById('posProductCount')?.textContent.match(/\d+/)?.[0] || 0));
    pagination.innerHTML = `
        <button class="pagination-btn" ${state.posPage === 1 ? 'disabled' : ''} onclick="changePosPage(${state.posPage - 1})" aria-label="Trang trước">
            <i class="fa-solid fa-chevron-left"></i>
        </button>
        <span class="pagination-current">${firstItem}-${lastItem} trên tổng số sản phẩm</span>
        <button class="pagination-btn" ${state.posPage === totalPages ? 'disabled' : ''} onclick="changePosPage(${state.posPage + 1})" aria-label="Trang sau">
            <i class="fa-solid fa-chevron-right"></i>
        </button>
    `;
}

function changePosPage(page) {
    state.posPage = page;
    const activePill = document.querySelector('#posCategoryPills .pill.active');
    const searchInput = document.getElementById('posSearchInput');
    renderPosProducts(
        activePill ? activePill.getAttribute('data-cat') : 'all',
        searchInput ? searchInput.value : ''
    );
}

function addToCart(productId) {
    const prod = state.products.find(p => p.ProductID === productId);
    if (!prod) return;

    if (prod.StockQuantity <= 0) {
        showToast(`Sản phẩm '${prod.ProductName}' đã hết hàng trong kho!`, 'error');
        return;
    }

    const existing = state.cart.find(item => item.productId === productId);
    if (existing) {
        if (existing.quantity >= prod.StockQuantity) {
            showToast(`Tồn kho chỉ còn ${prod.StockQuantity} máy, không thể thêm tiếp!`, 'warning');
            return;
        }
        existing.quantity += 1;
    } else {
        state.cart.push({
            productId: prod.ProductID,
            productCode: prod.ProductCode,
            productName: prod.ProductName,
            price: prod.Price,
            stock: prod.StockQuantity,
            quantity: 1
        });
    }

    renderCart();
    showToast(`Đã thêm '${prod.ProductName}' vào đơn hàng!`);
}

function updateCartItemQty(productId, delta) {
    const item = state.cart.find(i => i.productId === productId);
    if (!item) return;

    const newQty = item.quantity + delta;
    if (newQty <= 0) {
        state.cart = state.cart.filter(i => i.productId !== productId);
    } else if (newQty > item.stock) {
        showToast(`Số lượng vượt quá tồn kho hiện tại (${item.stock} máy)!`, 'warning');
        return;
    } else {
        item.quantity = newQty;
    }
    renderCart();
}

function clearCart() {
    state.cart = [];
    renderCart();
}

function renderCart() {
    const list = document.getElementById('posCartItemsList');
    const posLayout = document.querySelector('#page-pos .pos-layout');
    if (posLayout) posLayout.classList.toggle('has-cart', state.cart.length > 0);

    if (state.cart.length === 0) {
        list.innerHTML = `
            <div class="empty-cart-state">
                <i class="fa-solid fa-cart-arrow-down"></i>
                <p>Chưa có sản phẩm trong đơn hàng</p>
                <small>Nhấn chọn các mẫu laptop bên trái hoặc sử dụng Trợ lý AI để thêm máy.</small>
            </div>`;
    } else {
        list.innerHTML = state.cart.map(item => `
            <div class="cart-row">
                <div class="cart-row-title">
                    <strong>${item.productName}</strong>
                    <small>${item.productCode} • ${formatVND(item.price)}</small>
                </div>
                <div class="cart-qty-ctrl">
                    <button class="qty-btn" onclick="updateCartItemQty(${item.productId}, -1)">-</button>
                    <span style="font-weight:700;min-width:20px;text-align:center;">${item.quantity}</span>
                    <button class="qty-btn" onclick="updateCartItemQty(${item.productId}, 1)">+</button>
                </div>
                <div class="cart-row-price">${formatVND(item.price * item.quantity)}</div>
            </div>
        `).join('');
    }

    // Calculations
    const subtotal = state.cart.reduce((sum, it) => sum + (it.price * it.quantity), 0);
    const discPctInput = document.getElementById('posDiscountPercent');
    const discPct = Math.min(15, Math.max(0, parseFloat(discPctInput.value) || 0));
    const discAmount = (subtotal * discPct) / 100.0;
    const finalTotal = subtotal - discAmount;

    document.getElementById('posSubTotal').textContent = formatVND(subtotal);
    document.getElementById('posDiscountAmount').textContent = `- ${formatVND(discAmount)}`;
    document.getElementById('posFinalTotal').textContent = formatVND(finalTotal);
}

async function processCheckout() {
    if (state.cart.length === 0) {
        showToast('Vui lòng chọn ít nhất 1 sản phẩm vào đơn hàng!', 'warning');
        return;
    }

    const custSelect = document.getElementById('posCustomerSelect');
    const custId = custSelect.value ? parseInt(custSelect.value) : null;
    const discPct = parseFloat(document.getElementById('posDiscountPercent').value) || 0;
    const payMethodInput = document.querySelector('input[name="payMethod"]:checked');
    const paymentMethod = payMethodInput ? payMethodInput.value : 'Tiền mặt';

    const payload = {
        userId: state.currentUser.id,
        customerId: custId,
        paymentMethod: paymentMethod,
        discountPercent: discPct,
        items: state.cart.map(it => ({
            productId: it.productId,
            quantity: it.quantity
        }))
    };

    try {
        const res = await apiFetch('/api/invoices', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!data.success) {
            showToast(data.message, 'error');
            return;
        }

        showToast("Lập hóa đơn và thanh toán thành công!", 'success');

        // Show receipt print preview
        openReceiptModal(data.invoiceId, data.vietQrUrl);

        // Reset cart & refresh
        clearCart();
        loadProducts();
        loadDashboardData();
    } catch (e) {
        showToast('Lỗi khi gửi yêu cầu thanh toán!', 'error');
    }
}

async function openReceiptModal(invoiceId, customVietQrUrl = null) {
    try {
        const res = await apiFetch(`/api/invoices/${invoiceId}`);
        const data = await res.json();
        if (!data.success) return;

        const inv = data.invoice;
        const items = data.items;

        document.getElementById('rcInvoiceCode').textContent = `Mã HĐ: ${inv.InvoiceCode}`;
        document.getElementById('rcInvoiceDate').textContent = `Ngày: ${inv.InvoiceDate}`;
        document.getElementById('rcStaffName').textContent = `Thu ngân: ${inv.StaffName}`;
        document.getElementById('rcCustomerName').textContent = `Khách hàng: ${inv.CustomerName} (${inv.CustomerPhone})`;

        const itemsTbody = document.getElementById('rcItemsBody');
        itemsTbody.innerHTML = items.map(it => `
            <tr>
                <td>${it.ProductName}</td>
                <td>${it.Quantity}</td>
                <td>${formatVND(it.UnitPrice)}</td>
                <td style="text-align:right;">${formatVND(it.SubTotal)}</td>
            </tr>
        `).join('');

        document.getElementById('rcSubTotal').textContent = formatVND(inv.SubTotal);
        document.getElementById('rcDiscount').textContent = `- ${formatVND(inv.DiscountAmount)} (${inv.DiscountPercent}%)`;
        document.getElementById('rcFinalTotal').textContent = formatVND(inv.TotalAmount);
        document.getElementById('rcPaymentMethod').textContent = inv.PaymentMethod;

        // QR Code
        const qrWrap = document.getElementById('receiptQrWrap');
        const qrImg = document.getElementById('rcVietQrImg');
        const qrUrl = customVietQrUrl || `https://img.vietqr.io/image/MB-0987654321-compact2.png?amount=${parseInt(inv.TotalAmount)}&addInfo=${inv.InvoiceCode}&accountName=NGUYEN%20DINH%20BANG`;
        qrImg.src = qrUrl;
        qrWrap.style.display = 'block';

        openModal('receiptModal');
    } catch (e) {
        console.error("Lỗi xem hóa đơn:", e);
    }
}

// ================= CUSTOMERS LOGIC (UC03) =================
async function loadCustomers() {
    try {
        const res = await apiFetch('/api/customers');
        const data = await res.json();
        if (data.success) {
            state.customers = data.customers;
            renderCustomersTable();
            populateCustomerSelects();
        }
    } catch (e) {
        console.error("Lỗi tải khách hàng:", e);
    }
}

function renderCustomersTable() {
    const tbody = document.getElementById('customersTableBody');
    if (!tbody) return;
    const tierStyles = {
        'Thân thiết': { className: 'tier-friendly', icon: '' },
        'Bạc': { className: 'tier-silver', icon: 'fa-medal' },
        'Vàng': { className: 'tier-gold', icon: 'fa-trophy' },
        'Kim cương': { className: 'tier-diamond', icon: 'fa-gem' },
        'Ruby': { className: 'tier-ruby', icon: 'fa-crown' }
    };
    const canEditCustomers = ['Admin', 'Manager'].includes(state.currentRole);
    const canManageCustomerAccounts = ['Admin', 'Manager'].includes(state.currentRole);
    tbody.innerHTML = state.customers.map(c => `
        <tr>
            <td><strong>${c.CustomerCode || 'KH---'}</strong></td>
            <td><strong>${c.CustomerName}</strong></td>
            <td>${c.Phone}</td>
            <td>${c.Email || '---'}</td>
            <td>${c.Address || '---'}</td>
            <td>${(() => {
                const tier = tierStyles[c.CustomerGroup] || tierStyles['Thân thiết'];
                const icon = tier.icon ? `<i class="fa-solid ${tier.icon}" aria-hidden="true"></i>` : '';
                return `<span class="badge-status ${tier.className}">${icon}${c.CustomerGroup}</span>`;
            })()}</td>
            <td><strong class="text-success">${formatVND(c.TotalSpent)}</strong></td>
            <td>${canEditCustomers ? `<button class="btn btn-sm btn-outline" onclick="openEditCustomerModal(${c.CustomerID})" title="Cập nhật thông tin khách hàng">
                <i class="fa-solid fa-pen-to-square"></i> Cập nhật
            </button>` : '<span class="text-muted">Chỉ xem</span>'}</td>
            <td>${canManageCustomerAccounts && !c.HasAccount ? `<button class="btn btn-sm btn-outline" onclick="openCustomerAccountModal(${c.CustomerID})" title="Tạo tài khoản Customer"><i class="fa-solid fa-user-plus"></i> Tạo tài khoản</button>` : (c.HasAccount ? '<span class="user-status-badge active"><i class="fa-solid fa-circle-check"></i> Có tài khoản</span>' : '—')}</td>
        </tr>
    `).join('');
}

function populateCustomerSelects() {
    const select = document.getElementById('posCustomerSelect');
    if (!select) return;
    select.innerHTML = `<option value="">Khách lẻ vãng lai</option>` +
        state.customers.map(c => `<option value="${c.CustomerID}">${c.CustomerName} - ${c.Phone} (${c.CustomerGroup})</option>`).join('');
}

function openAddCustomerModal() {
    document.getElementById('customerModalTitle').innerHTML = '<i class="fa-solid fa-user-plus text-primary"></i> Thêm Khách hàng Mới';
    document.getElementById('customerSubmitLabel').textContent = 'Lưu Khách hàng';
    document.getElementById('customerEditId').value = '';
    document.getElementById('customerForm').reset();
    document.getElementById('customerAccountFields').style.display = '';
    document.getElementById('cFormUsername').required = true;
    document.getElementById('cFormPassword').required = true;
    openModal('customerModal');
}

function openEditCustomerModal(customerId) {
    const customer = state.customers.find(item => item.CustomerID === customerId);
    if (!customer) return;
    document.getElementById('customerModalTitle').innerHTML = '<i class="fa-solid fa-user-pen text-primary"></i> Cập nhật Thông tin Khách hàng';
    document.getElementById('customerSubmitLabel').textContent = 'Cập nhật thông tin';
    document.getElementById('customerEditId').value = customer.CustomerID;
    document.getElementById('cFormName').value = customer.CustomerName || '';
    document.getElementById('cFormPhone').value = customer.Phone || '';
    document.getElementById('cFormEmail').value = customer.Email || '';
    document.getElementById('cFormAddr').value = customer.Address || '';
    document.getElementById('customerAccountFields').style.display = 'none';
    document.getElementById('cFormUsername').required = false;
    document.getElementById('cFormPassword').required = false;
    openModal('customerModal');
}

function openCustomerAccountModal(customerId) {
    const customer = state.customers.find(item => item.CustomerID === customerId);
    if (!customer) return;
    document.getElementById('customerAccountId').value = customerId;
    document.getElementById('customerAccountName').textContent = `Khách hàng: ${customer.CustomerName}`;
    document.getElementById('customerAccountForm').reset();
    openModal('customerAccountModal');
}

async function handleCustomerAccountSubmit(event) {
    event.preventDefault();
    const customerId = document.getElementById('customerAccountId').value;
    const username = document.getElementById('customerAccountUsername').value.trim();
    const password = document.getElementById('customerAccountPassword').value;
    if (!username || password.length < 6) {
        showToast('Tên đăng nhập và mật khẩu tối thiểu 6 ký tự là bắt buộc.', 'error');
        return;
    }
    try {
        const res = await apiFetch(`/api/customers/${customerId}/account`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.message || 'Không thể tạo tài khoản Customer.');
        closeModal('customerAccountModal');
        showToast(data.message, 'success');
        loadCustomers();
    } catch (error) {
        showToast(error.message, 'error');
    }
}

async function handleCustomerSubmit(e) {
    e.preventDefault();
    const payload = {
        customerName: document.getElementById('cFormName').value.trim(),
        phone: document.getElementById('cFormPhone').value.trim(),
        email: document.getElementById('cFormEmail').value.trim(),
        address: document.getElementById('cFormAddr').value.trim(),
        username: document.getElementById('cFormUsername').value.trim(),
        password: document.getElementById('cFormPassword').value
    };
    const customerId = document.getElementById('customerEditId').value;
    const isEditing = Boolean(customerId);
    const contactError = validateContactInputs(payload.phone, payload.email, true, true);
    if (contactError) {
        showToast(contactError, 'error');
        return;
    }

    try {
        const res = await apiFetch(isEditing ? `/api/customers/${customerId}` : '/api/customers', {
            method: isEditing ? 'PUT' : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
            showToast(isEditing ? "Cập nhật thông tin khách hàng thành công!" : "Thêm khách hàng thành công!");
            closeModal('customerModal');
            document.getElementById('customerForm').reset();
            loadCustomers();
        } else {
            showToast(data.message, 'error');
        }
    } catch (e) {
        showToast("Lỗi khi thêm khách hàng!", 'error');
    }
}

// ================= INVENTORY & PRODUCTS MANAGEMENT (UC02, UC05) =================
function renderProductsTable() {
    const tbody = document.getElementById('productsTableBody');
    if (!tbody) return;

    const canEditProducts = ['Admin', 'Manager', 'Staff'].includes(state.currentRole);
    const customerMode = state.currentRole === 'Customer';
    tbody.innerHTML = state.products.map(p => {
        const isOutOfStock = p.StockQuantity <= 0;
        const isLowStock = p.StockQuantity > 0 && p.StockQuantity <= p.MinThreshold;
        const stockBadge = isOutOfStock ? 'out-of-stock' : (isLowStock ? 'low-stock' : 'in-stock');

        return `
        <tr>
            <td><strong>${p.ProductCode}</strong></td>
            <td>
                <div style="display:flex;align-items:center;gap:10px;">
                    <img src="${p.ImageURL || 'https://images.unsplash.com/photo-1593642632823-8f785ba67e45?w=100'}" style="width:42px;height:42px;border-radius:6px;object-fit:cover;">
                    <div>
                        <strong>${p.ProductName}</strong>
                        <div style="font-size:11px;color:var(--text-muted);">${p.CPU || ''} • ${p.RAM || ''} • ${p.GPU || ''}</div>
                    </div>
                </div>
            </td>
            <td><span class="badge-pill">${p.CategoryName}</span></td>
            <td class="product-cost-cell" style="${customerMode ? 'display:none;' : ''}">${customerMode ? '—' : formatVND(p.CostPrice)}</td>
            <td><strong style="color:#38bdf8;">${formatVND(p.Price)}</strong></td>
            <td>
                <strong class="${isLowStock ? 'text-warning' : ''}">${p.StockQuantity} máy</strong>
                <small class="text-muted d-block">${customerMode ? 'Có thể đặt mua' : `Ngưỡng: ${p.MinThreshold ?? 'Chưa đặt'}`}</small>
            </td>
            <td><span class="badge-status ${stockBadge}">${p.StockStatus}</span></td>
            <td class="product-action-cell" style="${customerMode ? 'display:none;' : ''}">${canEditProducts ? `<button class="btn btn-sm btn-outline" onclick="deleteProduct(${p.ProductID})" title="Ngừng kinh doanh">
                    <i class="fa-solid fa-trash-can text-danger"></i>
                </button>
            ` : '<span class="text-muted">Chỉ xem</span>'}</td>
        </tr>
        `;
    }).join('');
}

function openAddProductModal() {
    openModal('productModal');
}

async function handleProductSubmit(e) {
    e.preventDefault();
    const payload = {
        categoryId: parseInt(document.getElementById('pFormCategory').value),
        productCode: document.getElementById('pFormCode').value.trim(),
        productName: document.getElementById('pFormName').value.trim(),
        brand: document.getElementById('pFormBrand').value.trim(),
        cpu: document.getElementById('pFormCpu').value.trim(),
        ram: document.getElementById('pFormRam').value.trim(),
        gpu: document.getElementById('pFormGpu').value.trim(),
        storage: document.getElementById('pFormStorage').value.trim(),
        costPrice: parseFloat(document.getElementById('pFormCostPrice').value) || 0,
        price: parseFloat(document.getElementById('pFormPrice').value) || 0,
        quantity: parseInt(document.getElementById('pFormQty').value) || 0,
        minThreshold: parseInt(document.getElementById('pFormMinTh').value) || 3,
        imageUrl: document.getElementById('pFormImg').value.trim() || 'https://images.unsplash.com/photo-1593642632823-8f785ba67e45?w=500',
        description: document.getElementById('pFormDesc').value.trim()
    };

    try {
        const res = await apiFetch('/api/products', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
            showToast("Thêm sản phẩm thành công!");
            closeModal('productModal');
            document.getElementById('productForm').reset();
            loadProducts();
            loadDashboardData();
        } else {
            showToast(data.message, 'error');
        }
    } catch (e) {
        showToast("Lỗi khi thêm sản phẩm!", 'error');
    }
}

async function deleteProduct(productId) {
    if (!confirm("Bạn có chắc chắn muốn ngừng kinh doanh sản phẩm này?")) return;
    try {
        const res = await apiFetch(`/api/products/${productId}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.success) {
            showToast(data.message);
            loadProducts();
        }
    } catch (e) {
        showToast("Lỗi thao tác!", 'error');
    }
}

// ================= STOCK IMPORTS (UC05) =================
async function loadImports() {
    try {
        const res = await apiFetch('/api/imports');
        const data = await res.json();
        if (data.success) {
            renderImportsTable(data.imports);
        }
    } catch (e) {
        console.error("Lỗi tải phiếu nhập:", e);
    }
}

function renderImportsTable(imports) {
    const tbody = document.getElementById('importsTableBody');
    if (!tbody) return;
    tbody.innerHTML = imports.map(imp => `
        <tr>
            <td><strong>${imp.ImportCode}</strong></td>
            <td><strong>${imp.SupplierName}</strong></td>
            <td>${imp.StaffName}</td>
            <td>${imp.ImportDate}</td>
            <td>${imp.TotalItems} mặt hàng</td>
            <td><strong class="text-info">${formatVND(imp.TotalAmount)}</strong></td>
            <td><span class="badge-status in-stock">${imp.Status}</span></td>
        </tr>
    `).join('');
}

async function openAddImportModal() {
    // Load suppliers and products into dropdowns
    try {
        const [suppRes, prodRes] = await Promise.all([
            apiFetch('/api/suppliers'),
            apiFetch('/api/products')
        ]);
        const suppData = await suppRes.json();
        const prodData = await prodRes.json();

        const suppSelect = document.getElementById('impFormSupplier');
        const prodSelect = document.getElementById('impFormProduct');

        if (suppData.success) {
            suppSelect.innerHTML = suppData.suppliers.map(s => `<option value="${s.SupplierID}">${s.SupplierName}</option>`).join('');
        }
        if (prodData.success) {
            prodSelect.innerHTML = prodData.products.map(p => `<option value="${p.ProductID}">${p.ProductName} (Hiện có: ${p.StockQuantity})</option>`).join('');
        }
        openModal('importModal');
    } catch (e) {
        showToast("Lỗi khi mở modal nhập hàng!", 'error');
    }
}

async function handleImportSubmit(e) {
    e.preventDefault();
    const payload = {
        userId: state.currentUser.id,
        supplierId: parseInt(document.getElementById('impFormSupplier').value),
        items: [{
            productId: parseInt(document.getElementById('impFormProduct').value),
            quantity: parseInt(document.getElementById('impFormQty').value),
            unitPrice: parseFloat(document.getElementById('impFormPrice').value)
        }]
    };

    try {
        const res = await apiFetch('/api/imports', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
            showToast("Đã lập phiếu nhập kho & tự động cập nhật tồn kho!");
            closeModal('importModal');
            loadImports();
            loadProducts();
            loadDashboardData();
        } else {
            showToast(data.message, 'error');
        }
    } catch (e) {
        showToast("Lỗi khi lập phiếu nhập!", 'error');
    }
}

// ================= INVOICES HISTORY (UC04) =================
async function loadInvoices() {
    try {
        const res = await apiFetch('/api/invoices');
        const data = await res.json();
        if (data.success) {
            renderInvoicesTable(data.invoices);
        }
    } catch (e) {
        console.error("Lỗi tải hóa đơn:", e);
    }
}

function renderInvoicesTable(invoices) {
    const tbody = document.getElementById('invoicesTableBody');
    if (!tbody) return;
    tbody.innerHTML = invoices.map(inv => `
        <tr>
            <td><strong>${inv.InvoiceCode}</strong></td>
            <td>${inv.InvoiceDate}</td>
            <td><strong>${inv.CustomerName}</strong></td>
            <td>${inv.StaffName}</td>
            <td>${inv.TotalItems} món</td>
            <td><strong class="text-success">${formatVND(inv.TotalAmount)}</strong></td>
            <td><span class="badge-pill">${inv.PaymentMethod}</span></td>
            <td>
                <button class="btn btn-sm btn-outline" onclick="openReceiptModal(${inv.InvoiceID})">
                    <i class="fa-solid fa-eye"></i> Xem / In
                </button>
            </td>
        </tr>
    `).join('');
}

// ================= AI HUB INTERACTION (UC09, UC10, UC11) =================
function switchAiTab(tabId) {
    document.querySelectorAll('.ai-tab-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.ai-tab-content').forEach(c => c.classList.remove('active'));

    const btn = document.querySelector(`.ai-tab-btn[data-tab="${tabId}"]`);
    const content = document.getElementById(`tab-${tabId.replace('-tab', '')}`);
    if (btn) btn.classList.add('active');
    if (content) content.classList.add('active');

    if (tabId === 'history-tab') loadAiHistory();
}

function fillAdvisorPrompt(text) {
    document.getElementById('aiAdvisorQuery').value = text;
}

function escapeAiHtml(value) {
    return String(value || '').replace(/[&<>'"]/g, character => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    }[character]));
}

function renderAiText(value) {
    return escapeAiHtml(value)
        .replace(/^#### (.+)$/gm, '<h4>$1</h4>')
        .replace(/^### (.+)$/gm, '<h3>$1</h3>')
        .replace(/^## (.+)$/gm, '<h3>$1</h3>')
        .replace(/^\* (.+)$/gm, '<div class="ai-bullet">$1</div>')
        .replace(/^- (.+)$/gm, '<div class="ai-bullet">$1</div>')
        .replace(/^(\d+)\. (.+)$/gm, '<div class="ai-numbered"><span>$1.</span> $2</div>')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*([^*\n]+)\*/g, '<em>$1</em>')
        .replace(/\n/g, '<br>');
}

// UC09: AI Product Advisor
async function runAiAdvisor() {
    const query = document.getElementById('aiAdvisorQuery').value.trim();
    if (!query) {
        showToast("Vui lòng nhập nhu cầu khách hàng!", 'warning');
        return;
    }

    const btn = document.getElementById('btnRunAdvisor');
    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Đang phân tích kho hàng & cấu hình...`;

    try {
        const res = await apiFetch('/api/ai/advisor', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: query, userId: state.currentUser.id })
        });
        const resJson = await res.json();
        if (!resJson.success) {
            showToast(resJson.message || "Lỗi phân tích AI!", 'error');
            return;
        }

        const data = resJson.data;
        document.getElementById('advisorAnalysisText').innerHTML = renderAiText(data.analysis);

        // Render Recommended Product Cards
        const grid = document.getElementById('advisorCardsGrid');
        const requestedCount = Number(data.requested_count) || 3;
        const recommendedProducts = (data.recommended_products || []).slice(0, requestedCount);
        if (recommendedProducts.length > 0) {
            grid.innerHTML = recommendedProducts.map((p, idx) => `
                <div class="advisor-prod-card ${idx === 0 ? 'featured' : ''}">
                    ${idx === 0 ? '<span class="badge-status vip mb-2" style="align-self:flex-start;">LỰA CHỌN TỐI ƯU NHẤT</span>' : ''}
                    <img src="${p.ImageURL || 'https://images.unsplash.com/photo-1593642632823-8f785ba67e45?w=500'}" style="height:120px;border-radius:8px;object-fit:cover;margin-bottom:10px;">
                    <strong style="font-size:14px;margin-bottom:4px;">${p.ProductName}</strong>
                    <div style="font-size:12px;color:var(--text-muted);margin-bottom:8px;">
                        • <strong>CPU:</strong> ${p.CPU}<br>
                        • <strong>RAM:</strong> ${p.RAM} | <strong>Ổ:</strong> ${p.Storage}<br>
                        • <strong>GPU:</strong> ${p.GPU}<br>
                        • <strong>Màn hình:</strong> ${p.Screen}
                    </div>
                    <div style="font-size:16px;font-weight:800;color:#38bdf8;margin-top:auto;">${formatVND(p.Price)}</div>
                    <small class="text-muted">Kho: Còn ${p.StockQuantity} máy</small>
                    ${['Manager', 'Staff'].includes(state.currentRole) ? `<button class="btn btn-sm btn-primary mt-3" onclick="selectAdvisorProductToCart(${p.ProductID})">
                        <i class="fa-solid fa-cart-plus"></i> Thêm vào Hóa đơn POS
                    </button>` : ''}
                </div>
            `).join('');
        } else {
            grid.innerHTML = `<p class="text-muted">Không tìm thấy sản phẩm phù hợp.</p>`;
        }

        document.getElementById('advisorResultPanel').classList.remove('hidden');
        showToast("AI đã hoàn thành tư vấn sản phẩm!");
    } catch (e) {
        showToast("Lỗi kết nối AI!", 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles"></i> Phân tích & Đề xuất ngay`;
    }
}

function selectAdvisorProductToCart(productId) {
    addToCart(productId);
    switchPage('pos');
    showToast("Đã chuyển laptop được AI tư vấn vào giỏ hàng POS!", 'success');
}

// UC10: AI Revenue Analyst
async function runAiRevenueAnalysis() {
    const btn = document.getElementById('btnRunRevenueAnalysis');
    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> AI đang tổng hợp số liệu hóa đơn & tồn kho...`;

    try {
        const res = await apiFetch('/api/ai/revenue-analysis', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ userId: state.currentUser.id })
        });
        const resJson = await res.json();
        if (resJson.success) {
            document.getElementById('revenueAnalysisText').innerHTML = renderAiText(resJson.data.analysis);
            document.getElementById('revenueResultPanel').classList.remove('hidden');
            showToast("Báo cáo phân tích AI đã sẵn sàng!");
        } else {
            showToast(resJson.message || "Lỗi phân tích doanh thu!", 'error');
        }
    } catch (e) {
        showToast("Lỗi phân tích doanh thu!", 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<i class="fa-solid fa-chart-line"></i> Khởi chạy Phân tích Dữ liệu Toàn diện`;
    }
}

function printAiReport() {
    window.print();
}

// UC11: AI Sales Q&A
function sendQuickQuestion(question) {
    document.getElementById('chatQuestionInput').value = question;
    sendChatQuestion();
}

async function sendChatQuestion() {
    const input = document.getElementById('chatQuestionInput');
    const question = input.value.trim();
    if (!question) return;

    const chatWrap = document.getElementById('chatMessagesWrap');

    // Append User Message
    const userMsg = document.createElement('div');
    userMsg.className = 'chat-message user';
    userMsg.innerHTML = `
        <div class="msg-avatar">${state.currentUser.avatar}</div>
        <div class="msg-content">${escapeAiHtml(question)}</div>
    `;
    chatWrap.appendChild(userMsg);
    input.value = '';
    chatWrap.scrollTop = chatWrap.scrollHeight;

    // Append Loading Bot Message
    const botMsg = document.createElement('div');
    botMsg.className = 'chat-message bot';
    botMsg.innerHTML = `
        <div class="msg-avatar"><i class="fa-solid fa-robot"></i></div>
        <div class="msg-content"><i class="fa-solid fa-spinner fa-spin"></i> Đang tra cứu cơ sở dữ liệu hệ thống...</div>
    `;
    chatWrap.appendChild(botMsg);
    chatWrap.scrollTop = chatWrap.scrollHeight;

    try {
        const res = await apiFetch('/api/ai/query', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question: question, userId: state.currentUser.id })
        });
        const resJson = await res.json();
        if (resJson.success) {
            let answerHtml = renderAiText(resJson.data.answer);
            
            // RAG Level 3: Hiển thị Badge Route
            if (resJson.data.query_type) {
                let badgeColor = '#3b82f6'; // SQL
                if (resJson.data.query_type === 'RAG') badgeColor = '#10b981'; // RAG
                if (resJson.data.query_type.includes('Mixed')) badgeColor = '#f59e0b'; // Mixed
                
                answerHtml = `<div style="margin-bottom: 8px;"><span style="background: ${badgeColor}20; border: 1px solid ${badgeColor}; color: ${badgeColor}; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;"><i class="fa-solid fa-route"></i> Route: ${resJson.data.query_type}</span></div>` + answerHtml;
            }
            
            // RAG Level 3: Hiển thị Nguồn tài liệu
            if (resJson.data.sources && resJson.data.sources.length > 0) {
                answerHtml += `<div style="margin-top: 12px; padding-top: 10px; border-top: 1px dashed rgba(255,255,255,0.15); font-size: 12px; color: #94a3b8;">
                    <strong style="color: #cbd5e1;"><i class="fa-solid fa-book-open"></i> Nguồn tài liệu tham khảo:</strong>
                    <ul style="margin: 6px 0 0 24px; padding: 0; list-style-type: circle;">
                        ${resJson.data.sources.map(s => `<li>${s}</li>`).join('')}
                    </ul>
                </div>`;
            }
            
            botMsg.querySelector('.msg-content').innerHTML = answerHtml;
        } else {
            botMsg.querySelector('.msg-content').textContent = resJson.message || "Không thể xử lý câu hỏi lúc này.";
        }
    } catch (e) {
        botMsg.querySelector('.msg-content').textContent = "Lỗi kết nối tới máy chủ AI.";
    } finally {
        chatWrap.scrollTop = chatWrap.scrollHeight;
    }
}

function clearChat() {
    const chatWrap = document.getElementById('chatMessagesWrap');
    chatWrap.innerHTML = `
        <div class="chat-message bot">
            <div class="msg-avatar"><i class="fa-solid fa-robot"></i></div>
            <div class="msg-content">
                Đoạn hội thoại đã được làm mới. Quản lý có thể đặt câu hỏi tiếp theo về kho và doanh số bán hàng!
            </div>
        </div>
    `;
}

// ================= USERS MANAGEMENT (UC12 - ADMIN ONLY) =================
const userManagementState = {
    users: [],
    page: 1,
    pageSize: 10,
    search: '',
    role: 'all',
    status: 'all'
};

const userRoleLabels = { Admin: 'Admin', Manager: 'Quản lý', Staff: 'Nhân viên', Customer: 'Khách hàng' };

function getFilteredUsers() {
    const query = userManagementState.search.toLowerCase();
    return userManagementState.users.filter(user => {
        const matchesSearch = !query || [user.Username, user.FullName, user.Email, user.Phone]
            .some(value => String(value || '').toLowerCase().includes(query));
        const matchesRole = userManagementState.role === 'all' || user.Role === userManagementState.role;
        const matchesStatus = userManagementState.status === 'all' || String(user.Status) === userManagementState.status;
        return matchesSearch && matchesRole && matchesStatus;
    });
}

function updateUserStats() {
    const users = userManagementState.users;
    document.getElementById('userStatTotal').textContent = users.length;
    document.getElementById('userStatActive').textContent = users.filter(user => user.Status === 1).length;
    document.getElementById('userStatLocked').textContent = users.filter(user => user.Status !== 1).length;
    document.getElementById('userStatAdmins').textContent = users.filter(user => user.Role === 'Admin').length;
}

function renderUserPagination(totalPages) {
    const pagination = document.getElementById('userPagination');
    if (!pagination) return;
    if (totalPages <= 1) {
        pagination.innerHTML = '';
        return;
    }
    pagination.innerHTML = Array.from({ length: totalPages }, (_, index) => {
        const page = index + 1;
        return `<button class="user-page-btn ${page === userManagementState.page ? 'active' : ''}" onclick="changeUserPage(${page})">${page}</button>`;
    }).join('');
}

function renderUsersTable() {
    const tbody = document.getElementById('usersTableBody');
    if (!tbody) return;
    const filteredUsers = getFilteredUsers();
    const totalPages = Math.max(1, Math.ceil(filteredUsers.length / userManagementState.pageSize));
    userManagementState.page = Math.min(userManagementState.page, totalPages);
    const start = (userManagementState.page - 1) * userManagementState.pageSize;
    const pageUsers = filteredUsers.slice(start, start + userManagementState.pageSize);

    if (!pageUsers.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="user-table-state"><i class="fa-solid fa-user-slash"></i><strong>Không tìm thấy tài khoản</strong><span>Thử thay đổi từ khóa hoặc bộ lọc.</span></td></tr>';
    } else {
        tbody.innerHTML = pageUsers.map(user => {
            const isCurrentUser = state.currentUser && user.UserID === state.currentUser.id;
            const roleLabel = userRoleLabels[user.Role] || user.Role;
            const statusClass = user.Status === 1 ? 'active' : 'locked';
            return `
                <tr>
                    <td><span class="user-id">#${user.UserID}</span></td>
                    <td><strong>${escapeAiHtml(user.Username)}</strong>${isCurrentUser ? '<span class="user-self-tag">Bạn</span>' : ''}</td>
                    <td>${escapeAiHtml(user.FullName)}</td>
                    <td><select class="form-select user-role-select" onchange="updateUserRole(${user.UserID}, this.value)" ${isCurrentUser ? 'disabled' : ''} aria-label="Vai trò của ${escapeAiHtml(user.Username)}">
                        ${Object.entries(userRoleLabels).map(([role, label]) => `<option value="${role}" ${user.Role === role ? 'selected' : ''}>${label}</option>`).join('')}
                    </select></td>
                    <td><div class="user-contact"><span>${escapeAiHtml(user.Email || 'Chưa có email')}</span><small>${escapeAiHtml(user.Phone || 'Chưa có số điện thoại')}</small></div></td>
                    <td><span class="user-status-badge ${statusClass}"><i class="fa-solid ${user.Status === 1 ? 'fa-circle-check' : 'fa-lock'}"></i>${user.Status === 1 ? 'Hoạt động' : 'Đã khóa'}</span></td>
                    <td><div class="user-actions"><button class="btn btn-sm btn-outline" onclick="openEditUserModal(${user.UserID})" title="Sửa tài khoản"><i class="fa-solid fa-pen"></i><span>Sửa</span></button><button class="btn btn-sm ${user.Status === 1 ? 'btn-danger-soft' : 'btn-success-soft'}" onclick="openUserStatusConfirm(${user.UserID})" title="${user.Status === 1 ? 'Khóa' : 'Mở khóa'} tài khoản"><i class="fa-solid ${user.Status === 1 ? 'fa-lock' : 'fa-lock-open'}"></i><span>${user.Status === 1 ? 'Khóa' : 'Mở khóa'}</span></button></div></td>
                </tr>`;
        }).join('');
    }

    const summary = document.getElementById('userResultSummary');
    if (summary) summary.textContent = filteredUsers.length ? `Hiển thị ${start + 1}-${Math.min(start + pageUsers.length, filteredUsers.length)} trên ${filteredUsers.length} tài khoản` : '0 tài khoản phù hợp';
    renderUserPagination(totalPages);
}

async function loadUsers() {
    const tbody = document.getElementById('usersTableBody');
    if (tbody) tbody.innerHTML = '<tr><td colspan="7" class="user-table-state"><i class="fa-solid fa-spinner fa-spin"></i> Đang tải tài khoản...</td></tr>';
    try {
        const res = await apiFetch('/api/auth/users');
        const data = await res.json();
        if (!data.success) throw new Error(data.message || 'Không thể tải danh sách tài khoản.');
        userManagementState.users = data.users || [];
        updateUserStats();
        renderUsersTable();
    } catch (e) {
        console.error("Lỗi tải người dùng:", e);
        if (tbody) tbody.innerHTML = `<tr><td colspan="7" class="user-table-state error"><i class="fa-solid fa-triangle-exclamation"></i><strong>Không thể tải tài khoản</strong><span>${escapeAiHtml(e.message)}</span></td></tr>`;
    }
}

function changeUserPage(page) {
    userManagementState.page = page;
    renderUsersTable();
}

function openAddUserModal() {
    document.getElementById('userForm').reset();
    document.getElementById('userEditId').value = '';
    document.getElementById('userFormUsername').disabled = false;
    document.getElementById('userFormPasswordGroup').style.display = '';
    document.getElementById('userPasswordHint').textContent = '*';
    document.getElementById('userFormPassword').value = '';
    document.getElementById('userFormPassword').required = true;
    document.getElementById('userModalTitle').innerHTML = '<i class="fa-solid fa-user-plus text-primary"></i> Tạo tài khoản mới';
    document.getElementById('userFormSubmitLabel').textContent = 'Tạo tài khoản';
    openModal('userModal');
}

function openEditUserModal(userId) {
    const user = userManagementState.users.find(item => item.UserID === userId);
    if (!user) return;
    document.getElementById('userEditId').value = user.UserID;
    document.getElementById('userFormUsername').value = user.Username;
    document.getElementById('userFormUsername').disabled = true;
    document.getElementById('userFormFullname').value = user.FullName || '';
    document.getElementById('userFormEmail').value = user.Email || '';
    document.getElementById('userFormPhone').value = user.Phone || '';
    document.getElementById('userFormRole').value = user.Role;
    document.getElementById('userFormPasswordGroup').style.display = '';
    document.getElementById('userPasswordHint').textContent = 'mới, để trống nếu không đổi';
    document.getElementById('userFormPassword').value = '';
    document.getElementById('userFormPassword').required = false;
    document.getElementById('userModalTitle').innerHTML = '<i class="fa-solid fa-user-pen text-primary"></i> Sửa tài khoản';
    document.getElementById('userFormSubmitLabel').textContent = 'Lưu thay đổi';
    openModal('userModal');
}

async function handleUserSubmit(event) {
    event.preventDefault();
    const editId = document.getElementById('userEditId').value;
    const payload = {
        username: document.getElementById('userFormUsername').value.trim(),
        fullname: document.getElementById('userFormFullname').value.trim(),
        email: document.getElementById('userFormEmail').value.trim(),
        phone: document.getElementById('userFormPhone').value.trim(),
        role: document.getElementById('userFormRole').value,
        password: document.getElementById('userFormPassword').value.trim()
    };
    const endpoint = editId ? `/api/auth/users/${editId}` : '/api/auth/users';
    const method = editId ? 'PUT' : 'POST';
    const contactError = validateContactInputs(payload.phone, payload.email, true, true);
    if (contactError) {
        showToast(contactError, 'error');
        return;
    }
    try {
        const res = await apiFetch(endpoint, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        const data = await res.json();
        if (!data.success) throw new Error(data.message || 'Không thể lưu tài khoản.');
        closeModal('userModal');
        showToast(data.message || 'Đã lưu tài khoản!', 'success');
        loadUsers();
    } catch (e) {
        showToast(e.message, 'error');
    }
}

function openUserStatusConfirm(userId) {
    const user = userManagementState.users.find(item => item.UserID === userId);
    if (!user) return;
    const willLock = user.Status === 1;
    document.getElementById('userStatusModalTitle').innerHTML = `<i class="fa-solid ${willLock ? 'fa-lock text-warning' : 'fa-lock-open text-success'}"></i> ${willLock ? 'Xác nhận khóa tài khoản' : 'Xác nhận mở khóa tài khoản'}`;
    document.getElementById('userStatusModalText').textContent = `Bạn có chắc muốn ${willLock ? 'khóa' : 'mở khóa'} tài khoản này không?`;
    document.getElementById('userStatusModalDetails').innerHTML = `<strong>${escapeAiHtml(user.Username)}</strong><span>${escapeAiHtml(user.FullName)}</span><small>${userRoleLabels[user.Role] || user.Role}</small>`;
    document.getElementById('userStatusConfirmBtn').textContent = willLock ? 'Xác nhận khóa' : 'Xác nhận mở khóa';
    document.getElementById('userStatusConfirmBtn').onclick = () => toggleUserStatus(userId);
    openModal('userStatusModal');
}

async function updateUserRole(userId, role) {
    try {
        const res = await apiFetch(`/api/auth/users/${userId}/role`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ role })
        });
        const data = await res.json();
        if (!data.success) {
            showToast(data.message || 'Không thể cập nhật phân quyền!', 'error');
            loadUsers();
            return;
        }
        showToast(data.message, 'success');
        loadUsers();
    } catch (e) {
        showToast('Lỗi kết nối khi cập nhật phân quyền!', 'error');
        loadUsers();
    }
}

async function toggleUserStatus(userId) {
    try {
        const res = await apiFetch(`/api/auth/users/${userId}/toggle`, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            closeModal('userStatusModal');
            showToast("Cập nhật trạng thái tài khoản thành công!");
            loadUsers();
        } else {
            showToast(data.message || "Lỗi cập nhật người dùng!", 'error');
        }
    } catch (e) {
        showToast("Lỗi cập nhật người dùng!", 'error');
    }
}

// ================= SETTINGS & GEMINI API KEY =================
async function loadSettingsStatus() {
    try {
        const res = await apiFetch('/api/settings');
        const data = await res.json();
        if (data.success) {
            document.getElementById('apiKeyStatusText').textContent = `Trạng thái: ${data.maskedKey}`;
        }
    } catch (e) {
        console.error("Lỗi kiểm tra cài đặt:", e);
    }
}

async function saveGeminiApiKey() {
    const key = document.getElementById('geminiApiKeyInput').value.trim();
    try {
        const res = await apiFetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ apiKey: key })
        });
        const data = await res.json();
        if (data.success) {
            showToast("Đã lưu Google Gemini API Key thành công!");
            closeModal('settingsModal');
            loadSettingsStatus();
        }
    } catch (e) {
        showToast("Lỗi lưu API Key!", 'error');
    }
}

// ================= CSV EXPORT (UC08) =================
function exportReportCSV() {
    window.location.href = '/api/reports/export/csv';
    showToast("Đang tải xuống báo cáo bán hàng định dạng CSV...", 'info');
}

// ================= EVENT LISTENERS =================
function setupEventListeners() {
    // POS Search
    const posSearch = document.getElementById('posSearchInput');
    if (posSearch) {
        posSearch.addEventListener('input', (e) => {
            const activePill = document.querySelector('#posCategoryPills .pill.active');
            const cat = activePill ? activePill.getAttribute('data-cat') : 'all';
            state.posPage = 1;
            renderPosProducts(cat, e.target.value);
        });
    }

    // Products Search & Filter
    const prodBrandFilter = document.getElementById('productBrandFilter');
    const prodCatFilter = document.getElementById('productCategoryFilter');
    const prodStockFilter = document.getElementById('productStockFilter');

    function applyProductTableFilters() {
        const brand = prodBrandFilter ? prodBrandFilter.value : 'all';
        const cat = prodCatFilter ? prodCatFilter.value : 'all';
        const stock = prodStockFilter ? prodStockFilter.value : 'all';

        let filtered = state.products;
        if (cat !== 'all') filtered = filtered.filter(p => p.CategoryID == cat);
        if (stock === 'in_stock') filtered = filtered.filter(p => p.StockQuantity > 0);
        if (stock === 'low_stock') filtered = filtered.filter(p => p.StockQuantity > 0 && p.StockQuantity <= p.MinThreshold);
        if (stock === 'out_of_stock') filtered = filtered.filter(p => p.StockQuantity <= 0);
        if (brand !== 'all') filtered = filtered.filter(p => p.Brand === brand);

        const tbody = document.getElementById('productsTableBody');
        if (tbody) {
            tbody.innerHTML = filtered.map(p => `
                <tr>
                    <td><strong>${p.ProductCode}</strong></td>
                    <td>
                        <div style="display:flex;align-items:center;gap:10px;">
                            <img src="${p.ImageURL || 'https://images.unsplash.com/photo-1593642632823-8f785ba67e45?w=100'}" style="width:42px;height:42px;border-radius:6px;object-fit:cover;">
                            <div>
                                <strong>${p.ProductName}</strong>
                                <div style="font-size:11px;color:var(--text-muted);">${p.CPU || ''} • ${p.RAM || ''}</div>
                            </div>
                        </div>
                    </td>
                    <td><span class="badge-pill">${p.CategoryName}</span></td>
                    <td>${formatVND(p.CostPrice)}</td>
                    <td><strong style="color:#38bdf8;">${formatVND(p.Price)}</strong></td>
                    <td>${p.StockQuantity} máy</td>
                    <td><span class="badge-status ${p.StockQuantity <= 0 ? 'out-of-stock' : (p.StockQuantity <= p.MinThreshold ? 'low-stock' : 'in-stock')}">${p.StockStatus}</span></td>
                    <td>
                        <button class="btn btn-sm btn-outline" onclick="deleteProduct(${p.ProductID})">
                            <i class="fa-solid fa-trash-can text-danger"></i>
                        </button>
                    </td>
                </tr>
            `).join('');
        }
    }

    if (prodBrandFilter) prodBrandFilter.addEventListener('change', applyProductTableFilters);
    if (prodCatFilter) prodCatFilter.addEventListener('change', applyProductTableFilters);
    if (prodStockFilter) prodStockFilter.addEventListener('change', applyProductTableFilters);

    const reportPeriod = document.getElementById('reportPeriod');
    if (reportPeriod) reportPeriod.addEventListener('change', updateCustomReportDates);

    // AI Tabs
    document.querySelectorAll('.ai-tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            switchAiTab(btn.getAttribute('data-tab'));
        });
    });

    const userSearchInput = document.getElementById('userSearchInput');
    if (userSearchInput) userSearchInput.addEventListener('input', event => {
        userManagementState.search = event.target.value.trim();
        userManagementState.page = 1;
        renderUsersTable();
    });
    const userRoleFilter = document.getElementById('userRoleFilter');
    if (userRoleFilter) userRoleFilter.addEventListener('change', event => {
        userManagementState.role = event.target.value;
        userManagementState.page = 1;
        renderUsersTable();
    });
    const userStatusFilter = document.getElementById('userStatusFilter');
    if (userStatusFilter) userStatusFilter.addEventListener('change', event => {
        userManagementState.status = event.target.value;
        userManagementState.page = 1;
        renderUsersTable();
    });

    // Chat Enter Key
    const chatInput = document.getElementById('chatQuestionInput');
    if (chatInput) {
        chatInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendChatQuestion();
        });
    }

    // POS Discount change
    const discInput = document.getElementById('posDiscountPercent');
    if (discInput) {
        discInput.addEventListener('input', () => renderCart());
    }

    // Payment method pills click
    document.querySelectorAll('.method-option').forEach(opt => {
        opt.addEventListener('click', () => {
            document.querySelectorAll('.method-option').forEach(o => o.classList.remove('active'));
            opt.classList.add('active');
            const radio = opt.querySelector('input');
            if (radio) radio.checked = true;
        });
    });

    // Settings Modal Trigger
    const settingsBtn = document.getElementById('openSettingsBtn');
    if (settingsBtn) {
        settingsBtn.addEventListener('click', () => openModal('settingsModal'));
    }
}
