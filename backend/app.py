import os
import sys
import json
import csv
import io
import hashlib
import hmac
import secrets
import re
from functools import wraps
from io import BytesIO
from datetime import datetime, timedelta, date
from flask import Flask, render_template, request, jsonify, Response, send_file, session
from database import get_db_connection, init_db, get_customer_group
from ai_service import (
    ai_product_advisor,
    ai_revenue_analyst,
    ai_sales_qa,
    ai_smart_query,
    get_api_key,
    save_api_key
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, 'frontend', 'templates'),
    static_folder=os.path.join(BASE_DIR, 'frontend', 'static')
)
app.config['SECRET_KEY'] = 'ban-hang-ai-ictu-2026-secret-key'

VALID_ROLES = {'Admin', 'Manager', 'Staff', 'Customer'}
PBKDF2_ITERATIONS = 260_000
PHONE_PATTERN = re.compile(r'^\d{10}$')
EMAIL_PATTERN = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')

def validate_contact_fields(phone='', email='', phone_required=False, email_required=False):
    if phone_required and not phone:
        return 'Số điện thoại là bắt buộc.'
    if email_required and not email:
        return 'Email là bắt buộc.'
    if phone and not PHONE_PATTERN.fullmatch(phone):
        return 'Số điện thoại phải gồm đúng 10 chữ số.'
    if email and not EMAIL_PATTERN.fullmatch(email):
        return 'Email không đúng định dạng, ví dụ: example@gmail.com.'
    return None

def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('ascii'), PBKDF2_ITERATIONS)
    return f'pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest.hex()}'

def verify_password(password, stored_password):
    if not stored_password:
        return False
    if not stored_password.startswith('pbkdf2_sha256$'):
        return hmac.compare_digest(password, stored_password)
    try:
        _, iterations, salt, expected = stored_password.split('$', 3)
        actual = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('ascii'), int(iterations)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False

# Ensure database exists
init_db()

@app.after_request
def add_cors_headers(response):
    origin = request.headers.get('Origin')
    allowed_origins = {
        'http://localhost:5000',
        'http://127.0.0.1:5000',
        'http://localhost:5500',
        'http://127.0.0.1:5500',
    }
    if origin in allowed_origins:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Vary'] = 'Origin'
    else:
        response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
    return response

@app.route('/api/<path:subpath>', methods=['OPTIONS'])
def handle_options(subpath):
    return '', 204

@app.before_request
def require_authentication():
    """Block business APIs until the user has an authenticated session."""
    if not request.path.startswith('/api/') or request.method == 'OPTIONS':
        return None

    public_paths = {
        '/api/auth/login',
        '/api/auth/register',
        '/api/auth/session',
        '/api/auth/logout',
    }
    if request.path in public_paths or session.get('user'):
        return None

    return jsonify({
        'success': False,
        'message': 'Vui lòng đăng nhập để tiếp tục!'
    }), 401

def require_roles(*roles):
    allowed_roles = set(roles)
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = session.get('user') or {}
            if user.get('Role') not in allowed_roles:
                return jsonify({
                    'success': False,
                    'message': 'Bạn không có quyền thực hiện chức năng này.'
                }), 403
            return view(*args, **kwargs)
        return wrapped
    return decorator

def require_any_authenticated(view):
    return require_roles('Admin', 'Manager', 'Staff', 'Customer')(view)

@app.route('/')
def index():
    return render_template('index.html')

# ==========================================
# AUTHENTICATION & USERS (UC01, UC12)
# ==========================================
def generate_next_customer_code(cursor):
    """Return the next sequential customer code from KH001 to KH999."""
    cursor.execute("SELECT CustomerCode FROM Customer")
    used_codes = {row['CustomerCode'] for row in cursor.fetchall()}
    for number in range(1, 1000):
        code = f"KH{number:03d}"
        if code not in used_codes:
            return code
    raise ValueError('Đã hết mã khách hàng trong khoảng KH001 đến KH999!')

def sync_account_to_customer(cursor, user_id, fullname, email, phone, address='Chưa cập nhật'):
    """Create a customer record for every newly created account."""
    if phone:
        cursor.execute('SELECT CustomerID FROM Customer WHERE Phone = ?', (phone,))
        existing_customer = cursor.fetchone()
        if existing_customer:
            if address and address != 'Chưa cập nhật':
                cursor.execute(
                    'UPDATE Customer SET CustomerName = ?, Email = ?, Address = ? WHERE CustomerID = ?',
                    (fullname, email, address, existing_customer['CustomerID'])
                )
            return existing_customer['CustomerID']

    customer_code = generate_next_customer_code(cursor)
    cursor.execute('''
    INSERT INTO Customer (CustomerCode, CustomerName, Phone, Email, Address, CustomerGroup)
    VALUES (?, ?, ?, ?, ?, 'Thân thiết')
    ''', (customer_code, fullname, phone, email, address or 'Chưa cập nhật'))
    return cursor.lastrowid

def get_customer_id_for_user(cursor, user):
    """Resolve a customer profile from the authenticated account without trusting client IDs."""
    phone = user.get('Phone', '')
    email = user.get('Email', '')
    if phone:
        cursor.execute('SELECT CustomerID FROM Customer WHERE Phone = ? LIMIT 1', (phone,))
    elif email:
        cursor.execute('SELECT CustomerID FROM Customer WHERE Email = ? LIMIT 1', (email,))
    else:
        cursor.execute('SELECT CustomerID FROM Customer WHERE CustomerName = ? LIMIT 1', (user.get('FullName', ''),))
    customer = cursor.fetchone()
    if customer:
        return customer['CustomerID']

    return sync_account_to_customer(
        cursor,
        user.get('UserID'),
        user.get('FullName', ''),
        email,
        phone
    )

