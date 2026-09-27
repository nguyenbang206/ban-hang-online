import sqlite3
import os
import sys
import hashlib
import secrets
from datetime import datetime, timedelta
import random

try:
    if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'data', 'sales_management.db')

CUSTOMER_TIER_THRESHOLDS = (
    (500_000_000, 'Ruby'),
    (250_000_000, 'Kim cương'),
    (100_000_000, 'Vàng'),
    (50_000_000, 'Bạc'),
)

def hash_seed_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('ascii'), 260_000)
    return f'pbkdf2_sha256$260000${salt}${digest.hex()}'

def upgrade_plaintext_passwords(cursor):
    cursor.execute('SELECT UserID, PasswordHash FROM UserAccount')
    for user in cursor.fetchall():
        stored_password = user['PasswordHash'] or ''
        if not stored_password.startswith('pbkdf2_sha256$'):
            cursor.execute(
                'UPDATE UserAccount SET PasswordHash = ? WHERE UserID = ?',
                (hash_seed_password(stored_password), user['UserID'])
            )

def get_customer_group(total_spent):
    """Return the customer's tier from cumulative spending."""
    for threshold, group in CUSTOMER_TIER_THRESHOLDS:
        if total_spent >= threshold:
            return group
    return 'Thân thiết'

def normalize_customer_codes(cursor):
    """Migrate every customer code to the KH001-KH999 format."""
    cursor.execute('SELECT CustomerID, CustomerCode FROM Customer ORDER BY CustomerID ASC')
    customers = cursor.fetchall()
    if all(
        customer['CustomerCode']
        and len(customer['CustomerCode']) == 5
        and customer['CustomerCode'].startswith('KH')
        and customer['CustomerCode'][2:].isdigit()
        and 1 <= int(customer['CustomerCode'][2:]) <= 999
        for customer in customers
    ):
        return

    customer_ids = [customer['CustomerID'] for customer in customers]
    if len(customer_ids) > 999:
        raise ValueError('Số lượng khách hàng vượt quá giới hạn 999 mã từ KH001 đến KH999!')

    # Use temporary unique values first so old and new codes cannot collide.
    for customer_id in customer_ids:
        cursor.execute(
            'UPDATE Customer SET CustomerCode = ? WHERE CustomerID = ?',
            (f'TEMP-CUSTOMER-{customer_id}', customer_id)
        )
    for number, customer_id in enumerate(customer_ids, start=1):
        cursor.execute(
            'UPDATE Customer SET CustomerCode = ? WHERE CustomerID = ?',
            (f'KH{number:03d}', customer_id)
        )

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. UserAccount (Tài khoản người dùng)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS UserAccount (
        UserID INTEGER PRIMARY KEY AUTOINCREMENT,
        Username VARCHAR(50) UNIQUE NOT NULL,
        PasswordHash VARCHAR(255) NOT NULL,
        FullName NVARCHAR(100) NOT NULL,
        Email VARCHAR(100),
        Phone VARCHAR(15),
        Role VARCHAR(30) NOT NULL, -- 'Admin', 'Manager', 'Staff', 'Customer'
        Status INTEGER DEFAULT 1,
        CreatedAt DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    ''')

    # 2. Permission (Phân quyền)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Permission (
        PermissionID INTEGER PRIMARY KEY AUTOINCREMENT,
        PermissionCode VARCHAR(50) UNIQUE NOT NULL,
        PermissionName NVARCHAR(100) NOT NULL,
        Description NVARCHAR(255),
        Status INTEGER DEFAULT 1
    );
    ''')

    # 3. Category (Danh mục sản phẩm)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Category (
        CategoryID INTEGER PRIMARY KEY AUTOINCREMENT,
        CategoryName NVARCHAR(100) NOT NULL,
        Description NVARCHAR(255),
        Status INTEGER DEFAULT 1
    );
    ''')

    # 4. Product (Sản phẩm)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Product (
        ProductID INTEGER PRIMARY KEY AUTOINCREMENT,
        CategoryID INTEGER NOT NULL,
        ProductCode VARCHAR(50) UNIQUE NOT NULL,
        ProductName NVARCHAR(150) NOT NULL,
        Brand NVARCHAR(50) NOT NULL,
        CPU NVARCHAR(100),
        RAM NVARCHAR(50),
        Storage NVARCHAR(100),
        GPU NVARCHAR(100),
        Screen NVARCHAR(100),
        CostPrice DECIMAL(18,2) DEFAULT 0,
        Price DECIMAL(18,2) NOT NULL,
        Description NVARCHAR(500),
        ImageURL VARCHAR(255),
        Status INTEGER DEFAULT 1,
        FOREIGN KEY (CategoryID) REFERENCES Category(CategoryID)
    );
    ''')

    # 5. Inventory (Tồn kho)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Inventory (
        InventoryID INTEGER PRIMARY KEY AUTOINCREMENT,
        ProductID INTEGER UNIQUE NOT NULL,
        Quantity INTEGER NOT NULL DEFAULT 0,
        MinThreshold INTEGER NOT NULL DEFAULT 3,
        LastUpdated DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (ProductID) REFERENCES Product(ProductID) ON DELETE CASCADE
    );
    ''')

    # 6. Customer (Khách hàng)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Customer (
        CustomerID INTEGER PRIMARY KEY AUTOINCREMENT,
        CustomerCode VARCHAR(30) UNIQUE,
        CustomerName NVARCHAR(100) NOT NULL,
        Phone VARCHAR(15),
        Email VARCHAR(100),
        Address NVARCHAR(255),
        CustomerGroup VARCHAR(50) DEFAULT 'Thân thiết', -- 'Thân thiết', 'Bạc', 'Vàng', 'Kim cương', 'Ruby'
        TotalSpent DECIMAL(18,2) DEFAULT 0,
        CreatedAt DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    ''')

    # 7. Invoice (Hóa đơn bán hàng)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Invoice (
        InvoiceID INTEGER PRIMARY KEY AUTOINCREMENT,
        InvoiceCode VARCHAR(50) UNIQUE NOT NULL,
        CustomerID INTEGER,
        UserID INTEGER NOT NULL,
        InvoiceDate DATETIME DEFAULT CURRENT_TIMESTAMP,
        SubTotal DECIMAL(18,2) NOT NULL,
        DiscountPercent REAL DEFAULT 0,
        DiscountAmount DECIMAL(18,2) DEFAULT 0,
        TotalAmount DECIMAL(18,2) NOT NULL,
        PaymentMethod VARCHAR(30) DEFAULT 'Tiền mặt', -- 'Tiền mặt', 'Chuyển khoản QR', 'Thẻ POS'
        Notes NVARCHAR(255),
        Status VARCHAR(30) DEFAULT 'Hoàn thành',
        FOREIGN KEY (CustomerID) REFERENCES Customer(CustomerID),
        FOREIGN KEY (UserID) REFERENCES UserAccount(UserID)
    );
    ''')

    # 8. InvoiceDetail (Chi tiết hóa đơn)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS InvoiceDetail (
        InvoiceDetailID INTEGER PRIMARY KEY AUTOINCREMENT,
        InvoiceID INTEGER NOT NULL,
        ProductID INTEGER NOT NULL,
        Quantity INTEGER NOT NULL,
        UnitPrice DECIMAL(18,2) NOT NULL,
        SubTotal DECIMAL(18,2) NOT NULL,
        FOREIGN KEY (InvoiceID) REFERENCES Invoice(InvoiceID) ON DELETE CASCADE,
        FOREIGN KEY (ProductID) REFERENCES Product(ProductID)
    );
    ''')

    # 9. Supplier (Nhà cung cấp)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Supplier (
        SupplierID INTEGER PRIMARY KEY AUTOINCREMENT,
        SupplierName NVARCHAR(150) NOT NULL,
        Phone VARCHAR(15),
        Email VARCHAR(100),
        Address NVARCHAR(255),
        Status INTEGER DEFAULT 1
    );
    ''')

    # 10. ImportReceipt (Phiếu nhập hàng)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS ImportReceipt (
        ImportID INTEGER PRIMARY KEY AUTOINCREMENT,
        ImportCode VARCHAR(50) UNIQUE NOT NULL,
        SupplierID INTEGER NOT NULL,
        UserID INTEGER NOT NULL,
        ImportDate DATETIME DEFAULT CURRENT_TIMESTAMP,
        TotalAmount DECIMAL(18,2) NOT NULL,
        Status VARCHAR(30) DEFAULT 'Đã nhập kho',
        FOREIGN KEY (SupplierID) REFERENCES Supplier(SupplierID),
        FOREIGN KEY (UserID) REFERENCES UserAccount(UserID)
    );
    ''')

    # 11. ImportDetail (Chi tiết phiếu nhập)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS ImportDetail (
        ImportDetailID INTEGER PRIMARY KEY AUTOINCREMENT,
        ImportID INTEGER NOT NULL,
        ProductID INTEGER NOT NULL,
        Quantity INTEGER NOT NULL,
        UnitPrice DECIMAL(18,2) NOT NULL,
        SubTotal DECIMAL(18,2) NOT NULL,
        FOREIGN KEY (ImportID) REFERENCES ImportReceipt(ImportID) ON DELETE CASCADE,
        FOREIGN KEY (ProductID) REFERENCES Product(ProductID)
    );
    ''')

    # 12. SalesReport (Báo cáo doanh thu)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS SalesReport (
        ReportID INTEGER PRIMARY KEY AUTOINCREMENT,
        ReportCode VARCHAR(50) UNIQUE NOT NULL,
        FromDate DATE NOT NULL,
        ToDate DATE NOT NULL,
        TotalOrders INTEGER NOT NULL DEFAULT 0,
        TotalRevenue DECIMAL(18,2) NOT NULL DEFAULT 0,
        TotalProfit DECIMAL(18,2) DEFAULT 0,
        CreatedBy INTEGER,
        CreatedAt DATETIME DEFAULT CURRENT_TIMESTAMP,
        Notes NVARCHAR(500),
        FOREIGN KEY (CreatedBy) REFERENCES UserAccount(UserID)
    );
    ''')

    conn.commit()

    # Seed data if database is fresh
    cursor.execute('SELECT COUNT(*) FROM UserAccount')
    if cursor.fetchone()[0] == 0:
        seed_data(conn)

    normalize_customer_codes(cursor)
    upgrade_plaintext_passwords(cursor)

    # Keep legacy records aligned with the current tier policy.
    cursor.execute('SELECT CustomerID, TotalSpent FROM Customer')
    for customer in cursor.fetchall():
        cursor.execute(
            'UPDATE Customer SET CustomerGroup = ? WHERE CustomerID = ?',
            (get_customer_group(customer['TotalSpent']), customer['CustomerID'])
        )
    conn.commit()

    conn.close()

