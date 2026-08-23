import datetime as dt
import hashlib
import html
import json
import uuid
from collections import Counter
from pathlib import Path

import streamlit as st


st.set_page_config(
    page_title="图书馆跨时空留言板",
    page_icon="📜",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "messages_data.json"
HOT_FILE = BASE_DIR / "hot_data.json"
USERS_FILE = BASE_DIR / "users_data.json"
ADMIN_ACCOUNT = "1419742865"

BOOKS = {
    "9787544291163": {"name": "百年孤独", "author": "加西亚·马尔克斯", "theme": "魔幻现实主义", "icon": "📚"},
    "9787020002207": {"name": "红楼梦", "author": "曹雪芹", "theme": "古典文学", "icon": "🏮"},
    "9787544253994": {"name": "三体", "author": "刘慈欣", "theme": "科幻", "icon": "🌌"},
    "9787532769278": {"name": "活着", "author": "余华", "theme": "现实主义", "icon": "🕯️"},
    "9787540480590": {"name": "围城", "author": "钱钟书", "theme": "讽刺文学", "icon": "🏛️"},
    "9787020024759": {"name": "平凡的世界", "author": "路遥", "theme": "现实主义", "icon": "🌾"},
}

EMPTY_MESSAGES = {}
EMPTY_HOT_DATA = {"hot_discussions": [], "hot_searches": [], "visit_stats": {}}


def read_json(path, default):
    if not path.exists():
        return default.copy() if isinstance(default, dict) else list(default)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, type(default)) else default.copy()
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return default.copy() if isinstance(default, dict) else list(default)


def write_json(path, value):
    try:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except OSError as error:
        st.error(f"数据保存失败：{error}")
        return False


def load_messages():
    data = read_json(DATA_FILE, EMPTY_MESSAGES)
    return {str(isbn): entries for isbn, entries in data.items() if isinstance(entries, list)}


def load_users():
    data = read_json(USERS_FILE, {})
    return data if isinstance(data, dict) else {}


def load_hot_data():
    data = read_json(HOT_FILE, EMPTY_HOT_DATA)
    return {
        "hot_discussions": data.get("hot_discussions", []) if isinstance(data, dict) else [],
        "hot_searches": data.get("hot_searches", []) if isinstance(data, dict) else [],
        "visit_stats": data.get("visit_stats", {}) if isinstance(data, dict) else {},
    }


def save_messages():
    write_json(DATA_FILE, st.session_state.messages)


def save_users():
    write_json(USERS_FILE, st.session_state.users)


def save_hot_data():
    write_json(HOT_FILE, st.session_state.hot_data)


