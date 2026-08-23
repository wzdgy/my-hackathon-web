import datetime as dt
import hashlib
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
NOTIFICATIONS_FILE = BASE_DIR / "notifications_data.json"
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


def normalize_comment(comment, fallback_id):
    normalized = dict(comment) if isinstance(comment, dict) else {}
    normalized["id"] = str(normalized.get("id") or fallback_id)
    likes = normalized.get("likes", [])
    normalized["likes"] = [str(account) for account in likes if str(account).strip()] if isinstance(likes, list) else []
    replies = normalized.get("replies", [])
    normalized["replies"] = [
        normalize_comment(reply, f"{normalized['id']}-reply-{index}")
        for index, reply in enumerate(replies if isinstance(replies, list) else [])
        if isinstance(reply, dict)
    ]
    return normalized


def load_messages():
    data = read_json(DATA_FILE, EMPTY_MESSAGES)
    result = {}
    for isbn, entries in data.items():
        if isinstance(entries, list):
            result[str(isbn)] = [
                normalize_comment(entry, f"legacy-{isbn}-{index}")
                for index, entry in enumerate(entries)
            ]
    return result


def load_users():
    data = read_json(USERS_FILE, {})
    return data if isinstance(data, dict) else {}


def load_notifications():
    data = read_json(NOTIFICATIONS_FILE, {})
    return {str(account): items for account, items in data.items() if isinstance(items, list)}


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


def save_notifications():
    write_json(NOTIFICATIONS_FILE, st.session_state.notifications)


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
            if isinstance(message, dict):
                result.append({
                    **message,
                    "id": str(message.get("id", f"legacy-{isbn}-{index}")),
                    "isbn": isbn,
                    "book": BOOKS.get(isbn, {}).get("name", isbn),
                })
    return result


def flatten_comments(entries, isbn, book, parent_id=None, depth=0):
    result = []
    for index, comment in enumerate(entries):
        if not isinstance(comment, dict):
            continue
        comment_id = str(comment.get("id", f"legacy-{isbn}-{depth}-{index}"))
        result.append({
            **comment,
            "id": comment_id,
            "isbn": isbn,
            "book": book,
            "parent_id": parent_id,
            "depth": depth,
        })
        result.extend(flatten_comments(comment.get("replies", []), isbn, book, comment_id, depth + 1))
    return result


def all_comments():
    result = []
    for isbn, entries in st.session_state.messages.items():
        result.extend(flatten_comments(entries, isbn, BOOKS.get(isbn, {}).get("name", isbn)))
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


def find_comment(entries, comment_id):
    for comment in entries:
        if str(comment.get("id")) == str(comment_id):
            return comment
        found = find_comment(comment.get("replies", []), comment_id)
        if found:
            return found
    return None


def find_comment_path(entries, comment_id, path=None):
    path = list(path or [])
    for comment in entries:
        current_path = path + [comment]
        if str(comment.get("id")) == str(comment_id):
            return current_path
        found = find_comment_path(comment.get("replies", []), comment_id, current_path)
        if found:
            return found
    return None


def remove_comment(entries, comment_id):
    for index, comment in enumerate(entries):
        if str(comment.get("id")) == str(comment_id):
            return entries.pop(index)
        removed = remove_comment(comment.get("replies", []), comment_id)
        if removed:
            return removed
    return None


def comment_accounts(comment):
    accounts = set()
    account = str(comment.get("user_account", "")).strip()
    if account:
        accounts.add(account)
    for reply in comment.get("replies", []):
        accounts.update(comment_accounts(reply))
    return accounts


def can_delete(comment):
    user = current_user()
    return bool(user and (is_admin() or comment.get("user_account") == user.get("account")))


def notify_users(accounts, title, body):
    recipients = {str(account).strip() for account in accounts if str(account).strip()}
    actor = current_user()
    if actor:
        recipients.discard(str(actor.get("account", "")).strip())
    if not recipients:
        return
    for account in recipients:
        notifications = st.session_state.notifications.setdefault(account, [])
        notifications.insert(0, {
            "id": uuid.uuid4().hex,
            "title": title,
            "body": body,
            "date": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "read": False,
        })
        st.session_state.notifications[account] = notifications[:100]
    save_notifications()


def delete_comment(isbn, comment_id):
    entries = st.session_state.messages.get(isbn, [])
    target = find_comment(entries, comment_id)
    if not target:
        st.warning("这条留言已经不存在。")
        return
    if not can_delete(target):
        st.error("普通用户只能删除自己的留言。")
        return
    deleted_accounts = comment_accounts(target)
    subject = str(target.get("subject", "留言"))
    removed = remove_comment(entries, comment_id)
    if removed is None:
        return
    save_messages()
    if is_admin():
        notify_users(
            deleted_accounts,
            "你的留言已被管理员删除",
            f"《{BOOKS.get(isbn, {}).get('name', isbn)}》中的“{subject}”已被管理员删除。",
        )
    st.success("留言已删除。")
    st.rerun()


