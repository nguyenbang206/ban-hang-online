import re


# ============================================================
# KEYWORDS CHO CÂU HỎI DỮ LIỆU HỆ THỐNG (SQL)
# ============================================================

SQL_KEYWORDS = [
    "doanh thu",
    "hóa đơn",
    "bán chạy",
    "bán chậm",
    "tồn kho",
    "kho",
    "khách hàng",
    "sản phẩm",
    "giá",
    "số lượng",
    "tháng này",
    "tuần này",
    "hôm nay",
    "doanh số",
    "top",
    "nhiều nhất",
    "mua nhiều",
]


# ============================================================
# KEYWORDS CHO CÂU HỎI TÀI LIỆU / KIẾN THỨC (RAG)
# ============================================================

RAG_KEYWORDS = [
    "bảo hành",
    "đổi trả",
    "chính sách",
    "hướng dẫn",
    "quy định",
    "quy trình",
    "điều khoản",
    "thủ tục",
    "điều kiện",
    "hỗ trợ",
    "lỗi kỹ thuật",
    "cách sử dụng",
    "tính năng",
    "mô tả",
    "sử dụng",
]


def _contains_keyword(question, keywords):
    """
    Kiểm tra câu hỏi có chứa ít nhất một keyword hay không.
    re.escape() giúp xử lý keyword an toàn khi dùng regex.
    """

    for keyword in keywords:
        pattern = r"\b" + re.escape(keyword) + r"\b"

        if re.search(pattern, question, re.IGNORECASE):
            return True

    return False


def classify_query(question):
    """
    Phân loại câu hỏi thành 3 loại:

    - sql:
        Câu hỏi cần dữ liệu có cấu trúc từ Database/SQL.

    - rag:
        Câu hỏi cần thông tin từ tài liệu/Vector DB.

    - mixed:
        Câu hỏi cần cả Database/SQL và tài liệu/RAG.
    """

    # Kiểm tra input
    if not question or not isinstance(question, str):
        return "sql"

    # Chuẩn hóa câu hỏi
    q_lower = question.strip().lower()

    # Kiểm tra keyword
    has_sql = _contains_keyword(q_lower, SQL_KEYWORDS)
    has_rag = _contains_keyword(q_lower, RAG_KEYWORDS)

    # ========================================================
    # ROUTING
    # ========================================================

    # Có cả SQL + RAG
    if has_sql and has_rag:
        return "mixed"

    # Chỉ RAG
    if has_rag:
        return "rag"

    # Chỉ SQL hoặc không xác định
    # Hệ thống bán hàng nên mặc định về SQL
    return "sql"


# ============================================================
# TEST KHI CHẠY TRỰC TIẾP FILE
# ============================================================

if __name__ == "__main__":

    test_questions = [
        "Doanh thu tháng này bao nhiêu?",
        "Sản phẩm nào bán chậm?",
        "Chính sách đổi trả sản phẩm là gì?",
        "Quy định bảo hành như thế nào?",
        "Hướng dẫn sử dụng sản phẩm như thế nào?",
        "Sản phẩm nào bán chậm và chính sách xử lý hàng tồn là gì?",
        "Khách hàng nào mua nhiều nhất?",
        "Điều kiện bảo hành của sản phẩm là gì?",
    ]

    print("=" * 60)
    print("TEST RAG ROUTER")
    print("=" * 60)

    for question in test_questions:
        route = classify_query(question)

        print(f"\nCâu hỏi: {question}")
        print(f"Route:   {route}")
        print("-" * 50)

    print("=" * 60)