def is_admin_session():
    return session.get('user', {}).get('Role') == 'Admin'

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT UserID, Username, FullName, Email, Phone, Role, Status, PasswordHash
    FROM UserAccount WHERE Username = ?
    ''', (username,))
    user = cursor.fetchone()

    if not user:
        conn.close()
        return jsonify({"success": False, "message": "Tên đăng nhập hoặc mật khẩu không chính xác!"}), 401
    
    user_dict = dict(user)
    if user_dict['Status'] != 1:
        conn.close()
        return jsonify({"success": False, "message": "Tài khoản này hiện đang bị tạm khóa!"}), 403

    if not verify_password(password, user_dict['PasswordHash']):
        conn.close()
        return jsonify({"success": False, "message": "Tên đăng nhập hoặc mật khẩu không chính xác!"}), 401

    if not user_dict['PasswordHash'].startswith('pbkdf2_sha256$'):
        cursor.execute('UPDATE UserAccount SET PasswordHash = ? WHERE UserID = ?', (hash_password(password), user_dict['UserID']))
        conn.commit()
    user_dict.pop('PasswordHash', None)
    conn.close()

    session['user'] = user_dict
    return jsonify({"success": True, "user": user_dict})

@app.route('/api/auth/session', methods=['GET'])
def auth_session():
    user = session.get('user')
    if not user:
        return jsonify({"success": False, "message": "Chưa đăng nhập!"}), 401
    return jsonify({"success": True, "user": user})

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"success": True, "message": "Đã đăng xuất khỏi hệ thống!"})

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    fullname = data.get('fullname', '').strip()
    email = data.get('email', '').strip()
    phone = data.get('phone', '').strip()
    address = data.get('address', '').strip()
    # Tài khoản đăng ký công khai luôn bắt đầu ở quyền Khách hàng.
    # Admin có thể nâng quyền sau trong màn hình Phân quyền.
    role = 'Customer'

    if not username or not password or not fullname or not address or not phone:
        return jsonify({"success": False, "message": "Vui lòng điền đầy đủ họ tên, số điện thoại, địa chỉ, tên đăng nhập và mật khẩu!"}), 400

    contact_error = validate_contact_fields(phone, email, phone_required=True, email_required=True)
    if contact_error:
        return jsonify({"success": False, "message": contact_error}), 400

    if len(password) < 6:
        return jsonify({"success": False, "message": "Mật khẩu phải có ít nhất 6 ký tự!"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # Kiểm tra trùng username
    cursor.execute('SELECT UserID FROM UserAccount WHERE Username = ?', (username,))
    if cursor.fetchone():
        conn.close()
        return jsonify({"success": False, "message": f"Tên đăng nhập '{username}' đã được sử dụng!"}), 400

    try:
        cursor.execute('''
        INSERT INTO UserAccount (Username, PasswordHash, FullName, Email, Phone, Role, Status)
        VALUES (?, ?, ?, ?, ?, ?, 1)
        ''', (username, hash_password(password), fullname, email, phone, role))
        user_id = cursor.lastrowid

        sync_account_to_customer(cursor, user_id, fullname, email, phone, address)

        conn.commit()

        cursor.execute('''
        SELECT UserID, Username, FullName, Email, Phone, Role, Status
        FROM UserAccount WHERE UserID = ?
        ''', (user_id,))
        new_user = dict(cursor.fetchone())
        conn.close()

        session['user'] = new_user

        return jsonify({
            "success": True,
            "user": new_user,
            "message": f"Đăng ký tài khoản '{username}' thành công!"
        })
    except Exception as e:
        conn.close()
        return jsonify({"success": False, "message": f"Lỗi đăng ký: {str(e)}"}), 500


@app.route('/api/auth/users', methods=['GET', 'POST'])
def manage_users():
    if not is_admin_session():
        return jsonify({"success": False, "message": "Chỉ Admin mới được quản lý tài khoản và phân quyền!"}), 403

    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        data = request.get_json() or {}
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        fullname = data.get('fullname', '').strip()
        email = data.get('email', '').strip()
        phone = data.get('phone', '').strip()
        role = data.get('role', 'Staff')
        if role not in ['Admin', 'Manager', 'Staff', 'Customer']:
            conn.close()
            return jsonify({"success": False, "message": "Vai trò không hợp lệ!"}), 400

        if not username or not fullname or not password:
            conn.close()
            return jsonify({"success": False, "message": "Vui lòng nhập tên đăng nhập, họ tên và mật khẩu!"}), 400
        contact_error = validate_contact_fields(phone, email, phone_required=True, email_required=True)
        if contact_error:
            conn.close()
            return jsonify({"success": False, "message": contact_error}), 400

        try:
            if len(password) < 6:
                conn.close()
                return jsonify({"success": False, "message": "Mật khẩu phải có ít nhất 6 ký tự!"}), 400
            cursor.execute('''
            INSERT INTO UserAccount (Username, PasswordHash, FullName, Email, Phone, Role)
            VALUES (?, ?, ?, ?, ?, ?)
            ''', (username, hash_password(password), fullname, email, phone, role))
            uid = cursor.lastrowid
            sync_account_to_customer(cursor, uid, fullname, email, phone)
            conn.commit()
            conn.close()
            return jsonify({"success": True, "message": "Tạo tài khoản thành công!", "userId": uid})
        except Exception as e:
            conn.close()
            return jsonify({"success": False, "message": f"Tên đăng nhập '{username}' đã tồn tại!"}), 400

    cursor.execute('''
    SELECT UserID, Username, FullName, Email, Phone, Role, Status, CreatedAt
    FROM UserAccount
    ORDER BY UserID ASC
    ''')
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"success": True, "users": users})

@app.route('/api/auth/users/<int:user_id>/role', methods=['POST'])
def update_user_role(user_id):
    if not is_admin_session():
        return jsonify({"success": False, "message": "Chỉ Admin mới được thay đổi phân quyền!"}), 403

    data = request.get_json() or {}
    role = data.get('role', '').strip()
    valid_roles = ['Admin', 'Manager', 'Staff', 'Customer']
    role_labels = {
        'Admin': 'Admin',
        'Manager': 'Quản lý',
        'Staff': 'Nhân viên',
        'Customer': 'Khách hàng'
    }
    if role not in valid_roles:
        return jsonify({"success": False, "message": "Vai trò không hợp lệ!"}), 400

    current_user_id = session['user']['UserID']
    if user_id == current_user_id:
        return jsonify({"success": False, "message": "Không thể tự thay đổi quyền của tài khoản đang đăng nhập!"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT UserID, Role FROM UserAccount WHERE UserID = ?', (user_id,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return jsonify({"success": False, "message": "Không tìm thấy tài khoản!"}), 404

    if user['Role'] == 'Admin' and role != 'Admin':
        cursor.execute("SELECT COUNT(*) AS AdminCount FROM UserAccount WHERE Role = 'Admin' AND Status = 1")
        if cursor.fetchone()['AdminCount'] <= 1:
            conn.close()
            return jsonify({"success": False, "message": "Không thể hạ quyền Admin cuối cùng đang hoạt động!"}), 400

    cursor.execute('UPDATE UserAccount SET Role = ? WHERE UserID = ?', (role, user_id))
    conn.commit()
    conn.close()
    return jsonify({
        "success": True,
        "userId": user_id,
        "role": role,
        "roleLabel": role_labels[role],
        "message": f"Đã cập nhật quyền thành {role_labels[role]}!"
    })

@app.route('/api/auth/users/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    if not is_admin_session():
        return jsonify({"success": False, "message": "Chỉ Admin mới được sửa tài khoản!"}), 403

    data = request.get_json() or {}
    fullname = data.get('fullname', '').strip()
    email = data.get('email', '').strip()
    phone = data.get('phone', '').strip()
    role = data.get('role', '').strip()
    valid_roles = ['Admin', 'Manager', 'Staff', 'Customer']
    if not fullname or role not in valid_roles:
        return jsonify({"success": False, "message": "Họ tên và vai trò không hợp lệ!"}), 400
    contact_error = validate_contact_fields(phone, email, phone_required=True, email_required=True)
    if contact_error:
        return jsonify({"success": False, "message": contact_error}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT UserID, Role FROM UserAccount WHERE UserID = ?', (user_id,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return jsonify({"success": False, "message": "Không tìm thấy tài khoản!"}), 404

    if user_id == session['user']['UserID'] and role != 'Admin':
        conn.close()
        return jsonify({"success": False, "message": "Không thể tự hạ quyền tài khoản đang đăng nhập!"}), 400

    if user['Role'] == 'Admin' and role != 'Admin':
        cursor.execute("SELECT COUNT(*) AS AdminCount FROM UserAccount WHERE Role = 'Admin' AND Status = 1")
        if cursor.fetchone()['AdminCount'] <= 1:
            conn.close()
            return jsonify({"success": False, "message": "Không thể hạ quyền Admin cuối cùng đang hoạt động!"}), 400

    cursor.execute('''
        UPDATE UserAccount
        SET FullName = ?, Email = ?, Phone = ?, Role = ?
        WHERE UserID = ?
    ''', (fullname, email, phone, role, user_id))
    new_password = data.get('password', '').strip()
    if new_password:
        if len(new_password) < 6:
            conn.close()
            return jsonify({"success": False, "message": "Mật khẩu mới phải có ít nhất 6 ký tự!"}), 400
        cursor.execute('UPDATE UserAccount SET PasswordHash = ? WHERE UserID = ?', (hash_password(new_password), user_id))
    conn.commit()
    cursor.execute('''
        SELECT UserID, Username, FullName, Email, Phone, Role, Status, CreatedAt
        FROM UserAccount WHERE UserID = ?
    ''', (user_id,))
    updated_user = dict(cursor.fetchone())
    conn.close()
    return jsonify({"success": True, "user": updated_user, "message": "Đã cập nhật tài khoản!"})

@app.route('/api/auth/users/<int:user_id>/toggle', methods=['POST'])
def toggle_user(user_id):
    if not is_admin_session():
        return jsonify({"success": False, "message": "Chỉ Admin mới được khóa hoặc mở khóa tài khoản!"}), 403

    if user_id == session['user']['UserID']:
        return jsonify({"success": False, "message": "Không thể tự khóa tài khoản đang đăng nhập!"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT Status FROM UserAccount WHERE UserID = ?', (user_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({"success": False, "message": "Không tìm thấy người dùng!"}), 404

    new_status = 0 if row['Status'] == 1 else 1
    cursor.execute('UPDATE UserAccount SET Status = ? WHERE UserID = ?', (new_status, user_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "newStatus": new_status})

# ==========================================
# CATEGORIES & PRODUCTS (UC02, UC06)
# ==========================================
@app.route('/api/categories', methods=['GET', 'POST'])
@require_any_authenticated
def get_categories():
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        if session['user']['Role'] not in {'Admin', 'Manager', 'Staff'}:
            conn.close()
            return jsonify({"success": False, "message": "Bạn không có quyền thêm danh mục!"}), 403
        data = request.get_json() or {}
        name = data.get('categoryName', '').strip()
        desc = data.get('description', '').strip()
        if not name:
            conn.close()
            return jsonify({"success": False, "message": "Tên danh mục không được để trống!"}), 400
        cursor.execute('INSERT INTO Category (CategoryName, Description) VALUES (?, ?)', (name, desc))
        conn.commit()
        cid = cursor.lastrowid
        conn.close()
        return jsonify({"success": True, "categoryId": cid})

    cursor.execute('SELECT * FROM Category WHERE Status = 1')
    cats = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"success": True, "categories": cats})

@app.route('/api/products', methods=['GET', 'POST'])
@require_any_authenticated
def get_products():
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        if session['user']['Role'] not in {'Admin', 'Manager', 'Staff'}:
            conn.close()
            return jsonify({"success": False, "message": "Bạn không có quyền thêm sản phẩm!"}), 403
        data = request.get_json() or {}
        cat_id = data.get('categoryId')
        pcode = data.get('productCode', '').strip() or f"LT-{datetime.now().strftime('%m%d%H%M')}"
        pname = data.get('productName', '').strip()
        brand = data.get('brand', '').strip()
        cpu = data.get('cpu', '')
        ram = data.get('ram', '')
        storage = data.get('storage', '')
        gpu = data.get('gpu', '')
        screen = data.get('screen', '')
        cost = float(data.get('costPrice', 0))
        price = float(data.get('price', 0))
        desc = data.get('description', '')
        img = data.get('imageUrl', 'https://images.unsplash.com/photo-1593642632823-8f785ba67e45?w=500')
        init_qty = int(data.get('quantity', 5))
        min_th = int(data.get('minThreshold', 3))

        if not pname or not cat_id or price <= 0:
            conn.close()
            return jsonify({"success": False, "message": "Vui lòng nhập đầy đủ tên, danh mục và giá bán hợp lệ!"}), 400

        try:
            cursor.execute('''
            INSERT INTO Product (CategoryID, ProductCode, ProductName, Brand, CPU, RAM, Storage, GPU, Screen, CostPrice, Price, Description, ImageURL)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (cat_id, pcode, pname, brand, cpu, ram, storage, gpu, screen, cost, price, desc, img))
            pid = cursor.lastrowid

            cursor.execute('''
            INSERT INTO Inventory (ProductID, Quantity, MinThreshold)
            VALUES (?, ?, ?)
            ''', (pid, init_qty, min_th))
            conn.commit()
            conn.close()
            return jsonify({"success": True, "productId": pid, "message": "Thêm sản phẩm thành công!"})
        except Exception as e:
            conn.close()
            return jsonify({"success": False, "message": f"Mã sản phẩm '{pcode}' có thể đã tồn tại!"}), 400

    # GET Filtered products
    cat_filter = request.args.get('category')
    search = request.args.get('search', '').strip()
    in_stock = request.args.get('in_stock')

    sql = '''
    SELECT p.*, c.CategoryName, i.Quantity AS StockQuantity, i.MinThreshold,
           CASE 
             WHEN i.Quantity = 0 THEN 'Hết hàng'
             WHEN i.Quantity <= i.MinThreshold THEN 'Sắp hết hàng'
             ELSE 'Còn hàng'
           END AS StockStatus
    FROM Product p
    JOIN Category c ON p.CategoryID = c.CategoryID
    JOIN Inventory i ON p.ProductID = i.ProductID
    WHERE p.Status = 1
    '''
    params = []

    if cat_filter and cat_filter != 'all':
        sql += ' AND p.CategoryID = ?'
        params.append(cat_filter)

    if search:
        sql += ' AND (p.ProductName LIKE ? OR p.ProductCode LIKE ? OR p.Brand LIKE ? OR p.Description LIKE ?)'
        wild = f"%{search}%"
        params.extend([wild, wild, wild, wild])

    if in_stock == 'true':
        sql += ' AND i.Quantity > 0'

    sql += ' ORDER BY p.ProductID DESC'
    cursor.execute(sql, params)
    prods = [dict(row) for row in cursor.fetchall()]
    conn.close()
    if session['user']['Role'] == 'Customer':
        for product in prods:
            product.pop('CostPrice', None)
            product.pop('MinThreshold', None)
    return jsonify({"success": True, "products": prods})