def toggle_like(isbn, comment_id):
    user = current_user()
    if not user:
        st.info("请先登录后点赞。")
        return
    target = find_comment(st.session_state.messages.get(isbn, []), comment_id)
    if not target:
        return
    account = str(user.get("account"))
    likes = [str(item) for item in target.get("likes", [])]
    if account in likes:
        likes.remove(account)
    else:
        likes.append(account)
    target["likes"] = likes
    save_messages()
    st.rerun()


def add_reply(isbn, parent_id, content):
    user = current_user()
    if not user or not content.strip():
        return
    entries = st.session_state.messages.get(isbn, [])
    parent = find_comment(entries, parent_id)
    if not parent:
        st.error("回复目标不存在。")
        return
    reply = {
        "id": uuid.uuid4().hex,
        "name": user.get("name", user.get("account")),
        "user_account": user.get("account"),
        "content": content.strip(),
        "date": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "likes": [],
        "replies": [],
    }
    parent.setdefault("replies", []).append(reply)
    path = find_comment_path(entries, parent_id) or [parent]
    recipients = {comment.get("user_account") for comment in path if comment.get("user_account")}
    notify_users(
        recipients,
        "你的留言收到新回复",
        f"有人回复了你在《{BOOKS.get(isbn, {}).get('name', isbn)}》下的留言：“{content.strip()[:80]}”。",
    )
    save_messages()
    st.success("回复已发布。")
    st.rerun()


def show_book_card(isbn, book, count):
    st.write(f"{book['icon']} **{book['name']}**")
    st.caption(f"作者：{book['author']} · 主题：{book['theme']} · 留言：{count}")
    if st.button("查看留言", key=f"book_{isbn}"):
        open_book(isbn)


def comment_likes(comment):
    return len({str(item) for item in comment.get("likes", [])})


def reply_state_key(isbn, comment_id):
    return f"{isbn}:{comment_id}"


def render_replies(comment, isbn, depth):
    replies = sorted(comment.get("replies", []), key=comment_likes, reverse=True)
    if not replies:
        return
    state_key = reply_state_key(isbn, comment.get("id"))
    expanded = st.session_state.setdefault("expanded_replies", set())
    if state_key not in expanded:
        return
    limit_state = st.session_state.setdefault("reply_limits", {})
    limit = limit_state.get(state_key, 5)
    for index, reply in enumerate(replies[:limit]):
        render_comment(reply, isbn, index, depth + 1, include_replies=True)
    if limit < len(replies):
        remaining = len(replies) - limit
        if st.button(f"查看更多回复（还剩 {remaining} 条）", key=f"more_replies_{isbn}_{comment.get('id')}"):
            limit_state[state_key] = limit + 5
            st.rerun()


def render_comment_body(comment, isbn, depth, include_replies):
    comment_id = str(comment.get("id") or "comment")
    name = str(comment.get("name", "匿名用户"))
    content = str(comment.get("content", ""))
    date = str(comment.get("date", comment.get("timestamp", "")))
    likes = [str(item) for item in comment.get("likes", [])]
    state_key = reply_state_key(isbn, comment_id)
    expanded_replies = st.session_state.setdefault("expanded_replies", set())
    reply_target = st.session_state.get("reply_target")
    st.write(content)
    st.caption(date)
    action_columns = st.columns([1, 1, 1, 5])
    liked = current_user() and str(current_user().get("account")) in likes
    if action_columns[0].button(
        f"{'取消点赞' if liked else '点赞'}（{comment_likes(comment)}）",
        key=f"like_{isbn}_{comment_id}",
    ):
        toggle_like(isbn, comment_id)
    if can_delete(comment) and action_columns[1].button("删除", key=f"delete_{isbn}_{comment_id}"):
        delete_comment(isbn, comment_id)
    if current_user() and action_columns[2].button("回复", key=f"reply_{isbn}_{comment_id}"):
        st.session_state.reply_target = (isbn, comment_id)
        st.rerun()
    elif not current_user():
        action_columns[2].caption("登录后可互动")

    if current_user() and reply_target == (isbn, comment_id):
        with st.form(f"reply_form_{isbn}_{comment_id}"):
            reply_content = st.text_area("回复内容", key=f"reply_text_{isbn}_{comment_id}", height=70)
            reply_submitted = st.form_submit_button("提交回复")
        if reply_submitted:
            if reply_content.strip():
                add_reply(isbn, comment_id, reply_content)
            else:
                st.warning("回复内容不能为空。")

    reply_count = len(comment.get("replies", []))
    if reply_count:
        if state_key in expanded_replies:
            if st.button("收起回复", key=f"hide_replies_{isbn}_{comment_id}"):
                expanded_replies.discard(state_key)
                st.rerun()
        elif st.button(f"查看回复（{reply_count}）", key=f"show_replies_{isbn}_{comment_id}"):
            expanded_replies.add(state_key)
            st.rerun()
        if include_replies:
            render_replies(comment, isbn, depth)