def password_hash(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def admin_accounts_from_secrets():
    """读取多管理员配置，兼容旧版单管理员 Secrets。"""
    accounts = {}
    try:
        secrets = st.secrets
        admins = secrets.get("admins", {})
        if hasattr(admins, "items"):
            for account, config in admins.items():
                account = str(account).strip()
                if not account:
                    continue
                if hasattr(config, "get"):
                    password = config.get("password", config.get("admin_password", ""))
                    name = config.get("name", "管理员")
                else:
                    password = config
                    name = "管理员"
                if str(password).strip():
                    accounts[account] = {"password": str(password), "name": str(name).strip() or "管理员"}

        # 兼容旧配置：admin_password / ADMIN_PASSWORD 或 [admin] password
        for key in ("admin_password", "ADMIN_PASSWORD"):
            if key in secrets and str(secrets[key]).strip():
                accounts.setdefault(ADMIN_ACCOUNT, {"password": str(secrets[key]), "name": "管理员"})
        admin = secrets.get("admin", {})
        if hasattr(admin, "get"):
            for key in ("password", "admin_password"):
                if str(admin.get(key, "")).strip():
                    accounts.setdefault(ADMIN_ACCOUNT, {"password": str(admin[key]), "name": "管理员"})
    except Exception:
        return accounts
    return accounts


def is_reserved_admin_account(account):
    return account == ADMIN_ACCOUNT or account in admin_accounts_from_secrets()


def current_user():
    return st.session_state.get("user")


def is_admin():
    user = current_user()
    return bool(user and user.get("role") == "admin")


def all_messages():
    result = []
    for isbn, entries in st.session_state.messages.items():
        for index, message in enumerate(entries):
            if not isinstance(message, dict):
                continue
            result.append({
                **message,
                "id": str(message.get("id", f"legacy-{isbn}-{index}")),
                "isbn": isbn,
                "book": BOOKS.get(isbn, {}).get("name", isbn),
            })
    return result


def search_books(query):
    query = query.strip().lower()
    if not query:
        return []
    return [
        (isbn, book)
        for isbn, book in BOOKS.items()
        if query in isbn or query in book["name"].lower() or query in book["author"].lower() or query in book["theme"].lower()
    ]


def open_book(isbn):
    st.session_state.current_book = isbn
    st.rerun()


def can_delete(message):
    user = current_user()
    return bool(user and (is_admin() or message.get("user_account") == user.get("account")))


def delete_message(isbn, message_id):
    entries = st.session_state.messages.get(isbn, [])
    for index, entry in enumerate(entries):
        if str(entry.get("id")) == str(message_id):
            if not can_delete({**entry, "isbn": isbn}):
                st.error("你只能删除自己的留言。")
                return
            entries.pop(index)
            save_messages()
            st.success("留言已删除。")
            st.rerun()


def show_book_card(isbn, book, count):
    st.markdown(
        f"<div class='book-card'><div class='book-title'>{book['icon']} {html.escape(book['name'])}</div>"
        f"<div>作者：{html.escape(book['author'])}</div><div>主题：{html.escape(book['theme'])}</div>"
        f"<div class='hot-count'>🔥 留言 {count} 条</div></div>",
        unsafe_allow_html=True,
    )
    if st.button("查看留言", key=f"book_{isbn}", use_container_width=True):
        open_book(isbn)


def show_message(entry, isbn, index):
    subject = html.escape(str(entry.get("subject", "未命名主题")))
    name = html.escape(str(entry.get("name", "匿名用户")))
    content = html.escape(str(entry.get("content", "")))
    date = html.escape(str(entry.get("date", entry.get("timestamp", ""))))
    st.markdown(
        f"<div class='message-card'><div class='message-meta'><b>📜 {subject}</b><span>{date}</span></div>"
        f"<div class='message-book'>@{name}</div><div class='ink-text'>{content}</div></div>",
        unsafe_allow_html=True,
    )
    if can_delete(entry) and st.button("删除此留言", key=f"delete_{isbn}_{entry.get('id', index)}"):
        delete_message(isbn, entry.get("id", index))


def show_book_page(isbn):
    book = BOOKS[isbn]
    entries = st.session_state.messages.setdefault(isbn, [])
    st.header(f"{book['icon']} {book['name']}")
    st.caption(f"作者：{book['author']}　|　主题：{book['theme']}　|　ISBN：{isbn}")
    st.subheader(f"💬 留言列表（共 {len(entries)} 条）")
    if not entries:
        st.info("暂时没有留言。登录后可以留下第一条留言。")
    for index, entry in enumerate(entries):
        show_message(entry, isbn, index)

    st.subheader("✒️ 添加留言")
    if not current_user():
        st.info("请先在侧边栏注册或登录，再发布留言。")
    else:
        with st.form(f"message_form_{isbn}"):
            subject = st.text_input("留言主题 *")
            content = st.text_area("留言内容 *", height=120)
            submitted = st.form_submit_button("提交留言", type="primary")
        if submitted:
            if not subject.strip() or not content.strip():
                st.error("请填写留言主题和留言内容。")
            else:
                user = current_user()
                entries.append({
                    "id": uuid.uuid4().hex,
                    "subject": subject.strip(),
                    "name": user.get("name", user.get("account")),
                    "user_account": user.get("account"),
                    "content": content.strip(),
                    "date": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
                })
                save_messages()
                st.success("留言添加成功！")
                st.rerun()
    if st.button("↩ 返回首页", key=f"home_{isbn}"):
        st.session_state.current_book = None
        st.rerun()


def show_my_messages():
    user = current_user()
    if not user:
        st.info("请先登录后查看我的留言。")
        return
    st.header("📝 我的留言")
    mine = [message for message in all_messages() if message.get("user_account") == user.get("account")]
    if not mine:
        st.info("你还没有留言。")
        return
    for index, message in enumerate(mine):
        st.markdown(f"#### {message['book']} · {message.get('subject', '未命名主题')}")
        show_message(message, message["isbn"], index)


def account_panel():
    user = current_user()
    if user:
        st.sidebar.success(f"已登录：{user.get('name', user.get('account'))}{'（管理员）' if is_admin() else ''}")
        if st.sidebar.button("退出登录", use_container_width=True):
            st.session_state.user = None
            st.session_state.page = "首页"
            st.rerun()
        return

    mode = st.sidebar.radio("账户", ["登录", "注册"], horizontal=True)
    if mode == "注册":
        with st.sidebar.form("register_form"):
            account = st.text_input("账号")
            name = st.text_input("昵称")
            password = st.text_input("密码", type="password")
            confirm = st.text_input("确认密码", type="password")
            submitted = st.form_submit_button("注册", use_container_width=True)
        if submitted:
            if not account.strip() or not password:
                st.sidebar.error("账号和密码不能为空。")
            elif is_reserved_admin_account(account.strip()):
                st.sidebar.error("管理员账号不能注册为普通用户。")
            elif account.strip() in st.session_state.users:
                st.sidebar.error("该账号已存在。")
            elif password != confirm:
                st.sidebar.error("两次输入的密码不一致。")
            else:
                st.session_state.users[account.strip()] = {"name": name.strip() or account.strip(), "password": password_hash(password)}
                save_users()
                st.sidebar.success("注册成功，请登录。")
    else:
        with st.sidebar.form("login_form"):
            account = st.text_input("账号")
            password = st.text_input("密码", type="password")
            submitted = st.form_submit_button("登录", use_container_width=True)
        if submitted:
            account = account.strip()
            admin_accounts = admin_accounts_from_secrets()
            admin = admin_accounts.get(account)
            if admin:
                if password == admin["password"]:
                    st.session_state.user = {"account": account, "name": admin["name"], "role": "admin"}
                    st.rerun()
                st.sidebar.error("管理员密码不正确，或未在 Streamlit Secrets 中配置。")
            else:
                saved = st.session_state.users.get(account)
                if saved and saved.get("password") == password_hash(password):
                    st.session_state.user = {"account": account, "name": saved.get("name", account), "role": "user"}
                    st.rerun()
                st.sidebar.error("账号或密码错误。")


st.markdown(
    """
    <style>
    .stApp { background:#f4ecd8; color:#5c4033; font-family:Georgia,"Times New Roman",serif; }
    section[data-testid="stSidebar"] { background:#eaddcf; border-right:2px solid #8b5a2b; }
    h1,h2,h3 { color:#8b4513; }
    .book-card,.message-card { background:#fffaf0; border:1px solid #d2b48c; border-left:5px solid #8b4513; border-radius:6px; padding:15px; margin-bottom:12px; box-shadow:2px 2px 5px rgba(139,69,19,.12); }
    .book-title { color:#8b4513; font-size:1.15rem; font-weight:bold; margin-bottom:8px; }
    .hot-count,.message-book { color:#a0522d; }
    .message-meta { display:flex; justify-content:space-between; color:#8b4513; }
    .message-meta span { color:#a0522d; font-size:.8rem; }
    .ink-text { color:#2f4f4f; white-space:pre-wrap; }
    div.stButton > button { background:#8b4513 !important; color:white !important; border:1px solid #5c4033; }
    </style>
    """,
    unsafe_allow_html=True,
)


for key, loader in (("messages", load_messages), ("users", load_users), ("hot_data", load_hot_data)):
    if key not in st.session_state:
        st.session_state[key] = loader()
if "current_book" not in st.session_state:
    st.session_state.current_book = None
if "page" not in st.session_state:
    st.session_state.page = "首页"


with st.sidebar:
    st.header("🔐 账户与检索")
    account_panel()
    st.divider()
    if current_user() and st.button("我的留言", use_container_width=True):
        st.session_state.page = "我的留言"
        st.session_state.current_book = None
        st.rerun()
    with st.form("search_form"):
        query = st.text_input("书名、作者或 ISBN")
        submitted = st.form_submit_button("检索书籍", use_container_width=True)
    if submitted:
        st.session_state.search_query = query.strip()
        st.session_state.search_results = search_books(query)
        if query.strip():
            searches = st.session_state.hot_data.setdefault("hot_searches", [])
            searches.append(query.strip())
            st.session_state.hot_data["hot_searches"] = searches[-20:]
            save_hot_data()
    uploaded = st.file_uploader("📷 上传旧照片", type=["jpg", "jpeg", "png"])
    if uploaded:
        st.image(uploaded, caption="已加载的历史影像", use_container_width=True)


st.title("📜 图书馆跨时空留言板")
st.markdown("留下你的阅读疑问，也可以回应其他读者的思考。")

if st.session_state.get("current_book"):
    show_book_page(st.session_state.current_book)
elif st.session_state.get("page") == "我的留言":
    show_my_messages()
else:
    messages = all_messages()
    if st.session_state.get("search_query"):
        st.subheader(f"🔎 检索结果：{st.session_state.search_query}")
        results = st.session_state.get("search_results", [])
        if not results:
            st.info("没有找到相关书籍。")
        for index, (isbn, book) in enumerate(results):
            st.write(f"{book['icon']} **{book['name']}**　作者：{book['author']}　ISBN：{isbn}")
            if st.button("进入书页", key=f"result_{isbn}_{index}"):
                open_book(isbn)

    st.subheader("🔥 热点书籍")
    counts = Counter(message["isbn"] for message in messages)
    cols = st.columns(3)
    for index, (isbn, book) in enumerate(BOOKS.items()):
        with cols[index % 3]:
            show_book_card(isbn, book, counts.get(isbn, 0))

    st.subheader("💬 热门讨论")
    discussions = st.session_state.hot_data.get("hot_discussions", [])
    st.info("暂无热门讨论。" if not discussions else "热门讨论数据已加载。")
    if discussions:
        for item in discussions:
            st.write(item)

    st.subheader("🔎 热门搜索")
    searches = st.session_state.hot_data.get("hot_searches", [])
    st.info("暂无热门搜索。" if not searches else "、".join(searches))

    st.subheader("📊 访问统计")
    stats = st.session_state.hot_data.get("visit_stats", {})
    st.info("暂无访问统计。" if not stats else str(stats))

    st.subheader("🕰️ 历史回响")
    st.info("暂时没有留言。" if not messages else f"当前共有 {len(messages)} 条留言。")