def seed_data(conn):
    cursor = conn.cursor()
    print("Seeding initial mock data for Laptop AI Sales Management System...")

    # Users
    users = [
        ('admin', hash_seed_password('123456'), 'Nguyễn Đình Bằng (Admin)', 'admin@ictu.edu.vn', '0987654321', 'Admin'),
        ('manager', hash_seed_password('123456'), 'Vàng Thị Dẳm (Quản lý)', 'dam.vt@ictu.edu.vn', '0912345678', 'Manager'),
        ('staff', hash_seed_password('123456'), 'Trần Văn Nhân Viên', 'nhanvien@ictu.edu.vn', '0934567890', 'Staff'),
        ('customer', hash_seed_password('123456'), 'Lê Khách Hàng VIP', 'khachhang@gmail.com', '0978901234', 'Customer'),
    ]
    cursor.executemany('''
    INSERT INTO UserAccount (Username, PasswordHash, FullName, Email, Phone, Role)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', users)

    # Categories
    categories = [
        ('Laptop Gaming', 'Dòng laptop chuyên chơi game, cấu hình cực mạnh, card rời RTX đồ họa cao'),
        ('Laptop Văn phòng & Học tập', 'Mỏng nhẹ, pin trâu từ 8-12 tiếng, thiết kế sang trọng, tối ưu cho sinh viên & văn phòng'),
        ('Laptop Đồ họa - Kỹ thuật', 'Màn hình chuẩn màu 100% sRGB/DCI-P3, CPU/GPU mạnh cho Render 3D, Premiere, CAD'),
        ('Phụ kiện & Linh kiện cao cấp', 'Chuột gaming, bàn phím cơ, tai nghe chống ồn, balo chống sốc'),
    ]
    cursor.executemany('''
    INSERT INTO Category (CategoryName, Description)
    VALUES (?, ?)
    ''', categories)

    # Suppliers
    suppliers = [
        ('Công ty TNHH Phân Phối FPT Synnex', '02473006666', 'contact@synnexfpt.com.vn', 'Tòa nhà FPT, Cầu Giấy, Hà Nội'),
        ('Nhà phân phối Viễn Sơn Computer', '02838326085', 'sales@vienson.com.vn', '162B Bùi Thị Xuân, Q1, TP.HCM'),
        ('Công ty Cổ phần Digiworld (DGW)', '02839290059', 'info@dgw.com.vn', '195 Cô Bắc, Quận 1, TP.HCM')
    ]
    cursor.executemany('''
    INSERT INTO Supplier (SupplierName, Phone, Email, Address)
    VALUES (?, ?, ?, ?)
    ''', suppliers)

    # Customers
    customers = [
        ('KH001', 'Hoàng Minh Tuấn', '0981234567', 'tuan.hm@gmail.com', 'Thành phố Thái Nguyên', 'Bạc', 58000000),
        ('KH002', 'Nguyễn Thị Thu Hà', '0972345678', 'thuha.ng@gmail.com', 'Sông Công, Thái Nguyên', 'Thân thiết', 24500000),
        ('KH003', 'Đặng Quốc Anh', '0963456789', 'anh.dq@gmail.com', 'Phổ Yên, Thái Nguyên', 'Thân thiết', 16900000),
        ('KH004', 'Vũ Mai Linh', '0914567890', 'mailinh.vu@gmail.com', 'TP. Bắc Kạn', 'Thân thiết', 31200000),
        ('KH005', 'Phạm Đức Duy', '0935678901', 'duy.pd@gmail.com', 'TP. Tuyên Quang', 'Bạc', 65000000),
    ]
    cursor.executemany('''
    INSERT INTO Customer (CustomerCode, CustomerName, Phone, Email, Address, CustomerGroup, TotalSpent)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', customers)

    # Products (12 top-tier laptop models & accessories)
    products = [
        # Gaming (Cat 1)
        (1, 'LT-ASUS-G16', 'ASUS ROG Zephyrus G16 (2024)', 'ASUS', 'Intel Core Ultra 9 185H', '32GB LPDDR5X', '1TB NVMe PCIe 4.0', 'NVIDIA GeForce RTX 4070 8GB', '16" 2.5K OLED 240Hz 100% DCI-P3', 46000000, 52990000, 'Laptop gaming siêu mỏng nhẹ, vỏ nhôm CNC, màn OLED đỉnh cao, pin 90Wh.', 'https://images.unsplash.com/photo-1593642632823-8f785ba67e45?w=500', 8, 2),
        (1, 'LT-ACER-NEO16', 'Acer Predator Helios Neo 16', 'Acer', 'Intel Core i7 14700HX', '16GB DDR5 5600MHz', '512GB NVMe Gen4', 'NVIDIA GeForce RTX 4060 8GB', '16" WQXGA 165Hz IPS 100% sRGB', 29000000, 33490000, 'Tản nhiệt quạt kim loại AeroBlade 3D thế hệ 5, hiệu năng gaming vượt trội tầm giá.', 'https://images.unsplash.com/photo-1603302576837-37561b2e2302?w=500', 12, 3),
        (1, 'LT-MSI-K15', 'MSI Katana 15 B13VGK', 'MSI', 'Intel Core i7 13620H', '16GB DDR5', '1TB NVMe Gen4', 'NVIDIA GeForce RTX 4070 8GB', '15.6" FHD 144Hz IPS', 28000000, 31990000, 'Bàn phím RGB 4 vùng, sức mạnh RTX 4070 xử lý mượt mọi tựa game AAA.', 'https://images.unsplash.com/photo-1541807084-5c52b6b3adef?w=500', 3, 2), # low stock
        
        # Văn phòng (Cat 2)
        (2, 'LT-APPLE-M3', 'Apple MacBook Air 13.6" M3 (2024)', 'Apple', 'Apple M3 8-Core', '16GB Unified Memory', '512GB SSD', 'Apple M3 10-Core GPU', '13.6" Liquid Retina TrueTone', 28500000, 32990000, 'Thiết kế nhôm siêu mỏng 11.3mm, thời lượng pin 18 tiếng, hoạt động hoàn toàn không quạt êm ái.', 'https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=500', 15, 3),
        (2, 'LT-LENOVO-X1', 'Lenovo ThinkPad X1 Carbon Gen 11', 'Lenovo', 'Intel Core i7 1365U', '32GB LPDDR5', '1TB NVMe PCIe 4.0', 'Intel Iris Xe Graphics', '14.0" 2.8K OLED HDR500', 36000000, 41500000, 'Đẳng cấp doanh nhân, sợi carbon siêu bền chuẩn quân đội, bàn phím gõ êm nhất thế giới.', 'https://images.unsplash.com/photo-1588872657578-7efd1f1555ed?w=500', 5, 2),
        (2, 'LT-ASUS-ZEN14', 'ASUS Zenbook 14 OLED UX3405', 'ASUS', 'Intel Core Ultra 7 155H', '16GB LPDDR5X', '512GB NVMe Gen4', 'Intel Arc Graphics', '14.0" 3K OLED 120Hz', 23000000, 26990000, 'Pin trâu 75Wh, chuẩn AI NPU tích hợp Copilot, màn OLED rực rỡ sắc nét.', 'https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=500', 9, 3),
        (2, 'LT-HP-PAV14', 'HP Pavilion 14-dv2073TU', 'HP', 'Intel Core i5 1235U', '16GB DDR4', '512GB NVMe SSD', 'Intel Iris Xe Graphics', '14.0" FHD IPS viền mỏng', 12500000, 14890000, 'Mẫu laptop học tập - sinh viên lý tưởng, giá rẻ, hiệu năng văn phòng bền bỉ.', 'https://images.unsplash.com/photo-1525547719571-a2d4ac8945e2?w=500', 18, 4),

        # Đồ họa - Kỹ thuật (Cat 3)
        (3, 'LT-DELL-XPS16', 'Dell XPS 16 9640 (2024)', 'Dell', 'Intel Core Ultra 7 155H', '32GB LPDDR5X', '1TB NVMe PCIe Gen4', 'NVIDIA GeForce RTX 4060 8GB', '16.3" 4K+ OLED Touch 100% DCI-P3', 59000000, 67990000, 'Kiệt tác máy trạm đồ họa, kính tràn viền, bàn rê haptic ẩn, màu sắc tuyệt đối chuẩn xác.', 'https://images.unsplash.com/photo-1593642702821-c8da6771f0c6?w=500', 4, 2),
        (3, 'LT-MAC-PRO16', 'Apple MacBook Pro 16" M3 Pro', 'Apple', 'Apple M3 Pro 12-Core', '36GB Unified Memory', '512GB SSD', '18-Core GPU', '16.2" Liquid Retina XDR 120Hz ProMotion', 58000000, 64990000, 'Chuyên gia dựng video 4K/8K, đồ họa 3D, thời lượng pin 22 giờ liên tục.', 'https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=500', 6, 2),
        (3, 'LT-LENOVO-P16', 'Lenovo ThinkPad P16s Gen 2', 'Lenovo', 'AMD Ryzen 7 PRO 7840U', '32GB LPDDR5X', '1TB NVMe Opal2', 'AMD Radeon 780M', '16" WUXGA Low Power IPS', 31000000, 35900000, 'Máy trạm di động chứng nhận ISV, chuyên AutoCAD, SolidWorks và lập trình phần mềm.', 'https://images.unsplash.com/photo-1588872657578-7efd1f1555ed?w=500', 2, 2), # low stock

        # Phụ kiện (Cat 4)
        (4, 'PK-LOGI-MX3S', 'Chuột không dây Logitech MX Master 3S', 'Logitech', 'Cảm biến Darkfield 8000 DPI', 'Pin sạc 70 ngày', 'Kết nối Bluetooth & Logi Bolt', 'Click tĩnh âm 90%', 'Công thái học chống mỏi cổ tay', 1700000, 2290000, 'Chuột văn phòng & lập trình viên cao cấp nhất hiện nay.', 'https://images.unsplash.com/photo-1615663245857-ac93bb7c39e7?w=500', 25, 5),
        (4, 'PK-KEY-K2PRO', 'Bàn phím cơ không dây Keychron K2 Pro', 'Keychron', 'Switch Gateron G Pro Red', 'Hot-swap, Foam tiêu âm', 'Keycap PBT Double-shot', 'RGB 22 hiệu ứng', 'Layout 75% gọn gàng', 1800000, 2450000, 'Bàn phím cơ hỗ trợ Mac/Windows, gõ đầm chắc, pin 4000mAh.', 'https://images.unsplash.com/photo-1587829741301-dc798b83add3?w=500', 14, 3)
    ]

    for p in products:
        cat_id, pcode, pname, brand, cpu, ram, storage, gpu, screen, cost, price, desc, img, qty, min_th = p
        cursor.execute('''
        INSERT INTO Product (CategoryID, ProductCode, ProductName, Brand, CPU, RAM, Storage, GPU, Screen, CostPrice, Price, Description, ImageURL)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (cat_id, pcode, pname, brand, cpu, ram, storage, gpu, screen, cost, price, desc, img))
        pid = cursor.lastrowid
        cursor.execute('''
        INSERT INTO Inventory (ProductID, Quantity, MinThreshold)
        VALUES (?, ?, ?)
        ''', (pid, qty, min_th))

    # Past Import Receipts
    cursor.execute('''
    INSERT INTO ImportReceipt (ImportCode, SupplierID, UserID, ImportDate, TotalAmount, Status)
    VALUES ('PN-2026-001', 1, 1, '2026-03-01 09:30:00', 165000000, 'Đã nhập kho')
    ''')
    imp_id = cursor.lastrowid
    cursor.execute('''
    INSERT INTO ImportDetail (ImportID, ProductID, Quantity, UnitPrice, SubTotal)
    VALUES (?, 1, 3, 46000000, 138000000), (?, 11, 15, 1700000, 25500000)
    ''', (imp_id, imp_id))

    # Past Invoices (to populate rich dashboard charts and revenue reports)
    sample_invoices = [
        ('HD-202603-01', 1, 3, '2026-03-02 10:15:00', 52990000, 5, 2649500, 50340500, 'Chuyển khoản QR', 1, 1, 52990000),
        ('HD-202603-02', 2, 3, '2026-03-04 14:20:00', 33490000, 0, 0, 33490000, 'Tiền mặt', 2, 1, 33490000),
        ('HD-202603-03', 3, 3, '2026-03-06 11:00:00', 14890000, 0, 0, 14890000, 'Chuyển khoản QR', 7, 1, 14890000),
        ('HD-202603-04', 4, 3, '2026-03-08 16:45:00', 35280000, 3, 1058400, 34221600, 'Thẻ POS', 4, 1, 32990000),
        ('HD-202603-05', 5, 3, '2026-03-10 15:30:00', 67990000, 5, 3399500, 64590500, 'Chuyển khoản QR', 8, 1, 67990000),
        ('HD-202603-06', 1, 3, '2026-03-12 18:10:00', 2290000, 0, 0, 2290000, 'Tiền mặt', 11, 1, 2290000),
        ('HD-202603-07', 2, 3, '2026-03-13 09:40:00', 26990000, 0, 0, 26990000, 'Chuyển khoản QR', 6, 1, 26990000),
    ]

    for inv in sample_invoices:
        code, cust_id, user_id, inv_date, subtotal, disc_pct, disc_amt, total, method, prod_id, qty, unit_price = inv
        cursor.execute('''
        INSERT INTO Invoice (InvoiceCode, CustomerID, UserID, InvoiceDate, SubTotal, DiscountPercent, DiscountAmount, TotalAmount, PaymentMethod)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (code, cust_id, user_id, inv_date, subtotal, disc_pct, disc_amt, total, method))
        inv_id = cursor.lastrowid
        cursor.execute('''
        INSERT INTO InvoiceDetail (InvoiceID, ProductID, Quantity, UnitPrice, SubTotal)
        VALUES (?, ?, ?, ?, ?)
        ''', (inv_id, prod_id, qty, unit_price, subtotal))

    conn.commit()
    print("Seeding completed successfully!")

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully!")