def render_comment(comment, isbn, index, depth=0, include_replies=True):
    comment_id = str(comment.get("id", f"comment-{index}"))
    name = str(comment.get("name", "匿名用户"))
    subject = comment.get("subject")
    title = str(subject) if subject else f"回复 @{name}"
    prefix = "" if depth == 0 else "↳ "
    state_key = reply_state_key(isbn, comment_id)
    expanded_replies = st.session_state.setdefault("expanded_replies", set())
    reply_target = st.session_state.get("reply_target")
    expander_open = reply_target == (isbn, comment_id) or state_key in expanded_replies
    if depth == 0:
        with st.expander(f"{prefix}{title} · @{name} · 👍 {comment_likes(comment)}", expanded=expander_open):
            render_comment_body(comment, isbn, depth, include_replies)
    else:
        st.write(f"↳ {title} · @{name} · 👍 {comment_likes(comment)}")
        render_comment_body(comment, isbn, depth, include_replies)


def show_book_page(isbn):
    book = BOOKS[isbn]
    entries = st.session_state.messages.setdefault(isbn, [])
    st.header(f"{book['icon']} {book['name']}")
    st.caption(f"作者：{book['author']}　|　主题：{book['theme']}　|　ISBN：{isbn}")
    st.subheader(f"💬 留言列表（共 {len(entries)} 条）")
    if not entries:
        st.info("暂时没有留言。登录后可以留下第一条留言。")
    for index, entry in enumerate(sorted(entries, key=comment_likes, reverse=True)):
        render_comment(entry, isbn, index)

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
                    "likes": [],
                    "replies": [],
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
    mine = sorted(
        [comment for comment in all_comments() if comment.get("user_account") == user.get("account")],
        key=comment_likes,
        reverse=True,
    )
    if not mine:
        st.info("你还没有留言。")
        return
    for index, comment in enumerate(mine):
        st.markdown(f"#### {comment['book']} · {comment.get('subject', '回复')}")
        render_comment(comment, comment["isbn"], index, depth=0, include_replies=False)


def show_notifications():
    user = current_user()
    if not user:
        st.info("请先登录后查看通知。")
        return
    account = str(user.get("account"))
    notifications = st.session_state.notifications.setdefault(account, [])
    st.header("🔔 通知")
    if not notifications:
        st.info("暂无通知。")
        return
    if st.button("全部标记为已读", key="mark_all_notifications"):
        for notification in notifications:
            notification["read"] = True
        save_notifications()
        st.rerun()
    for notification in notifications:
        prefix = "未读 · " if not notification.get("read") else ""
        st.info(f"{prefix}{notification.get('title', '通知')}\n\n{notification.get('body', '')}\n\n{notification.get('date', '')}")


def account_panel():
    user = current_user()
    if user:
        account = str(user.get("account"))
        unread = sum(1 for item in st.session_state.notifications.get(account, []) if not item.get("read"))
        st.sidebar.success(f"已登录：{user.get('name', account)}{'（管理员）' if is_admin() else ''}")
        if st.sidebar.button(f"🔔 通知 ({unread})", use_container_width=True):
            st.session_state.page = "通知"
            st.session_state.current_book = None
            st.rerun()
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
            admin = admin_accounts_from_secrets().get(account)
            if admin:
                if password == admin["password"]:
                    st.session_state.user = {"account": account, "name": admin["name"], "role": "admin"}
                    st.session_state.page = "首页"
                    st.rerun()
                st.sidebar.error("管理员密码不正确，或未在 Streamlit Secrets 中配置。")
            else:
                saved = st.session_state.users.get(account)
                if saved and saved.get("password") == password_hash(password):
                    st.session_state.user = {"account": account, "name": saved.get("name", account), "role": "user"}
                    st.session_state.page = "首页"
                    st.rerun()
                st.sidebar.error("账号或密码错误。")


for key, loader in (
    ("messages", load_messages),
    ("users", load_users),
    ("notifications", load_notifications),
    ("hot_data", load_hot_data),
):
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
elif st.session_state.get("page") == "通知":
    show_notifications()
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
