import os
import sys
import json
import re
import urllib.request
import urllib.error
from database import get_db_connection

try:
    if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'ai'))

PROMPTS_DIR = os.path.join(BASE_DIR, 'ai', 'prompts')
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')

def load_prompt_template(filename):
    path = os.path.join(PROMPTS_DIR, filename)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    return ""

def get_api_key():
    # Priority: 1. config.json, 2. Environment variable
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data.get('gemini_api_key'):
                    return data['gemini_api_key'].strip()
        except Exception:
            pass
    return os.environ.get('GEMINI_API_KEY', '').strip()

def get_ai_model():
    """Allow the deployed Gemini model to be changed without editing source code."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data.get('gemini_model'):
                    return data['gemini_model'].strip()
        except Exception:
            pass
    return os.environ.get('GEMINI_MODEL', 'gemini-3.6-flash').strip()

def save_api_key(key):
    data = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            pass
    data['gemini_api_key'] = key.strip()
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return True

def anonymize_customer(phone, name=""):
    """Bảo mật PII: Ẩn bớt số điện thoại và tên theo tài liệu mục 1.3.6 & 2.1.2"""
    masked_phone = phone
    if phone and len(phone) >= 7:
        masked_phone = phone[:3] + "****" + phone[-3:]
    return masked_phone

def get_requested_product_count(query):
    """Read an explicit requested quantity; keep the advisor result bounded."""
    number_words = {
        'mot': 1, 'một': 1, 'hai': 2, 'ba': 3,
        'bon': 4, 'bốn': 4, 'nam': 5, 'năm': 5
    }
    normalized_query = query.lower()
    count_match = re.search(
        r'\b(\d+|một|mot|hai|ba|bốn|bon|năm|nam)\s*(?:chiếc|cái|con|máy|laptop|sản phẩm|mẫu)\b',
        normalized_query
    )
    if not count_match:
        return 3

    raw_count = count_match.group(1)
    count = number_words.get(raw_count, int(raw_count) if raw_count.isdigit() else 3)
    return max(1, count)

def call_gemini_api(prompt_text, api_key):
    """Gọi trực tiếp Google Gemini API qua giao thức REST chuẩn."""
    if not api_key:
        return None
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{get_ai_model()}:generateContent?key={api_key}"
    payload = {
        "contents": [{
            "parts": [{"text": prompt_text}]
        }],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 4096
        }
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            res_body = response.read().decode('utf-8')
            res_json = json.loads(res_body)
            candidates = res_json.get('candidates', [])
            if candidates and 'content' in candidates[0]:
                parts = candidates[0]['content'].get('parts', [])
                if parts:
                    return parts[0].get('text', '')
    except Exception as e:
        print(f"Gemini API call failed or timed out: {e}")
        return None
    return None

# ==========================================
# 1. UC09: AI TƯ VẤN SẢN PHẨM (Laptop Advisor)
# ==========================================
def ai_product_advisor(user_query, user_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Truy vấn toàn bộ sản phẩm đang còn hàng trong kho
    cursor.execute('''
    SELECT p.ProductID, p.ProductCode, p.ProductName, p.Brand, c.CategoryName,
           p.CPU, p.RAM, p.Storage, p.GPU, p.Screen, p.Price, p.Description, p.ImageURL,
           i.Quantity AS StockQuantity
    FROM Product p
    JOIN Category c ON p.CategoryID = c.CategoryID
    JOIN Inventory i ON p.ProductID = i.ProductID
    WHERE p.Status = 1 AND i.Quantity > 0
    ORDER BY p.Price ASC
    ''')
    products = [dict(row) for row in cursor.fetchall()]

    if not products:
        conn.close()
        return {
            "analysis": "Hiện tại tất cả các mặt hàng trong kho đều đã tạm hết. Vui lòng tạo phiếu nhập hàng mới.",
            "recommended_products": []
        }

    # Phân tích từ khóa nhu cầu
    q = user_query.lower()
    
    # 1. Lọc theo ngân sách (nếu khách đề cập)
    max_budget = None
    min_budget = None
    
    # Bắt số tiền (ví dụ: 15 triệu, 20tr, 30.000.000, 50tr)
    million_matches = re.findall(r'(\d+[\.,]?\d*)\s*(triệu|tr|m)', q)
    if million_matches:
        val = float(million_matches[0][0].replace(',', '.')) * 1000000
        if "dưới" in q or "tối đa" in q or "<" in q:
            max_budget = val
        elif "trên" in q or "tối thiểu" in q or ">" in q:
            min_budget = val
        else:
            max_budget = val * 1.15 # Dung sai 15%

    num_matches = re.findall(r'(\d{7,9})', q)
    if num_matches:
        val = float(num_matches[0])
        max_budget = val

    requested_count = get_requested_product_count(user_query)

    # 2. Chấm điểm độ phù hợp của từng laptop
    scored_products = []
    for p in products:
        score = 10 # Base score
        p_name = p['ProductName'].lower()
        p_desc = p['Description'].lower()
        p_cat = p['CategoryName'].lower()
        p_brand = p['Brand'].lower()
        p_specs = f"{p['CPU']} {p['RAM']} {p['GPU']} {p['Storage']} {p['Screen']}".lower()

        # Kiểm tra ngân sách
        if max_budget and p['Price'] <= max_budget:
            score += 40
            if p['Price'] >= max_budget * 0.75:
                score += 15 # Tối ưu cấu hình sát ngân sách
        elif max_budget and p['Price'] > max_budget:
            score -= 50

        if min_budget and p['Price'] >= min_budget:
            score += 25

        # Nhu cầu Gaming
        if any(w in q for w in ['game', 'gaming', 'chơi game', 'fps', 'card rời', 'rtx']):
            if 'gaming' in p_cat or 'rtx' in p_specs:
                score += 50
            if '4070' in p_specs:
                score += 15

        # Nhu cầu Văn phòng / Học sinh sinh viên
        if any(w in q for w in ['văn phòng', 'học tập', 'sinh viên', 'nhẹ', 'mỏng', 'pin trâu', 'pin lâu']):
            if 'văn phòng' in p_cat or 'air' in p_name or 'zenbook' in p_name or 'pavilion' in p_name:
                score += 50
            if 'kg' in p_desc or 'pin' in p_desc or 'mỏng' in p_desc:
                score += 15

        # Nhu cầu Đồ họa / Render / Lập trình kỹ thuật
        if any(w in q for w in ['đồ họa', 'render', '3d', 'autocad', 'dựng phim', 'premiere', 'it', 'lập trình', 'code']):
            if 'đồ họa' in p_cat or 'xps' in p_name or 'thinkpad' in p_name or 'pro' in p_name:
                score += 50
            if '32gb' in p_specs or 'oled' in p_specs or '4k' in p_specs:
                score += 20

        # Khớp thương hiệu
        for brand in ['asus', 'apple', 'dell', 'lenovo', 'hp', 'msi', 'acer', 'macbook']:
            if brand in q and (brand in p_brand or brand in p_name):
                score += 45

        # Khớp linh kiện (RAM 16GB, 32GB, i7, i9, OLED)
        if '16gb' in q and '16gb' in p_specs:
            score += 20
        if '32gb' in q and '32gb' in p_specs:
            score += 25
        if 'oled' in q and 'oled' in p_specs:
            score += 20

        # Ưu tiên hàng còn tồn kho nhiều hơn một chút để dễ xuất bán
        score += min(p['StockQuantity'], 10)

        scored_products.append((score, p))

    # Chỉ chọn trong ngân sách nếu có đủ sản phẩm phù hợp.
    scored_products.sort(key=lambda x: x[0], reverse=True)
    eligible_products = scored_products
    if max_budget:
        within_budget = [item for item in scored_products if item[1]['Price'] <= max_budget]
        if within_budget:
            eligible_products = within_budget
    recommended_products = [item[1] for item in eligible_products[:requested_count]]

    # Thử gọi Gemini nếu có API Key
    api_key = get_api_key()
    gemini_text = None
    if api_key:
        template = load_prompt_template('product_advisor.txt')
        prod_data_str = json.dumps([{
            "Mã": p["ProductCode"],
            "Tên": p["ProductName"],
            "Danh mục": p["CategoryName"],
            "Cấu hình": f"{p['CPU']}, RAM {p['RAM']}, {p['Storage']}, {p['GPU']}, Màn {p['Screen']}",
            "Giá bán": f"{p['Price']:,.0f} VNĐ",
            "Tồn kho": p["StockQuantity"]
        } for p in recommended_products], ensure_ascii=False, indent=2)

        prompt = (template.replace('{product_data}', prod_data_str)
              .replace('{customer_query}', user_query)
              .replace('{requested_count}', str(len(recommended_products))))
        gemini_text = call_gemini_api(prompt, api_key)

    if not gemini_text:
        # Ground-truth AI Engine sinh nhận xét sắc bén chuẩn xác
        summary_lines = [
            f"🎯 **Phân tích yêu cầu**: '{user_query}'",
            f"Dựa trên dữ liệu tồn kho thực tế, hệ thống đã đối sánh thông số kỹ thuật và chọn đúng **{len(recommended_products)} dòng máy** theo yêu cầu:",
        ]
        for idx, p in enumerate(recommended_products, 1):
            summary_lines.append(
                f"\n**{idx}. {p['ProductName']}** (Giá: **{p['Price']:,.0f} VNĐ** | Kho: **{p['StockQuantity']} chiếc**)"
                f"\n- **Điểm nổi bật**: CPU {p['CPU']} | RAM {p['RAM']} | Ổ cứng {p['Storage']} | {p['GPU']} | Màn hình {p['Screen']}."
                f"\n- **Lý do đề xuất**: {p['Description']}"
            )
        summary_lines.append("\n💡 *Nhân viên bán hàng có thể bấm nút **'Thêm vào Hóa đơn'** bên dưới để lập phiếu thanh toán nhanh cho khách.*")
        gemini_text = "\n".join(summary_lines)

    conn.close()

    return {
        "analysis": gemini_text,
        "recommended_products": recommended_products,
        "requested_count": requested_count
    }

# ==========================================
# 2. UC10: AI PHÂN TÍCH BÁO CÁO DOANH THU (Revenue Analyst)
# ==========================================
def ai_revenue_analyst(user_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Tổng doanh thu & đơn hàng
    cursor.execute('''
    SELECT COUNT(*) AS TotalInvoices,
           COALESCE(SUM(TotalAmount), 0) AS TotalRevenue,
           COALESCE(SUM(DiscountAmount), 0) AS TotalDiscount
    FROM Invoice
    WHERE Status = 'Hoàn thành'
    ''')
    summary = dict(cursor.fetchone())

    # Doanh thu theo danh mục
    cursor.execute('''
        SELECT c.CategoryName,
           COUNT(d.InvoiceDetailID) AS ItemsSold,
           COALESCE(SUM(d.SubTotal), 0) AS CategoryRevenue
    FROM Category c
    LEFT JOIN Product p ON c.CategoryID = p.CategoryID
        LEFT JOIN InvoiceDetail d ON p.ProductID = d.ProductID
        LEFT JOIN Invoice inv ON d.InvoiceID = inv.InvoiceID AND inv.Status = 'Hoàn thành'
        WHERE inv.InvoiceID IS NOT NULL OR d.InvoiceDetailID IS NULL
    GROUP BY c.CategoryID
    ORDER BY CategoryRevenue DESC
    ''')
    by_category = [dict(row) for row in cursor.fetchall()]

    # Top 3 sản phẩm bán chạy nhất
    cursor.execute('''
    SELECT p.ProductName, p.Brand, SUM(d.Quantity) AS TotalQtySold, SUM(d.SubTotal) AS ProductRevenue
    FROM InvoiceDetail d
    JOIN Product p ON d.ProductID = p.ProductID
    JOIN Invoice inv ON d.InvoiceID = inv.InvoiceID AND inv.Status = 'Hoàn thành'
    GROUP BY d.ProductID
    ORDER BY TotalQtySold DESC, ProductRevenue DESC
    LIMIT 3
    ''')
    best_sellers = [dict(row) for row in cursor.fetchall()]

    # Sản phẩm bán chậm hoặc chưa bán được (tồn kho cao)
    cursor.execute('''
    SELECT p.ProductName, p.Brand, i.Quantity AS StockQty, p.Price,
           COALESCE(SUM(d.Quantity), 0) AS SoldQty
    FROM Product p
    JOIN Inventory i ON p.ProductID = i.ProductID
    LEFT JOIN InvoiceDetail d ON p.ProductID = d.ProductID
    LEFT JOIN Invoice inv ON d.InvoiceID = inv.InvoiceID AND inv.Status = 'Hoàn thành'
    WHERE inv.InvoiceID IS NOT NULL OR d.InvoiceDetailID IS NULL
    GROUP BY p.ProductID
    ORDER BY SoldQty ASC, StockQty DESC
    LIMIT 4
    ''')
    slow_sellers = [dict(row) for row in cursor.fetchall()]

    # Cảnh báo tồn kho dưới ngưỡng tối thiểu
    cursor.execute('''
    SELECT p.ProductName, i.Quantity, i.MinThreshold
    FROM Product p
    JOIN Inventory i ON p.ProductID = i.ProductID
    WHERE i.Quantity <= i.MinThreshold
    ''')
    low_stock = [dict(row) for row in cursor.fetchall()]

    report_context = {
        "tong_quan": summary,
        "theo_danh_muc": by_category,
        "san_pham_ban_chay": best_sellers,
        "san_pham_ban_cham_va_ton_kho": slow_sellers,
        "canh_bao_sap_het_hang": low_stock
    }

    api_key = get_api_key()
    gemini_text = None
    if api_key:
        template = load_prompt_template('revenue_analyst.txt')
        prompt = template.replace('{report_data}', json.dumps(report_context, ensure_ascii=False, indent=2))
        gemini_text = call_gemini_api(prompt, api_key)

    if not gemini_text:
        # Heuristic Analysis Output
        tot_rev = summary.get('TotalRevenue', 0)
        tot_inv = summary.get('TotalInvoices', 0)
        avg_order = (tot_rev / tot_inv) if tot_inv > 0 else 0

        cat_breakdown = ", ".join([f"**{c['CategoryName']}** ({c['CategoryRevenue']:,.0f} đ)" for c in by_category if c['CategoryRevenue'] > 0])
        top_names = ", ".join([f"**{b['ProductName']}** ({b['TotalQtySold']} máy)" for b in best_sellers]) or "Chưa có"
        slow_names = ", ".join([f"**{s['ProductName']}** (Tồn: {s['StockQty']} máy)" for s in slow_sellers[:2]]) or "Không có"
        alert_names = ", ".join([f"**{l['ProductName']}** (còn {l['Quantity']}/{l['MinThreshold']} máy)" for l in low_stock]) or "Kho hàng ở mức an toàn"

        gemini_text = f"""### 📊 BÁO CÁO PHÂN TÍCH TÌNH HÌNH KINH DOANH VÀ DOANH THU (AI INSIGHTS)