@app.route('/api/products/<int:product_id>', methods=['GET', 'PUT', 'DELETE'])
@require_any_authenticated
def single_product(product_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'DELETE':
        if session['user']['Role'] not in {'Admin', 'Manager', 'Staff'}:
            conn.close()
            return jsonify({"success": False, "message": "Bạn không có quyền xóa sản phẩm!"}), 403
        cursor.execute('UPDATE Product SET Status = 0 WHERE ProductID = ?', (product_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Đã chuyển sản phẩm vào trạng thái ngừng kinh doanh!"})

    if request.method == 'PUT':
        if session['user']['Role'] not in {'Admin', 'Manager', 'Staff'}:
            conn.close()
            return jsonify({"success": False, "message": "Bạn không có quyền sửa sản phẩm!"}), 403
        data = request.get_json() or {}
        cursor.execute('''
        UPDATE Product
        SET CategoryID = ?, ProductName = ?, Brand = ?, CPU = ?, RAM = ?, Storage = ?,
            GPU = ?, Screen = ?, CostPrice = ?, Price = ?, Description = ?, ImageURL = ?
        WHERE ProductID = ?
        ''', (
            data.get('categoryId'), data.get('productName'), data.get('brand'),
            data.get('cpu'), data.get('ram'), data.get('storage'), data.get('gpu'),
            data.get('screen'), data.get('costPrice'), data.get('price'),
            data.get('description'), data.get('imageUrl'), product_id
        ))
        if 'minThreshold' in data or 'quantity' in data:
            cursor.execute('''
            UPDATE Inventory
            SET Quantity = COALESCE(?, Quantity),
                MinThreshold = COALESCE(?, MinThreshold),
                LastUpdated = CURRENT_TIMESTAMP
            WHERE ProductID = ?
            ''', (data.get('quantity'), data.get('minThreshold'), product_id))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Cập nhật sản phẩm thành công!"})

    cursor.execute('''
    SELECT p.*, c.CategoryName, i.Quantity, i.MinThreshold
    FROM Product p
    JOIN Category c ON p.CategoryID = c.CategoryID
    JOIN Inventory i ON p.ProductID = i.ProductID
    WHERE p.ProductID = ?
    ''', (product_id,))
    p = cursor.fetchone()
    conn.close()
    if not p:
        return jsonify({"success": False, "message": "Không tìm thấy sản phẩm!"}), 404
    product = dict(p)
    if session['user']['Role'] == 'Customer':
        product.pop('CostPrice', None)
        product.pop('MinThreshold', None)
    return jsonify({"success": True, "product": product})

# ==========================================
# CUSTOMERS (UC03)
# ==========================================
@app.route('/api/customers', methods=['GET', 'POST'])
@require_roles('Admin', 'Manager', 'Staff')
def manage_customers():
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        if session['user']['Role'] not in {'Admin', 'Manager'}:
            conn.close()
            return jsonify({"success": False, "message": "Bạn không có quyền thêm khách hàng!"}), 403
        data = request.get_json() or {}
        name = data.get('customerName', '').strip()
        phone = data.get('phone', '').strip()
        email = data.get('email', '').strip()
        addr = data.get('address', '').strip()
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()

        if not name or not phone or not username or not password:
            conn.close()
            return jsonify({"success": False, "message": "Họ tên, số điện thoại, tên đăng nhập và mật khẩu là bắt buộc!"}), 400
        if len(password) < 6:
            conn.close()
            return jsonify({"success": False, "message": "Mật khẩu phải có ít nhất 6 ký tự!"}), 400
        contact_error = validate_contact_fields(phone, email, phone_required=True, email_required=True)
        if contact_error:
            conn.close()
            return jsonify({"success": False, "message": contact_error}), 400
        cursor.execute('SELECT UserID FROM UserAccount WHERE Username = ?', (username,))
        if cursor.fetchone():
            conn.close()
            return jsonify({"success": False, "message": "Tên đăng nhập đã tồn tại!"}), 400
        cursor.execute('SELECT CustomerID FROM Customer WHERE Phone = ?', (phone,))
        if cursor.fetchone():
            conn.close()
            return jsonify({"success": False, "message": "Số điện thoại đã thuộc về khách hàng khác!"}), 400
        try:
            code = generate_next_customer_code(cursor)
            cursor.execute('''
            INSERT INTO UserAccount (Username, PasswordHash, FullName, Email, Phone, Role, Status)
            VALUES (?, ?, ?, ?, ?, 'Customer', 1)
            ''', (username, hash_password(password), name, email, phone))
            account_id = cursor.lastrowid
            cursor.execute('''
            INSERT INTO Customer (CustomerCode, CustomerName, Phone, Email, Address)
            VALUES (?, ?, ?, ?, ?)
            ''', (code, name, phone, email, addr))
            cid = cursor.lastrowid
            conn.commit()
            conn.close()
            return jsonify({"success": True, "customerId": cid, "accountId": account_id, "message": "Đã tạo khách hàng và tài khoản Customer thành công!"})
        except Exception as error:
            conn.rollback()
            conn.close()
            return jsonify({"success": False, "message": f"Không thể tạo khách hàng: {error}"}), 400

    search = request.args.get('search', '').strip()
    sql = '''
    SELECT c.*,
           EXISTS(
               SELECT 1 FROM UserAccount u
               WHERE u.Role = 'Customer'
                 AND ((c.Phone <> '' AND u.Phone = c.Phone)
                      OR (c.Email <> '' AND u.Email = c.Email))
           ) AS HasAccount
    FROM Customer c WHERE 1=1
    '''
    params = []
    if search:
        sql += ' AND (CustomerName LIKE ? OR Phone LIKE ? OR CustomerCode LIKE ?)'
        w = f"%{search}%"
        params.extend([w, w, w])

    sql += ' ORDER BY CustomerID DESC'
    cursor.execute(sql, params)
    customers = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"success": True, "customers": customers})

@app.route('/api/customers/<int:customer_id>/account', methods=['POST'])
@require_roles('Admin', 'Manager')
def create_customer_account(customer_id):
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    if not username or not password:
        return jsonify({"success": False, "message": "Vui lòng nhập tên đăng nhập và mật khẩu!"}), 400
    if len(password) < 6:
        return jsonify({"success": False, "message": "Mật khẩu phải có ít nhất 6 ký tự!"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM Customer WHERE CustomerID = ?', (customer_id,))
    customer = cursor.fetchone()
    if not customer:
        conn.close()
        return jsonify({"success": False, "message": "Không tìm thấy khách hàng!"}), 404
    cursor.execute('SELECT UserID FROM UserAccount WHERE Username = ?', (username,))
    if cursor.fetchone():
        conn.close()
        return jsonify({"success": False, "message": "Tên đăng nhập đã tồn tại!"}), 400
    cursor.execute('''
        SELECT UserID FROM UserAccount
        WHERE Role = 'Customer' AND ((Phone <> '' AND Phone = ?) OR (Email <> '' AND Email = ?))
    ''', (customer['Phone'], customer['Email']))
    if cursor.fetchone():
        conn.close()
        return jsonify({"success": False, "message": "Khách hàng này đã có tài khoản!"}), 400
    cursor.execute('''
        INSERT INTO UserAccount (Username, PasswordHash, FullName, Email, Phone, Role, Status)
        VALUES (?, ?, ?, ?, ?, 'Customer', 1)
    ''', (username, hash_password(password), customer['CustomerName'], customer['Email'], customer['Phone']))
    conn.commit()
    account_id = cursor.lastrowid
    conn.close()
    return jsonify({"success": True, "accountId": account_id, "message": "Đã tạo tài khoản Customer thành công!"})

@app.route('/api/customers/<int:customer_id>', methods=['PUT'])
@require_roles('Admin', 'Manager')
def update_customer(customer_id):
    data = request.get_json() or {}
    name = data.get('customerName', '').strip()
    phone = data.get('phone', '').strip()
    email = data.get('email', '').strip()
    addr = data.get('address', '').strip()

    if not name or not phone:
        return jsonify({"success": False, "message": "Họ tên và số điện thoại là bắt buộc!"}), 400
    contact_error = validate_contact_fields(phone, email, phone_required=True, email_required=True)
    if contact_error:
        return jsonify({"success": False, "message": contact_error}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM Customer WHERE CustomerID = ?', (customer_id,))
    existing_customer = cursor.fetchone()
    if not existing_customer:
        conn.close()
        return jsonify({"success": False, "message": "Không tìm thấy khách hàng!"}), 404

    cursor.execute('''
        SELECT CustomerID FROM Customer
        WHERE Phone = ? AND CustomerID <> ?
    ''', (phone, customer_id))
    if cursor.fetchone():
        conn.close()
        return jsonify({"success": False, "message": "Số điện thoại đã thuộc về khách hàng khác!"}), 400

    cursor.execute('''
        UPDATE Customer
        SET CustomerName = ?, Phone = ?, Email = ?, Address = ?
        WHERE CustomerID = ?
    ''', (name, phone, email, addr, customer_id))
    cursor.execute('''
        UPDATE UserAccount
        SET FullName = ?, Phone = ?, Email = ?
        WHERE Role = 'Customer'
          AND ((Phone <> '' AND Phone = ?) OR (Email <> '' AND Email = ?))
    ''', (name, phone, email, existing_customer['Phone'], existing_customer['Email']))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Cập nhật thông tin khách hàng thành công!"})

# ==========================================
# INVOICES & POS COUNTER (UC04)
# ==========================================
@app.route('/api/invoices', methods=['GET', 'POST'])
@require_roles('Admin', 'Manager', 'Staff', 'Customer')
def manage_invoices():
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        data = request.get_json() or {}
        items = data.get('items', [])
        is_customer = session['user']['Role'] == 'Customer'
        cust_id = get_customer_id_for_user(cursor, session['user']) if is_customer else data.get('customerId')
        user_id = session['user']['UserID']
        method = data.get('paymentMethod', 'Tiền mặt')
        disc_pct = 0 if is_customer else float(data.get('discountPercent', 0))
        notes = data.get('notes', '')

        # Kiểm tra giới hạn giảm giá theo kết quả khảo sát mục 2.1.2:
        # Nhân viên chỉ được chiết khấu trong khung <= 10%, nếu cao hơn cần duyệt
        if disc_pct > 15:
            conn.close()
            return jsonify({"success": False, "message": "Mức chiết khấu vượt quá khung quy định (tối đa 15%)!"}), 400

        if not items:
            conn.close()
            return jsonify({"success": False, "message": "Hóa đơn phải có ít nhất 1 sản phẩm!"}), 400

        # Kiểm tra tồn kho cho từng sản phẩm trước khi tạo đơn
        subtotal = 0
        validated_items = []
        for item in items:
            pid = item.get('productId')
            qty = int(item.get('quantity', 1))
            cursor.execute('''
            SELECT p.ProductID, p.ProductName, p.Price, i.Quantity AS Stock
            FROM Product p
            JOIN Inventory i ON p.ProductID = i.ProductID
            WHERE p.ProductID = ?
            ''', (pid,))
            prod = cursor.fetchone()
            if not prod:
                conn.close()
                return jsonify({"success": False, "message": f"Sản phẩm ID {pid} không tồn tại!"}), 400
            if prod['Stock'] < qty:
                conn.close()
                return jsonify({
                    "success": False,
                    "message": f"Sản phẩm '{prod['ProductName']}' không đủ tồn kho! (Hiện còn {prod['Stock']} máy, yêu cầu {qty})"
                }), 400
            
            line_sub = prod['Price'] * qty
            subtotal += line_sub
            validated_items.append({
                "productId": pid,
                "quantity": qty,
                "unitPrice": prod['Price'],
                "subTotal": line_sub
            })

        disc_amt = (subtotal * disc_pct) / 100.0
        final_total = subtotal - disc_amt
        inv_code = f"HD-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        # 1. Lưu hóa đơn
        cursor.execute('''
        INSERT INTO Invoice (InvoiceCode, CustomerID, UserID, SubTotal, DiscountPercent, DiscountAmount, TotalAmount, PaymentMethod, Notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (inv_code, cust_id, user_id, subtotal, disc_pct, disc_amt, final_total, method, notes))
        inv_id = cursor.lastrowid

        # 2. Lưu chi tiết & Trừ tồn kho
        for it in validated_items:
            cursor.execute('''
            INSERT INTO InvoiceDetail (InvoiceID, ProductID, Quantity, UnitPrice, SubTotal)
            VALUES (?, ?, ?, ?, ?)
            ''', (inv_id, it['productId'], it['quantity'], it['unitPrice'], it['subTotal']))

            cursor.execute('''
            UPDATE Inventory
            SET Quantity = Quantity - ?, LastUpdated = CURRENT_TIMESTAMP
            WHERE ProductID = ?
            ''', (it['quantity'], it['productId']))

        # 3. Cập nhật doanh số tích lũy cho khách hàng
        if cust_id:
            cursor.execute('''
            UPDATE Customer
            SET TotalSpent = TotalSpent + ?
            WHERE CustomerID = ?
            ''', (final_total, cust_id))

            # Tự động cập nhật hạng theo tổng chi tiêu tích lũy.
            cursor.execute('''
            UPDATE Customer
            SET CustomerGroup = ?
            WHERE CustomerID = ?
            ''', (get_customer_group(
                cursor.execute('SELECT TotalSpent FROM Customer WHERE CustomerID = ?', (cust_id,)).fetchone()['TotalSpent'],
            ), cust_id))

        conn.commit()
        conn.close()

        # Tạo chuỗi VietQR chuẩn để khách quét qua app ngân hàng
        vietqr_url = f"https://img.vietqr.io/image/MB-0987654321-compact2.png?amount={int(final_total)}&addInfo={inv_code}&accountName=NGUYEN%20DINH%20BANG"

        return jsonify({
            "success": True,
            "invoiceId": inv_id,
            "invoiceCode": inv_code,
            "totalAmount": final_total,
            "paymentMethod": method,
            "vietQrUrl": vietqr_url,
            "message": "Lập hóa đơn và thanh toán thành công!"
        })

    # GET Invoices list
    invoice_filter = ''
    invoice_params = []
    if session['user']['Role'] == 'Customer':
        customer_id = get_customer_id_for_user(cursor, session['user'])
        invoice_filter = 'WHERE inv.CustomerID = ?'
        invoice_params.append(customer_id)

    cursor.execute(f'''
    SELECT inv.*, 
           COALESCE(c.CustomerName, 'Khách lẻ vãng lai') AS CustomerName,
           COALESCE(c.Phone, '') AS CustomerPhone,
           u.FullName AS StaffName,
           (SELECT COUNT(*) FROM InvoiceDetail WHERE InvoiceID = inv.InvoiceID) AS TotalItems
    FROM Invoice inv
    LEFT JOIN Customer c ON inv.CustomerID = c.CustomerID
    JOIN UserAccount u ON inv.UserID = u.UserID
    {invoice_filter}
    ORDER BY inv.InvoiceID DESC
    ''', invoice_params)
    invoices = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"success": True, "invoices": invoices})

@app.route('/api/invoices/<int:invoice_id>', methods=['GET'])
@require_roles('Admin', 'Manager', 'Staff')
def get_invoice_detail(invoice_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
    SELECT inv.*, 
           COALESCE(c.CustomerName, 'Khách lẻ vãng lai') AS CustomerName,
           COALESCE(c.Phone, 'Không có') AS CustomerPhone,
           COALESCE(c.Address, 'Không có') AS CustomerAddress,
           u.FullName AS StaffName
    FROM Invoice inv
    LEFT JOIN Customer c ON inv.CustomerID = c.CustomerID
    JOIN UserAccount u ON inv.UserID = u.UserID
    WHERE inv.InvoiceID = ?
    ''', (invoice_id,))
    inv = cursor.fetchone()
    if not inv:
        conn.close()
        return jsonify({"success": False, "message": "Không tìm thấy hóa đơn!"}), 404

    cursor.execute('''
    SELECT d.*, p.ProductName, p.ProductCode, p.Brand, p.CPU, p.RAM
    FROM InvoiceDetail d
    JOIN Product p ON d.ProductID = p.ProductID
    WHERE d.InvoiceID = ?
    ''', (invoice_id,))
    details = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify({
        "success": True,
        "invoice": dict(inv),
        "items": details
    })

# ==========================================
# INVENTORY & IMPORTS (UC05)
# ==========================================
@app.route('/api/inventory', methods=['GET'])
@require_roles('Admin', 'Manager', 'Staff', 'Customer')
def get_inventory():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT i.*, p.ProductName, p.ProductCode, p.Brand, p.Price, p.CostPrice, c.CategoryName,
           CASE 
             WHEN i.Quantity = 0 THEN 'Hết hàng'
             WHEN i.Quantity <= i.MinThreshold THEN 'Sắp hết hàng'
             ELSE 'Đủ hàng'
           END AS AlertStatus
    FROM Inventory i
    JOIN Product p ON i.ProductID = p.ProductID
    JOIN Category c ON p.CategoryID = c.CategoryID
    WHERE p.Status = 1
    ORDER BY i.Quantity ASC
    ''')
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    if session['user']['Role'] == 'Customer':
        for item in items:
            item.pop('CostPrice', None)
            item.pop('MinThreshold', None)
            item.pop('AlertStatus', None)
    return jsonify({"success": True, "inventory": items})

@app.route('/api/suppliers', methods=['GET', 'POST'])
@require_roles('Admin', 'Manager', 'Staff')
def manage_suppliers():
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        data = request.get_json() or {}
        name = data.get('supplierName', '').strip()
        phone = data.get('phone', '').strip()
        email = data.get('email', '').strip()
        addr = data.get('address', '').strip()
        if not name:
            conn.close()
            return jsonify({"success": False, "message": "Tên nhà cung cấp là bắt buộc!"}), 400
        contact_error = validate_contact_fields(phone, email)
        if contact_error:
            conn.close()
            return jsonify({"success": False, "message": contact_error}), 400
        cursor.execute('''
        INSERT INTO Supplier (SupplierName, Phone, Email, Address)
        VALUES (?, ?, ?, ?)
        ''', (name, phone, email, addr))
        conn.commit()
        sid = cursor.lastrowid
        conn.close()
        return jsonify({"success": True, "supplierId": sid, "message": "Thêm nhà cung cấp thành công!"})

    cursor.execute('SELECT * FROM Supplier WHERE Status = 1')
    suppliers = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"success": True, "suppliers": suppliers})

@app.route('/api/imports', methods=['GET', 'POST'])
@require_roles('Admin', 'Manager', 'Staff')
def manage_imports():
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        data = request.get_json() or {}
        supp_id = data.get('supplierId')
        user_id = session['user']['UserID']
        items = data.get('items', [])

        if not supp_id or not items:
            conn.close()
            return jsonify({"success": False, "message": "Vui lòng chọn nhà cung cấp và ít nhất 1 sản phẩm nhập!"}), 400

        total_amount = sum(float(item.get('unitPrice', 0)) * int(item.get('quantity', 0)) for item in items)
        imp_code = f"PN-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        cursor.execute('''
        INSERT INTO ImportReceipt (ImportCode, SupplierID, UserID, TotalAmount, Status)
        VALUES (?, ?, ?, ?, 'Đã nhập kho')
        ''', (imp_code, supp_id, user_id, total_amount))
        imp_id = cursor.lastrowid

        for it in items:
            pid = it['productId']
            qty = int(it['quantity'])
            price = float(it['unitPrice'])
            sub = qty * price

            cursor.execute('''
            INSERT INTO ImportDetail (ImportID, ProductID, Quantity, UnitPrice, SubTotal)
            VALUES (?, ?, ?, ?, ?)
            ''', (imp_id, pid, qty, price, sub))

            # Tăng tồn kho
            cursor.execute('''
            UPDATE Inventory
            SET Quantity = Quantity + ?, LastUpdated = CURRENT_TIMESTAMP
            WHERE ProductID = ?
            ''', (qty, pid))

            # Cập nhật giá nhập mới nhất cho sản phẩm
            cursor.execute('''
            UPDATE Product SET CostPrice = ? WHERE ProductID = ?
            ''', (price, pid))

        conn.commit()
        conn.close()
        return jsonify({"success": True, "importId": imp_id, "message": "Nhập hàng và cập nhật tồn kho thành công!"})

    cursor.execute('''
    SELECT r.*, s.SupplierName, u.FullName AS StaffName,
           (SELECT COUNT(*) FROM ImportDetail WHERE ImportID = r.ImportID) AS TotalItems
    FROM ImportReceipt r
    JOIN Supplier s ON r.SupplierID = s.SupplierID
    JOIN UserAccount u ON r.UserID = u.UserID
    ORDER BY r.ImportID DESC
    ''')
    receipts = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"success": True, "imports": receipts})

# ==========================================
# REPORTS & DASHBOARD (UC07, UC08)
# ==========================================
def get_report_period(args):
    """Return an inclusive start and exclusive end for a report period."""
    period = args.get('period', 'all')
    anchor_text = args.get('date') or datetime.now().strftime('%Y-%m-%d')
    try:
        anchor = datetime.strptime(anchor_text, '%Y-%m-%d').date()
    except ValueError:
        anchor = datetime.now().date()

    if period == 'day':
        start = anchor
        end = start + timedelta(days=1)
    elif period == 'week':
        start = anchor - timedelta(days=anchor.weekday())
        end = start + timedelta(days=7)
    elif period == 'month':
        start = anchor.replace(day=1)
        end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    elif period == 'quarter':
        start_month = ((anchor.month - 1) // 3) * 3 + 1
        start = anchor.replace(month=start_month, day=1)
        end_month = start_month + 3
        end = anchor.replace(year=anchor.year + (end_month - 1) // 12, month=(end_month - 1) % 12 + 1, day=1)
    elif period == 'year':
        start = anchor.replace(month=1, day=1)
        end = start.replace(year=start.year + 1)
    elif period == 'custom':
        try:
            start = datetime.strptime(args.get('from', ''), '%Y-%m-%d').date()
            end = datetime.strptime(args.get('to', ''), '%Y-%m-%d').date() + timedelta(days=1)
            if end <= start:
                raise ValueError
        except ValueError:
            start = anchor.replace(day=1)
            end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
            period = 'month'
    else:
        return None, None, 'all'

    return start, end, period

def report_date_clause(start, end, column='inv.InvoiceDate'):
    if start is None or end is None:
        return '', []
    return f' AND {column} >= ? AND {column} < ?', [start.isoformat(), end.isoformat()]

def get_report_data(args):
    start, end, period = get_report_period(args)
    date_clause, date_params = report_date_clause(start, end)
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(f'''
        SELECT COUNT(*) AS InvoiceCount, COALESCE(SUM(inv.TotalAmount), 0) AS Revenue
        FROM Invoice inv
        WHERE inv.Status = 'Hoàn thành'{date_clause}
    ''', date_params)
    summary = dict(cursor.fetchone())

    cursor.execute(f'''
        SELECT inv.InvoiceID, inv.InvoiceCode, inv.InvoiceDate,
               COALESCE(c.CustomerName, 'Khách vãng lai') AS CustomerName,
               COALESCE(u.FullName, 'Không xác định') AS StaffName,
               inv.SubTotal, inv.DiscountAmount, inv.TotalAmount,
               inv.PaymentMethod,
               COALESCE(SUM(d.Quantity), 0) AS TotalItems
        FROM Invoice inv
        LEFT JOIN Customer c ON inv.CustomerID = c.CustomerID
        LEFT JOIN UserAccount u ON inv.UserID = u.UserID
        LEFT JOIN InvoiceDetail d ON inv.InvoiceID = d.InvoiceID
        WHERE inv.Status = 'Hoàn thành'{date_clause}
        GROUP BY inv.InvoiceID
        ORDER BY inv.InvoiceDate DESC, inv.InvoiceID DESC
    ''', date_params)
    invoices = [dict(row) for row in cursor.fetchall()]

    cursor.execute(f'''
        SELECT p.ProductName, p.Brand, SUM(d.Quantity) AS QtySold,
               SUM(d.SubTotal) AS Revenue
        FROM InvoiceDetail d
        JOIN Invoice inv ON d.InvoiceID = inv.InvoiceID
        JOIN Product p ON d.ProductID = p.ProductID
        WHERE inv.Status = 'Hoàn thành'{date_clause}
        GROUP BY d.ProductID
        ORDER BY QtySold DESC, Revenue DESC
        LIMIT 10
    ''', date_params)
    top_products = [dict(row) for row in cursor.fetchall()]

    cursor.execute(f'''
        SELECT p.Brand, SUM(d.Quantity) AS QuantitySold
        FROM InvoiceDetail d
        JOIN Invoice inv ON d.InvoiceID = inv.InvoiceID
        JOIN Product p ON d.ProductID = p.ProductID
        WHERE inv.Status = 'Hoàn thành'{date_clause}
        GROUP BY p.Brand
        ORDER BY QuantitySold DESC
    ''', date_params)
    brands = [dict(row) for row in cursor.fetchall()]
    conn.close()

    chart_labels = []
    chart_values = []
    if start and end:
        cursor_date = start
        while cursor_date < end and len(chart_labels) < 31:
            next_date = cursor_date + timedelta(days=1)
            label = cursor_date.strftime('%d/%m')
            chart_labels.append(label)
            chart_values.append(sum(
                invoice['TotalAmount'] for invoice in invoices
                if invoice['InvoiceDate'][:10] == cursor_date.isoformat()
            ))
            cursor_date = next_date
        if end - start > timedelta(days=31):
            chart_labels = []
            chart_values = []
            month = start.replace(day=1)
            while month < end:
                next_month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
                chart_labels.append(month.strftime('%m/%Y'))
                chart_values.append(sum(
                    invoice['TotalAmount'] for invoice in invoices
                    if month.isoformat()[:7] == invoice['InvoiceDate'][:7]
                ))
                month = next_month

    return {
        'period': period,
        'from': start.isoformat() if start else '',
        'to': (end - timedelta(days=1)).isoformat() if end else '',
        'summary': summary,
        'invoices': invoices,
        'topProducts': top_products,
        'brands': brands,
        'chart': {'labels': chart_labels, 'values': chart_values}
    }

@app.route('/api/reports/dashboard', methods=['GET'])
@require_roles('Admin', 'Manager')
def get_dashboard_metrics():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Tổng doanh thu & đơn hàng
    cursor.execute("SELECT COUNT(*), COALESCE(SUM(TotalAmount), 0) FROM Invoice WHERE Status = 'Hoàn thành'")
    tot_invoices, tot_revenue = cursor.fetchone()

    # Doanh thu hôm nay
    today_str = datetime.now().strftime('%Y-%m-%d')
    cursor.execute('''
    SELECT COUNT(*), COALESCE(SUM(TotalAmount), 0) 
    FROM Invoice 
    WHERE Status = 'Hoàn thành' AND date(InvoiceDate) = ?
    ''', (today_str,))
    today_invoices, today_revenue = cursor.fetchone()

    # Tổng sản phẩm & sản phẩm sắp hết hàng
    cursor.execute("SELECT COUNT(*) FROM Product WHERE Status = 1")
    tot_products = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM Inventory WHERE Quantity <= MinThreshold")
    low_stock_count = cursor.fetchone()[0]

    # Doanh thu 7 ngày gần nhất
    daily_labels = []
    daily_values = []
    for i in range(6, -1, -1):
        day = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        cursor.execute('''
        SELECT COALESCE(SUM(TotalAmount), 0) 
        FROM Invoice 
        WHERE Status = 'Hoàn thành' AND date(InvoiceDate) = ?
        ''', (day,))
        val = cursor.fetchone()[0]
        daily_labels.append(day[5:]) # MM-DD
        daily_values.append(val)

    # Hiển thị tất cả hãng đang kinh doanh; hãng chưa bán được máy có giá trị 0
    cursor.execute('''
        SELECT p.Brand,
            COALESCE(SUM(CASE WHEN inv.InvoiceID IS NOT NULL THEN d.Quantity ELSE 0 END), 0) AS QuantitySold
    FROM Product p
    LEFT JOIN InvoiceDetail d ON p.ProductID = d.ProductID
    LEFT JOIN Invoice inv ON d.InvoiceID = inv.InvoiceID
        AND inv.Status = 'Hoàn thành'
    WHERE p.Status = 1
    GROUP BY p.Brand
    ORDER BY QuantitySold DESC
    ''')
    brand_rows = cursor.fetchall()
    cat_labels = [row['Brand'] for row in brand_rows]
    cat_values = [row['QuantitySold'] for row in brand_rows]

    # Top 5 sản phẩm bán chạy nhất
    cursor.execute('''
    SELECT p.ProductName, p.Brand, SUM(d.Quantity) as QtySold, SUM(d.SubTotal) as Revenue, p.ImageURL
    FROM InvoiceDetail d
    JOIN Product p ON d.ProductID = p.ProductID
    GROUP BY d.ProductID
    ORDER BY QtySold DESC, Revenue DESC
    LIMIT 5
    ''')
    top_sellers = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return jsonify({
        "success": True,
        "kpis": {
            "totalRevenue": tot_revenue,
            "totalInvoices": tot_invoices,
            "todayRevenue": today_revenue,
            "todayInvoices": today_invoices,
            "totalProducts": tot_products,
            "lowStockCount": low_stock_count
        },
        "dailyChart": {
            "labels": daily_labels,
            "values": daily_values
        },
        "categoryChart": {
            "labels": cat_labels,
            "values": cat_values
        },
        "topSellers": top_sellers
    })

@app.route('/api/reports/revenue-chart', methods=['GET'])
@require_roles('Admin', 'Manager')
def get_revenue_chart():
    """Trả về dữ liệu biểu đồ doanh thu theo kỳ: 7days, week, month, quarter, year."""
    period = request.args.get('period', '7days')
    today = datetime.now().date()
    conn = get_db_connection()
    cursor = conn.cursor()

    labels = []
    values = []

    if period == '7days':
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            cursor.execute(
                "SELECT COALESCE(SUM(TotalAmount),0) FROM Invoice WHERE Status='Hoàn thành' AND date(InvoiceDate)=?",
                (day.isoformat(),)
            )
            labels.append(day.strftime('%d/%m'))
            values.append(cursor.fetchone()[0])

    elif period == 'week':
        # 8 tuần gần nhất (tính từ thứ Hai)
        monday = today - timedelta(days=today.weekday())
        for i in range(7, -1, -1):
            w_start = monday - timedelta(weeks=i)
            w_end = w_start + timedelta(days=7)
            cursor.execute(
                "SELECT COALESCE(SUM(TotalAmount),0) FROM Invoice WHERE Status='Hoàn thành' AND date(InvoiceDate)>=? AND date(InvoiceDate)<?",
                (w_start.isoformat(), w_end.isoformat())
            )
            labels.append(f"T{w_start.strftime('%d/%m')}")
            values.append(cursor.fetchone()[0])

    elif period == 'month':
        # 12 tháng gần nhất
        for i in range(11, -1, -1):
            m = today.month - i
            y = today.year + (m - 1) // 12
            m = ((m - 1) % 12) + 1
            m_start = date(y, m, 1)
            next_m = (m_start.replace(day=28) + timedelta(days=4)).replace(day=1)
            cursor.execute(
                "SELECT COALESCE(SUM(TotalAmount),0) FROM Invoice WHERE Status='Hoàn thành' AND date(InvoiceDate)>=? AND date(InvoiceDate)<?",
                (m_start.isoformat(), next_m.isoformat())
            )
            labels.append(m_start.strftime('%m/%Y'))
            values.append(cursor.fetchone()[0])

    elif period == 'quarter':
        # 8 quý gần nhất
        cur_q = (today.month - 1) // 3  # 0-based quarter index
        cur_y = today.year
        for i in range(7, -1, -1):
            q_idx = cur_q - i
            y = cur_y + q_idx // 4
            q = q_idx % 4
            if q < 0:
                y -= 1
                q += 4
            q_start_m = q * 3 + 1
            q_start = date(y, q_start_m, 1)
            q_end_m = q_start_m + 3
            if q_end_m > 12:
                q_end = date(y + 1, q_end_m - 12, 1)
            else:
                q_end = date(y, q_end_m, 1)
            cursor.execute(
                "SELECT COALESCE(SUM(TotalAmount),0) FROM Invoice WHERE Status='Hoàn thành' AND date(InvoiceDate)>=? AND date(InvoiceDate)<?",
                (q_start.isoformat(), q_end.isoformat())
            )
            labels.append(f"Q{q+1}/{y}")
            values.append(cursor.fetchone()[0])

    elif period == 'year':
        # 5 năm gần nhất
        for i in range(4, -1, -1):
            y = today.year - i
            y_start = date(y, 1, 1)
            y_end = date(y + 1, 1, 1)
            cursor.execute(
                "SELECT COALESCE(SUM(TotalAmount),0) FROM Invoice WHERE Status='Hoàn thành' AND date(InvoiceDate)>=? AND date(InvoiceDate)<?",
                (y_start.isoformat(), y_end.isoformat())
            )
            labels.append(str(y))
            values.append(cursor.fetchone()[0])

    conn.close()
    return jsonify({'success': True, 'labels': labels, 'values': values, 'period': period})


@app.route('/api/reports/data', methods=['GET'])
@require_roles('Admin', 'Manager')
def report_data():
    return jsonify({'success': True, **get_report_data(request.args)})

def get_export_rows(data):
    return [[
        row['InvoiceCode'], row['InvoiceDate'], row['CustomerName'], row['StaffName'],
        row['TotalItems'], row['SubTotal'], row['DiscountAmount'], row['TotalAmount'], row['PaymentMethod']
    ] for row in data['invoices']]

@app.route('/api/reports/export/xlsx', methods=['GET'])
@require_roles('Admin', 'Manager')
def export_xlsx():
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter
        from openpyxl.worksheet.table import Table, TableStyleInfo
    except ImportError:
        return jsonify({'success': False, 'message': 'Chưa cài thư viện Excel openpyxl.'}), 503

    data = get_report_data(request.args)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Bao cao ban hang'
    sheet.merge_cells('A1:I1')
    sheet['A1'] = 'BÁO CÁO DOANH THU BÁN HÀNG'
    sheet['A1'].font = Font(size=18, bold=True, color='FFFFFF')
    sheet['A1'].fill = PatternFill('solid', fgColor='12304A')
    sheet['A1'].alignment = Alignment(horizontal='center')
    sheet.merge_cells('A2:I2')
    sheet['A2'] = f"Thời gian: {data['from'] or 'Toàn bộ'} đến {data['to'] or 'hiện tại'}"
    sheet['A2'].font = Font(italic=True, color='486581')
    sheet.append([])
    sheet.append(['Tổng doanh thu', 'Số hóa đơn', 'Số sản phẩm bán'])
    sheet.append([data['summary']['Revenue'], data['summary']['InvoiceCount'], sum(row[4] for row in get_export_rows(data))])
    sheet.append([])
    headers = ['Mã hóa đơn', 'Ngày lập', 'Khách hàng', 'Nhân viên', 'Số món', 'Tiền hàng', 'Giảm giá', 'Thực thu', 'Thanh toán']
    sheet.append(headers)
    for row in get_export_rows(data):
        sheet.append(row)
    header_row = 7
    for cell in sheet[header_row]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='167D9A')
        cell.alignment = Alignment(horizontal='center')
    for row in sheet.iter_rows(min_row=8, max_col=9):
        for cell in row:
            cell.alignment = Alignment(vertical='center')
        for column in (6, 7, 8):
            row[column - 1].number_format = '#,##0 [$₫-vi-VN]'
    for column, width in {'A': 18, 'B': 20, 'C': 26, 'D': 26, 'E': 10, 'F': 18, 'G': 16, 'H': 18, 'I': 20}.items():
        sheet.column_dimensions[column].width = width
    sheet.freeze_panes = 'A8'
    sheet.auto_filter.ref = f'A7:I{max(7, sheet.max_row)}'
    if sheet.max_row >= 8:
        table = Table(displayName='BangDoanhThu', ref=f'A7:I{sheet.max_row}')
        table.tableStyleInfo = TableStyleInfo(name='TableStyleMedium2', showRowStripes=True)
        sheet.add_table(table)
    thin = Side(style='thin', color='D9E2EC')
    for row in sheet.iter_rows(min_row=4, max_row=sheet.max_row, max_col=9):
        for cell in row:
            cell.border = Border(bottom=thin)

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name=f"bao_cao_ban_hang_{datetime.now():%Y%m%d}.xlsx", mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/api/reports/export/pdf', methods=['GET'])
@require_roles('Admin', 'Manager')
def export_pdf():
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError:
        return jsonify({'success': False, 'message': 'Chưa cài thư viện PDF reportlab.'}), 503

    data = get_report_data(request.args)
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=landscape(A4), rightMargin=12 * mm, leftMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm)
    font_name = 'Helvetica'
    bold_font_name = 'Helvetica-Bold'
    font_dir = os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts')
    regular_font = os.path.join(font_dir, 'arial.ttf')
    bold_font = os.path.join(font_dir, 'arialbd.ttf')
    if os.path.exists(regular_font) and os.path.exists(bold_font):
        pdfmetrics.registerFont(TTFont('AppArial', regular_font))
        pdfmetrics.registerFont(TTFont('AppArialBold', bold_font))
        font_name = 'AppArial'
        bold_font_name = 'AppArialBold'

    styles = getSampleStyleSheet()
    title = ParagraphStyle('ReportTitle', parent=styles['Title'], fontName=bold_font_name, fontSize=20, leading=24, textColor=colors.HexColor('#12304A'), alignment=TA_CENTER, spaceAfter=6)
    subtitle = ParagraphStyle('ReportSubtitle', parent=styles['Normal'], fontName=font_name, fontSize=10, textColor=colors.HexColor('#486581'), alignment=TA_CENTER, spaceAfter=14)
    body = ParagraphStyle('ReportBody', parent=styles['Normal'], fontName=font_name, fontSize=8, leading=10)
    story = [Paragraph('BÁO CÁO DOANH THU BÁN HÀNG', title), Paragraph(f"Thời gian: {data['from'] or 'Toàn bộ'} đến {data['to'] or 'hiện tại'}", subtitle)]
    summary_data = [['TỔNG DOANH THU', 'SỐ HÓA ĐƠN', 'SỐ SẢN PHẨM BÁN'], [f"{data['summary']['Revenue']:,.0f} đ", str(data['summary']['InvoiceCount']), str(sum(row[4] for row in get_export_rows(data)))]]
    summary_table = Table(summary_data, colWidths=[85 * mm] * 3)
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#167D9A')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), bold_font_name), ('FONTNAME', (0, 1), (-1, -1), font_name), ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, -1), 11), ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#EAF6F8')),
        ('BOX', (0, 0), (-1, -1), 0.6, colors.HexColor('#B8CBD4')), ('BOTTOMPADDING', (0, 0), (-1, -1), 9), ('TOPPADDING', (0, 0), (-1, -1), 9)
    ]))
    story.extend([summary_table, Spacer(1, 12)])
    table_data = [['Mã hóa đơn', 'Ngày lập', 'Khách hàng', 'Nhân viên', 'Số món', 'Tiền hàng', 'Giảm giá', 'Thực thu', 'Thanh toán']]
    table_data.extend([[Paragraph(str(value), body) for value in row] for row in get_export_rows(data)])
    report_table = Table(table_data, repeatRows=1, colWidths=[25 * mm, 29 * mm, 42 * mm, 42 * mm, 15 * mm, 25 * mm, 22 * mm, 25 * mm, 28 * mm])
    report_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#12304A')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), bold_font_name), ('FONTNAME', (0, 1), (-1, -1), font_name), ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#D9E2EC')), ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F9FC')]),
        ('ALIGN', (4, 1), (7, -1), 'RIGHT'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5)
    ]))
    story.append(report_table)
    doc.build(story)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name=f"bao_cao_ban_hang_{datetime.now():%Y%m%d}.pdf", mimetype='application/pdf')

@app.route('/api/reports/export/csv', methods=['GET'])
@require_roles('Admin', 'Manager')
def export_csv():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT inv.InvoiceCode, inv.InvoiceDate, 
           COALESCE(c.CustomerName, 'Khách vãng lai') AS Customer,
           u.FullName AS Staff, inv.SubTotal, inv.DiscountAmount, inv.TotalAmount, inv.PaymentMethod
    FROM Invoice inv
    LEFT JOIN Customer c ON inv.CustomerID = c.CustomerID
    JOIN UserAccount u ON inv.UserID = u.UserID
    ORDER BY inv.InvoiceID DESC
    ''')
    rows = cursor.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Mã Hóa Đơn', 'Ngày Lập', 'Khách Hàng', 'Nhân Viên Lập', 'Tổng Tiền Hàng (VNĐ)', 'Giảm Giá (VNĐ)', 'Thực Thu (VNĐ)', 'Hình Thức Thanh Toán'])
    for r in rows:
        writer.writerow([r['InvoiceCode'], r['InvoiceDate'], r['Customer'], r['Staff'], r['SubTotal'], r['DiscountAmount'], r['TotalAmount'], r['PaymentMethod']])

    output.seek(0)
    return Response(
        output.getvalue().encode('utf-8-sig'),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=bao_cao_ban_hang_{datetime.now().strftime('%Y%m%d')}.csv"}
    )

# ==========================================
# AI INTEGRATION (UC09, UC10, UC11)
# ==========================================
@app.route('/api/ai/advisor', methods=['POST'])
@require_roles('Manager', 'Staff', 'Customer')
def handle_ai_advisor():
    data = request.get_json() or {}
    query = data.get('query', '').strip()
    user_id = data.get('userId', 1)

    if not query:
        return jsonify({"success": False, "message": "Vui lòng nhập nhu cầu hoặc yêu cầu của khách hàng!"}), 400

    result = ai_product_advisor(query, user_id=user_id)
    return jsonify({"success": True, "data": result})

@app.route('/api/ai/revenue-analysis', methods=['POST'])
@require_roles('Manager')
def handle_ai_revenue():
    data = request.get_json() or {}
    user_id = data.get('userId', 1)
    result = ai_revenue_analyst(user_id=user_id)
    return jsonify({"success": True, "data": result})

@app.route('/api/ai/query', methods=['POST'])
@require_roles('Manager')
def handle_ai_query():
    data = request.get_json() or {}
    question = data.get('question', '').strip()
    user_id = data.get('userId', 1)

    if not question:
        return jsonify({"success": False, "message": "Vui lòng nhập câu hỏi!"}), 400

    result = ai_smart_query(question, user_id=user_id)
    return jsonify({"success": True, "data": result})

@app.route('/api/ai/rag-status', methods=['GET'])
@require_roles('Manager', 'Admin')
def handle_rag_status():
    sys.path.insert(0, os.path.join(BASE_DIR, 'ai'))
    try:
        from rag_service import check_rag_status
        is_ready = check_rag_status()
    except Exception:
        is_ready = False
    return jsonify({"success": True, "isReady": is_ready})
    

# ==========================================
# SETTINGS & API KEY
# ==========================================
@app.route('/api/settings', methods=['GET', 'POST'])
@require_roles('Admin')
def handle_settings():
    if request.method == 'POST':
        data = request.get_json() or {}
        key = data.get('apiKey', '').strip()
        save_api_key(key)
        return jsonify({"success": True, "message": "Đã lưu cấu hình Google Gemini API Key!"})

    current_key = get_api_key()
    masked = f"{current_key[:6]}...{current_key[-4:]}" if len(current_key) > 10 else ("Đã cấu hình" if current_key else "Chưa cấu hình")
    return jsonify({
        "success": True,
        "isConfigured": bool(current_key),
        "maskedKey": masked
    })

if __name__ == '__main__':
    print("Khởi chạy Hệ thống Quản lý Bán hàng tích hợp AI trên cổng 5000...")
    app.run(host='0.0.0.0', port=5000, debug=True)