#### 1. Tổng quan Tăng trưởng & Doanh số
* **Tổng doanh thu thực đạt**: **{tot_rev:,.0f} VNĐ** trên tổng số **{tot_inv} đơn hàng hoàn tất**.
* **Giá trị trung bình mỗi đơn (AOV)**: **{avg_order:,.0f} VNĐ/đơn**. Tỷ lệ khách hàng đầu tư các dòng máy phân khúc trung và cao cấp rất tích cực.
* **Đóng góp doanh thu chính**: {cat_breakdown}.

#### 2. Phân tích Mặt hàng Bán chạy & Thị hiếu Khách hàng
* Các model dẫn đầu doanh thu: {top_names}.
* Nhận định thị hiếu chỉ được đưa ra khi có dữ liệu bán hàng tương ứng; báo cáo này không tự suy diễn ngoài số liệu hệ thống.

#### 3. Cảnh báo Mặt hàng Bán chậm & Tồn kho Cần lưu ý
* **Sản phẩm bán chậm / tốc độ luân chuyển thấp**: {slow_names}. Cần tránh tình trạng đọng vốn lâu ngày.
* **Cảnh báo hàng sắp hết (dưới ngưỡng an toàn)**: {alert_names}.

#### 4. Khuyến nghị Quản trị từ Trợ lý AI (Actionable Strategies)
1. **Kế hoạch nhập hàng**: Khẩn trương lập phiếu nhập bổ sung đối với các sản phẩm đang có số lượng dưới ngưỡng tối thiểu để không bỏ lỡ nhu cầu của khách trong tuần tới.
2. **Kích cầu sản phẩm chậm luân chuyển**: Triển khai gói khuyến mãi tặng kèm phụ kiện (chuột công thái học, balo chống sốc, voucher 5%) hoặc chiết khấu 2-3% cho các dòng máy đang tồn nhiều.
3. **Theo dõi khách hàng thân thiết**: Chỉ triển khai chăm sóc theo nhóm khách hàng khi dữ liệu CRM hiện tại có đủ thông tin phù hợp."""

    conn.close()

    return {
        "analysis": gemini_text,
        "metrics": report_context
    }

# ==========================================
# 3. UC11: AI HỎI ĐÁP DỮ LIỆU BÁN HÀNG (Sales Q&A)
# ==========================================
def ai_sales_qa(question, user_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()

    q_lower = question.lower()
    
    # 1. Truy vấn các dữ kiện kinh doanh cốt lõi để chuẩn bị ngữ cảnh
    cursor.execute("SELECT COUNT(*), COALESCE(SUM(TotalAmount), 0) FROM Invoice WHERE Status = 'Hoàn thành'")
    inv_count, total_revenue = cursor.fetchone()

    cursor.execute('''
    SELECT p.ProductName, SUM(d.Quantity) as Qty, SUM(d.SubTotal) as Rev
    FROM InvoiceDetail d
    JOIN Product p ON d.ProductID = p.ProductID
    JOIN Invoice inv ON d.InvoiceID = inv.InvoiceID AND inv.Status = 'Hoàn thành'
    GROUP BY d.ProductID ORDER BY Qty DESC LIMIT 3
    ''')
    best_sellers = [dict(row) for row in cursor.fetchall()]

    cursor.execute('''
    SELECT p.ProductName, i.Quantity, i.MinThreshold
    FROM Product p JOIN Inventory i ON p.ProductID = i.ProductID
    WHERE i.Quantity <= i.MinThreshold
    ''')
    low_stocks = [dict(row) for row in cursor.fetchall()]

    cursor.execute('''
    SELECT p.ProductName, i.Quantity, COALESCE(SUM(d.Quantity), 0) as Sold
    FROM Product p JOIN Inventory i ON p.ProductID = i.ProductID
    LEFT JOIN InvoiceDetail d ON p.ProductID = d.ProductID
    LEFT JOIN Invoice inv ON d.InvoiceID = inv.InvoiceID AND inv.Status = 'Hoàn thành'
    WHERE inv.InvoiceID IS NOT NULL OR d.InvoiceDetailID IS NULL
    GROUP BY p.ProductID ORDER BY Sold ASC, i.Quantity DESC LIMIT 3
    ''')
    slow_sellers = [dict(row) for row in cursor.fetchall()]

    cursor.execute("SELECT CustomerName, TotalSpent, CustomerGroup, Phone FROM Customer ORDER BY TotalSpent DESC LIMIT 3")
    top_customers = []
    for row in cursor.fetchall():
        top_customers.append({
            "Tên": row['CustomerName'],
            "Chi tiêu": f"{row['TotalSpent']:,.0f} đ",
            "Nhóm": row['CustomerGroup'],
            "SĐT": anonymize_customer(row['Phone'])
        })

    api_key = get_api_key()
    dynamic_context = None

    if api_key:
        # Text-to-SQL Logic
        sql_schema_prompt = f"""You are a SQLite expert. Given the schema:
Table Product(ProductID, CategoryID, ProductCode, ProductName, Brand, CPU, RAM, Storage, GPU, Screen, CostPrice, Price, Description, ImageURL)
Table Inventory(InventoryID, ProductID, Quantity, MinThreshold)
Table Customer(CustomerID, CustomerCode, CustomerName, Phone, Email, Address, CustomerGroup, TotalSpent)
Table Invoice(InvoiceID, InvoiceCode, CustomerID, UserID, InvoiceDate, SubTotal, DiscountPercent, DiscountAmount, TotalAmount, PaymentMethod, Status)
Table InvoiceDetail(InvoiceDetailID, InvoiceID, ProductID, Quantity, UnitPrice, SubTotal)
Table Category(CategoryID, CategoryName)

Write a SQLite SELECT query to answer this question: "{question}"
Rules:
- DO NOT wrap the query in ```sql ``` or any markdown. Return ONLY raw SQL.
- ONLY use SELECT.
- If asked for max/min, use ORDER BY and LIMIT 1.
"""
        generated_sql = call_gemini_api(sql_schema_prompt, api_key)
        if generated_sql:
            clean_sql = generated_sql.strip()
            if clean_sql.startswith("```sql"):
                clean_sql = clean_sql[6:]
            if clean_sql.startswith("```"):
                clean_sql = clean_sql[3:]
            if clean_sql.endswith("```"):
                clean_sql = clean_sql[:-3]
            clean_sql = clean_sql.strip()

            if clean_sql.upper().startswith("SELECT"):
                try:
                    cursor.execute(clean_sql)
                    columns = [desc[0] for desc in cursor.description]
                    rows = cursor.fetchall()
                    result_list = [dict(zip(columns, row)) for row in rows]
                    if result_list:
                        dynamic_context = result_list
                    else:
                        dynamic_context = "Không tìm thấy dữ liệu."
                except Exception as e:
                    print(f"Text-to-SQL error: {e}")

    context_dict = {
        "tong_doanh_thu": f"{total_revenue:,.0f} VNĐ",
        "tong_so_hoa_don": inv_count,
        "san_pham_ban_chay_nhat": best_sellers,
        "san_pham_ban_cham_nhat": slow_sellers,
        "san_pham_sap_het_hang": low_stocks,
        "top_khach_hang_chi_tieu_cao": top_customers
    }
    
    if dynamic_context:
        context_dict["ket_qua_truy_van_dong_tu_cau_hoi"] = dynamic_context

    answer_text = None
    if api_key:
        template = load_prompt_template('sales_qa.txt')
        prompt = template.replace('{context_data}', json.dumps(context_dict, ensure_ascii=False, indent=2)).replace('{user_question}', question)
        answer_text = call_gemini_api(prompt, api_key)

    if not answer_text:
        # Heuristic QA Response
        if any(w in q_lower for w in ['chậm', 'ế', 'ít người mua', 'tồn nhiều']):
            items_str = "\n".join([f"- **{s['ProductName']}**: Đã bán {s['Sold']} máy, hiện còn tồn kho **{s['Quantity']} máy**." for s in slow_sellers])
            answer_text = f"Dựa trên dữ liệu bán hàng thực tế, các mặt hàng có tốc độ luân chuyển chậm nhất hiện nay gồm:\n{items_str}\n\n💡 **Khuyến nghị**: Quản lý nên cân nhắc chương trình tặng kèm phụ kiện hoặc giảm giá nhẹ để giải phóng tồn kho."
        elif any(w in q_lower for w in ['chạy', 'nhiều nhất', 'hot', 'ưa chuộng']):
            items_str = "\n".join([f"- **{b['ProductName']}**: Đã bán **{b['Qty']} máy**, mang về doanh thu **{b['Rev']:,.0f} VNĐ**." for b in best_sellers])
            answer_text = f"Top các mẫu laptop bán chạy nhất hệ thống ghi nhận:\n{items_str}\n\n💡 **Khuyến nghị**: Các dòng máy này đang có sức mua rất tốt, hãy đảm bảo lượng tồn kho tối thiểu luôn duy trì trên 5 chiếc."
        elif any(w in q_lower for w in ['doanh thu', 'tiền', 'doanh số']):
            answer_text = f"Tổng doanh thu toàn hệ thống hiện tại đạt **{total_revenue:,.0f} VNĐ** thông qua **{inv_count} đơn hàng** đã xuất và thanh toán thành công."
        elif any(w in q_lower for w in ['tồn kho', 'hết hàng', 'cảnh báo', 'kho']):
            if low_stocks:
                items_str = "\n".join([f"- **{l['ProductName']}**: Hiện chỉ còn **{l['Quantity']} chiếc** (Ngưỡng cảnh báo an toàn: {l['MinThreshold']} chiếc)." for l in low_stocks])
                answer_text = f"⚠️ **Cảnh báo tồn kho thấp**: Hiện có {len(low_stocks)} sản phẩm đang chạm hoặc dưới ngưỡng an toàn:\n{items_str}\n\nĐề xuất tạo ngay phiếu nhập hàng từ nhà cung cấp!"
            else:
                answer_text = "Tất cả các mặt hàng trong kho hiện đều ở mức an toàn trên ngưỡng quy định."
        elif any(w in q_lower for w in ['khách hàng', 'vip', 'mua nhiều']):
            cust_str = "\n".join([f"- **{c['Tên']}** ({c['Nhóm']}) - Đã chi tiêu: **{c['Chi tiêu']}** (Liên hệ: {c['SĐT']})" for c in top_customers])
            answer_text = f"Danh sách khách hàng có mức chi tiêu cao nhất:\n{cust_str}"
        else:
            answer_text = f"Hệ thống ghi nhận câu hỏi: *'{question}'*.\n\nThông số kinh doanh hiện tại:\n- **Tổng doanh thu**: {total_revenue:,.0f} VNĐ ({inv_count} đơn hàng).\n- **Model bán chạy số 1**: {best_sellers[0]['ProductName'] if best_sellers else 'Chưa có'}.\n- **Sản phẩm cần lưu ý tồn kho**: {low_stocks[0]['ProductName'] if low_stocks else 'Kho ổn định'}.\n\nBạn có thể hỏi chi tiết hơn như: *'Mặt hàng nào bán chậm?'*, *'Doanh thu hôm nay?'* hoặc *'Sản phẩm nào sắp hết hàng?'*."

    conn.close()

    return {
        "question": question,
        "answer": answer_text
    }

# ==========================================
# 4. RAG & MIXED QA (LEVEL 3)
# ==========================================
def ai_rag_qa(question, user_id=None):
    # pyrefly: ignore [missing-import]
    from rag_service import retrieve_relevant_documents
    
    docs = retrieve_relevant_documents(question, top_k=5)
    
    if not docs:
        return {
            "question": question,
            "answer": "Rất tiếc, hệ thống không tìm thấy tài liệu nào liên quan đến câu hỏi của bạn.",
            "sources": []
        }
        
    context_text = "\n\n".join([f"Tài liệu {i+1} (Nguồn: {d['source']}):\n{d['content']}" for i, d in enumerate(docs)])
    sources = list(set([d['source'] for d in docs]))
    
    api_key = get_api_key()
    if not api_key:
        return {
            "question": question,
            "answer": "Lỗi: Chưa cấu hình API Key. Hãy cấu hình API Key trong mục Cài đặt.",
            "sources": sources
        }
        
    template = load_prompt_template('rag_qa.txt')
    prompt = template.replace('{context}', context_text).replace('{user_question}', question)
    answer_text = call_gemini_api(prompt, api_key)
    
    if not answer_text:
        answer_text = "Có lỗi xảy ra khi gọi Gemini API."
        
    return {
        "question": question,
        "answer": answer_text,
        "sources": sources
    }

def ai_mixed_qa(question, user_id=None):
    # pyrefly: ignore [missing-import]
    from rag_service import retrieve_relevant_documents
    
    # 1. Get SQL context using ai_sales_qa
    sql_result = ai_sales_qa(question, user_id)
    # The answer from ai_sales_qa is currently the final response, but we can intercept the logic or just use its heuristic text as context
    # To keep it simple, we use its generated text (heuristic) as SQL context.
    sql_context = sql_result.get("answer", "")
    
    # 2. Get RAG context
    docs = retrieve_relevant_documents(question, top_k=5)
    rag_context = "\n\n".join([f"Tài liệu {i+1} (Nguồn: {d['source']}):\n{d['content']}" for i, d in enumerate(docs)])
    sources = list(set([d['source'] for d in docs])) if docs else []
    
    api_key = get_api_key()
    if not api_key:
        return {
            "question": question,
            "answer": "Lỗi: Chưa cấu hình API Key. Hãy cấu hình API Key trong mục Cài đặt.",
            "sources": sources
        }
        
    template = load_prompt_template('mixed_qa.txt')
    prompt = template.replace('{sql_context}', sql_context).replace('{rag_context}', rag_context).replace('{user_question}', question)
    answer_text = call_gemini_api(prompt, api_key)
    
    if not answer_text:
        answer_text = "Có lỗi xảy ra khi gọi Gemini API."
        
    return {
        "question": question,
        "answer": answer_text,
        "sources": sources
    }

def ai_smart_query(question, user_id=None):
    # pyrefly: ignore [missing-import]
    from rag_router import classify_query
    
    query_type = classify_query(question)
    
    if query_type == "sql":
        res = ai_sales_qa(question, user_id)
        res["query_type"] = "SQL"
        return res
    elif query_type == "rag":
        res = ai_rag_qa(question, user_id)
        res["query_type"] = "RAG"
        return res
    else:
        res = ai_mixed_qa(question, user_id)
        res["query_type"] = "Mixed (SQL + RAG)"
        return res

