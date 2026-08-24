import datetime as dt
import hashlib
import json
import sqlite3
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import streamlit as st


st.set_page_config(page_title="图书馆跨时空留言板", page_icon="📚", layout="wide")

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "library.db"
LEGACY_MESSAGES = BASE_DIR / "messages_data.json"
LEGACY_USERS = BASE_DIR / "users_data.json"
LEGACY_NOTIFICATIONS = BASE_DIR / "notifications_data.json"
LEGACY_HOT = BASE_DIR / "hot_data.json"
ADMIN_ACCOUNT = "1419742865"

def now_text():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def password_hash(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()
def fetch_json(url):
    request = Request(
        url,
        headers={"User-Agent": "LibraryHackathon/1.0"}
    )
    with urlopen(request, timeout=8) as response:
        return json.loads(response.read().decode("utf-8"))
@st.cache_data(ttl=86400, show_spinner=False)
def lookup_open_library(query):
    query = query.strip()
    if not query:
        return []

    clean_query = query.replace("-", "").replace(" ", "")

    if clean_query.isdigit():
        url = (
            "https://openlibrary.org/search.json"
            f"?isbn={quote(clean_query)}&limit=10"
        )
    else:
        url = (
            "https://openlibrary.org/search.json"
            f"?q={quote(query)}&limit=10"
        )

    try:
        data = fetch_json(url)
    except (
        HTTPError,
        URLError,
        TimeoutError,
        json.JSONDecodeError,
    ):
        return []

    results = []

    for item in data.get("docs", []):
        isbn_list = item.get("isbn", [])

        isbn = next(
            (
                value.replace("-", "").replace(" ", "")
                for value in isbn_list
                if len(value.replace("-", "").replace(" ", "")) == 13
                and value.replace("-", "").replace(" ", "").isdigit()
            ),
            None,
        )

        if not isbn:
            continue

        authors = item.get("author_name", [])
        subjects = item.get("subject", [])

        results.append({
            "isbn": isbn,
            "name": item.get("title", "未知书名"),
            "author": "、".join(authors[:3]) or "未知作者",
            "theme": "、".join(subjects[:3]) or "未分类",
            "icon": "📚",
        })

    return results


def admin_accounts_from_secrets():
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
                    password, name = config, "管理员"
                if str(password).strip():
                    accounts[account] = {"password": str(password), "name": str(name).strip() or "管理员"}
        for key in ("admin_password", "ADMIN_PASSWORD"):
            if key in secrets and str(secrets[key]).strip():
                accounts.setdefault(ADMIN_ACCOUNT, {"password": str(secrets[key]), "name": "管理员"})
        legacy_admin = secrets.get("admin", {})
        if hasattr(legacy_admin, "get"):
            password = legacy_admin.get("password", legacy_admin.get("admin_password", ""))
            if str(password).strip():
                accounts.setdefault(ADMIN_ACCOUNT, {"password": str(password), "name": "管理员"})
    except Exception:
        pass
    return accounts


def is_reserved_admin_account(account):
    return account == ADMIN_ACCOUNT or account in admin_accounts_from_secrets()


def current_user():
    return st.session_state.get("user")


def is_admin():
    user = current_user()
    return bool(user and user.get("role") == "admin")


def can_delete(comment):
    user = current_user()
    return bool(user and (is_admin() or comment.get("user_account") == user.get("account")))


def read_json(path, default):
    if not path.exists():
        return default
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, type(default)) else default
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return default


def connect_db():
    connection = sqlite3.connect(DB_FILE, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    with connect_db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS books (
                isbn TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                author TEXT NOT NULL DEFAULT '',
                theme TEXT NOT NULL DEFAULT '',
                icon TEXT NOT NULL DEFAULT '📚',
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS users (
                account TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS comments (
                id TEXT PRIMARY KEY,
                isbn TEXT NOT NULL REFERENCES books(isbn) ON DELETE RESTRICT,
                parent_id TEXT REFERENCES comments(id) ON DELETE CASCADE,
                subject TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL,
                name TEXT NOT NULL,
                user_account TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_comments_book_parent ON comments(isbn, parent_id);
            CREATE TABLE IF NOT EXISTS comment_likes (
                comment_id TEXT NOT NULL REFERENCES comments(id) ON DELETE CASCADE,
                account TEXT NOT NULL,
                PRIMARY KEY(comment_id, account)
            );
            CREATE TABLE IF NOT EXISTS notifications (
                id TEXT PRIMARY KEY,
                account TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL,
                is_read INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_notifications_account ON notifications(account, is_read);
            CREATE TABLE IF NOT EXISTS searches (
                query TEXT PRIMARY KEY,
                count INTEGER NOT NULL DEFAULT 0,
                last_used TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS visits (
                visit_date TEXT PRIMARY KEY,
                count INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        migrate_legacy_data(db)


def normalize_legacy_comment(comment, fallback_id):
    if not isinstance(comment, dict):
        return None
    return {
        "id": str(comment.get("id") or fallback_id),
        "subject": str(comment.get("subject", comment.get("message_title", ""))),
        "content": str(comment.get("content", "")).strip(),
        "name": str(comment.get("name", "匿名用户")),
        "user_account": str(comment.get("user_account", comment.get("account", ""))),
        "created_at": str(comment.get("date", comment.get("timestamp", now_text()))),
        "likes": [str(item) for item in comment.get("likes", [])] if isinstance(comment.get("likes", []), list) else [],
        "replies": comment.get("replies", []) if isinstance(comment.get("replies", []), list) else [],
    }


def migrate_comment(db, isbn, comment, parent_id=None, fallback_id=None):
    item = normalize_legacy_comment(comment, fallback_id or uuid.uuid4().hex)
    if not item or not item["content"]:
        return
    comment_id = item["id"]
    exists = db.execute("SELECT 1 FROM comments WHERE id=?", (comment_id,)).fetchone()
    if not exists:
        db.execute(
            "INSERT INTO comments(id,isbn,parent_id,subject,content,name,user_account,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (comment_id, isbn, parent_id, item["subject"], item["content"], item["name"], item["user_account"], item["created_at"]),
        )
        db.executemany(
            "INSERT OR IGNORE INTO comment_likes(comment_id,account) VALUES(?,?)",
            [(comment_id, account) for account in item["likes"] if account.strip()],
        )
    for index, reply in enumerate(item["replies"]):
        migrate_comment(db, isbn, reply, comment_id, f"{comment_id}-reply-{index}")


def migrate_legacy_data(db):
    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        users = read_json(LEGACY_USERS, {})
        if isinstance(users, dict):
            for account, user in users.items():
                if isinstance(user, dict) and user.get("password"):
                    db.execute(
                        "INSERT OR IGNORE INTO users(account,name,password_hash,created_at) VALUES(?,?,?,?)",
                        (str(account), str(user.get("name", account)), str(user["password"]), now_text()),
                    )
    if db.execute("SELECT COUNT(*) FROM comments").fetchone()[0] == 0:
        messages = read_json(LEGACY_MESSAGES, {})
        if isinstance(messages, dict):
            for isbn, entries in messages.items():
                if db.execute("SELECT 1 FROM books WHERE isbn=?", (str(isbn),)).fetchone() is None:
                    db.execute(
                        "INSERT INTO books(isbn,name,author,theme,icon,enabled,created_at) VALUES(?,?,?,?,?,1,?)",
                        (str(isbn), str(isbn), "", "", "📚", now_text()),
                    )
                for index, entry in enumerate(entries if isinstance(entries, list) else []):
                    migrate_comment(db, str(isbn), entry, None, f"legacy-{isbn}-{index}")
    if db.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] == 0:
        notifications = read_json(LEGACY_NOTIFICATIONS, {})
        if isinstance(notifications, dict):
            for account, items in notifications.items():
                for item in items if isinstance(items, list) else []:
                    if isinstance(item, dict):
                        db.execute(
                            "INSERT OR IGNORE INTO notifications(id,account,title,body,created_at,is_read) VALUES(?,?,?,?,?,?)",
                            (str(item.get("id", uuid.uuid4().hex)), str(account), str(item.get("title", "通知")), str(item.get("body", "")), str(item.get("date", now_text())), int(bool(item.get("read")))),
                        )
    hot = read_json(LEGACY_HOT, {})
    if isinstance(hot, dict) and db.execute("SELECT COUNT(*) FROM searches").fetchone()[0] == 0:
        for query in hot.get("hot_searches", []) if isinstance(hot.get("hot_searches", []), list) else []:
            db.execute("INSERT INTO searches(query,count,last_used) VALUES(?,?,?) ON CONFLICT(query) DO UPDATE SET count=count+1,last_used=excluded.last_used", (str(query), 1, now_text()))
        for visit_date, count in (hot.get("visit_stats", {}) or {}).items():
            db.execute("INSERT OR IGNORE INTO visits(visit_date,count) VALUES(?,?)", (str(visit_date), int(count)))


def books(include_disabled=False):
    query = "SELECT * FROM books"
    if not include_disabled:
        query += " WHERE enabled=1"
    query += " ORDER BY name COLLATE NOCASE"
    with connect_db() as db:
        return [dict(row) for row in db.execute(query)]
def save_remote_book(book):
    with connect_db() as db:
        db.execute(
            """
            INSERT INTO books(
                isbn,
                name,
                author,
                theme,
                icon,
                enabled,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(isbn) DO UPDATE SET
                name = excluded.name,
                author = excluded.author,
                theme = excluded.theme,
                icon = excluded.icon,
                enabled = 1
            """,
            (
                book["isbn"],
                book["name"],
                book["author"],
                book["theme"],
                book["icon"],
                now_text(),
            ),
        )


def get_book(isbn):
    with connect_db() as db:
        row = db.execute("SELECT * FROM books WHERE isbn=?", (isbn,)).fetchone()
        return dict(row) if row else None


def search_books(query):
    query = query.strip().lower()
    if not query:
        return []
    with connect_db() as db:
        rows = db.execute(
            "SELECT * FROM books WHERE enabled=1 AND (lower(isbn) LIKE ? OR lower(name) LIKE ? OR lower(author) LIKE ? OR lower(theme) LIKE ?) ORDER BY name",
            tuple(f"%{query}%" for _ in range(4)),
        ).fetchall()
        db.execute("INSERT INTO searches(query,count,last_used) VALUES(?,?,?) ON CONFLICT(query) DO UPDATE SET count=count+1,last_used=excluded.last_used", (query, 1, now_text()))
        return [dict(row) for row in rows]


def open_book(isbn):
    """打开书籍留言页。"""
    if get_book(isbn) is None:
        st.error("书籍不存在或已被停用。")
        return
    st.session_state.current_book = isbn
    st.session_state.page = "首页"
    st.rerun()


def comment_rows(isbn):
    with connect_db() as db:
        rows = db.execute(
            """
            SELECT c.*, COUNT(cl.account) AS likes_count
            FROM comments c LEFT JOIN comment_likes cl ON cl.comment_id=c.id
            WHERE c.isbn=? GROUP BY c.id ORDER BY likes_count DESC, c.created_at DESC
            """,
            (isbn,),
        ).fetchall()
        return [dict(row) for row in rows]


def comment_tree(isbn, account=None):
    rows = comment_rows(isbn)
    by_parent = {}
    for row in rows:
        row["replies"] = []
        row["liked"] = False
        by_parent.setdefault(row["parent_id"], []).append(row)
    if account:
        with connect_db() as db:
            liked_ids = {row[0] for row in db.execute("SELECT comment_id FROM comment_likes WHERE account=?", (account,))}
        for row in rows:
            row["liked"] = row["id"] in liked_ids
    for row in rows:
        row["replies"] = by_parent.get(row["id"], [])
    return by_parent.get(None, [])


def comment_count(isbn):
    with connect_db() as db:
        return db.execute("SELECT COUNT(*) FROM comments WHERE isbn=?", (isbn,)).fetchone()[0]


def create_comment(isbn, parent_id, subject, content):
    user = current_user()
    if not user:
        return
    comment_id = uuid.uuid4().hex
    with connect_db() as db:
        db.execute(
            "INSERT INTO comments(id,isbn,parent_id,subject,content,name,user_account,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (comment_id, isbn, parent_id, subject.strip(), content.strip(), user.get("name", user.get("account")), user.get("account"), now_text()),
        )
    if parent_id:
        parent = get_comment(parent_id)
        if parent:
            notify_accounts = {parent["user_account"]}
            notify_users(notify_accounts, "你的留言收到新回复", f"有人回复了你在《{get_book(isbn)['name']}》下的留言。")


def get_comment(comment_id):
    with connect_db() as db:
        row = db.execute("SELECT * FROM comments WHERE id=?", (comment_id,)).fetchone()
        return dict(row) if row else None


def delete_comment(comment_id):
    target = get_comment(comment_id)
    user = current_user()
    if not target or not user:
        return
    if not is_admin() and target["user_account"] != user.get("account"):
        st.error("普通用户只能删除自己的留言。")
        return
    with connect_db() as db:
        db.execute("DELETE FROM comments WHERE id=?", (comment_id,))
    if is_admin() and target["user_account"]:
        notify_users({target["user_account"]}, "你的留言已被管理员删除", f"《{get_book(target['isbn'])['name']}》中的留言已被管理员删除。")


def toggle_like(comment_id):
    user = current_user()
    if not user:
        st.info("请先登录后点赞。")
        return
    account = str(user.get("account"))
    with connect_db() as db:
        exists = db.execute("SELECT 1 FROM comment_likes WHERE comment_id=? AND account=?", (comment_id, account)).fetchone()
        if exists:
            db.execute("DELETE FROM comment_likes WHERE comment_id=? AND account=?", (comment_id, account))
        else:
            db.execute("INSERT OR IGNORE INTO comment_likes(comment_id,account) VALUES(?,?)", (comment_id, account))


def notify_users(accounts, title, body):
    actor = current_user()
    recipients = {str(account) for account in accounts if account}
    if actor:
        recipients.discard(str(actor.get("account")))
    if not recipients:
        return
    with connect_db() as db:
        for account in recipients:
            db.execute("INSERT INTO notifications(id,account,title,body,created_at,is_read) VALUES(?,?,?,?,?,0)", (uuid.uuid4().hex, account, title, body, now_text()))


def notification_rows(account):
    with connect_db() as db:
        return [dict(row) for row in db.execute("SELECT * FROM notifications WHERE account=? ORDER BY is_read,created_at DESC", (account,))]


def mark_notifications_read(account):
    with connect_db() as db:
        db.execute("UPDATE notifications SET is_read=1 WHERE account=?", (account,))


def record_visit():
    if st.session_state.get("visit_recorded"):
        return
    with connect_db() as db:
        db.execute(
            "INSERT INTO visits(visit_date,count) VALUES(?,1) ON CONFLICT(visit_date) DO UPDATE SET count=count+1",
            (dt.date.today().isoformat(),),
        )
    st.session_state.visit_recorded = True


def render_reply(reply, isbn, depth):
    indent = "　" * min(depth, 8)
    st.write(f"{indent}↳ @{reply['name']} · 👍 {reply['likes_count']} · {reply['created_at']}")
    st.write(f"{indent}{reply['content']}")
    render_comment_actions(reply, isbn, depth)
    replies = reply.get("replies", [])
    if replies:
        key = f"replies_{reply['id']}"
        expanded = st.session_state.setdefault("expanded_replies", set())
        if key not in expanded:
            if st.button(f"{indent}查看回复（{len(replies)}）", key=f"show_{reply['id']}"):
                expanded.add(key)
                st.rerun()
        else:
            if st.button(f"{indent}收起回复", key=f"hide_{reply['id']}"):
                expanded.discard(key)
                st.rerun()
            limits = st.session_state.setdefault("reply_limits", {})
            limit = limits.get(key, 5)
            for child in replies[:limit]:
                render_reply(child, isbn, depth + 1)
            if limit < len(replies) and st.button(f"{indent}查看更多回复（还剩 {len(replies) - limit} 条）", key=f"more_{reply['id']}"):
                limits[key] = limit + 5
                st.rerun()


def render_comment_actions(comment, isbn, depth=0):
    columns = st.columns([1, 1, 1, 5])
    label = "取消点赞" if comment.get("liked") else "点赞"
    if columns[0].button(f"{label}（{comment['likes_count']}）", key=f"like_{comment['id']}"):
        toggle_like(comment["id"])
        st.rerun()
    if can_delete(comment) and columns[1].button("删除", key=f"delete_{comment['id']}"):
        delete_comment(comment["id"])
        st.rerun()
    if current_user() and columns[2].button("回复", key=f"reply_{comment['id']}"):
        st.session_state.reply_target = comment["id"]
        st.rerun()
    elif not current_user():
        columns[2].caption("登录后互动")
    if current_user() and st.session_state.get("reply_target") == comment["id"]:
        with st.form(f"reply_form_{comment['id']}"):
            content = st.text_area("回复内容", key=f"reply_text_{comment['id']}", height=70)
            if st.form_submit_button("提交回复"):
                if content.strip():
                    create_comment(isbn, comment["id"], "", content)
                    st.session_state.reply_target = None
                    st.rerun()
                st.warning("回复内容不能为空。")


def render_comment(comment, isbn, depth=0):
    title = comment["subject"] or f"回复 @{comment['name']}"
    with st.expander(f"{'↳ ' if depth else ''}{title} · @{comment['name']} · 👍 {comment['likes_count']}"):
        st.write(comment["content"])
        st.caption(comment["created_at"])
        render_comment_actions(comment, isbn, depth)
        replies = comment.get("replies", [])
        if replies:
            key = f"replies_{comment['id']}"
            expanded = st.session_state.setdefault("expanded_replies", set())
            if key not in expanded:
                if st.button(f"查看回复（{len(replies)}）", key=f"show_{comment['id']}"):
                    expanded.add(key)
                    st.rerun()
            else:
                if st.button("收起回复", key=f"hide_{comment['id']}"):
                    expanded.discard(key)
                    st.rerun()
                limits = st.session_state.setdefault("reply_limits", {})
                limit = limits.get(key, 5)
                for reply in replies[:limit]:
                    render_reply(reply, isbn, depth + 1)
                if limit < len(replies):
                    if st.button(f"查看更多回复（还剩 {len(replies) - limit} 条）", key=f"more_{comment['id']}"):
                        limits[key] = limit + 5
                        st.rerun()


def show_book_page(isbn):
    book = get_book(isbn)
    if not book:
        st.error("书籍不存在或已被删除。")
        return
    account = current_user().get("account") if current_user() else None
    comments = comment_tree(isbn, account)
    st.header(f"{book['icon']} {book['name']}")
    st.caption(f"作者：{book['author']} · 主题：{book['theme']} · ISBN：{isbn}")
    st.subheader(f"留言（{len(comments)} 条）")
    if not comments:
        st.info("暂时没有留言。")
    for comment in comments:
        render_comment(comment, isbn)
    if current_user():
        with st.form(f"new_comment_{isbn}"):
            subject = st.text_input("主题")
            content = st.text_area("留言内容")
            if st.form_submit_button("提交留言"):
                if subject.strip() and content.strip():
                    create_comment(isbn, None, subject, content)
                    st.rerun()
                st.warning("主题和留言内容不能为空。")
    else:
        st.info("登录后可以发布留言、点赞和回复。")
    if st.button("返回首页", key=f"home_{isbn}"):
        st.session_state.current_book = None
        st.rerun()


def show_my_messages():
    user = current_user()
    if not user:
        st.info("请先登录。")
        return
    with connect_db() as db:
        rows = [dict(row) for row in db.execute("SELECT c.*, COUNT(cl.account) likes_count FROM comments c LEFT JOIN comment_likes cl ON cl.comment_id=c.id WHERE c.user_account=? GROUP BY c.id ORDER BY likes_count DESC, c.created_at DESC", (user["account"],))]
    st.header("我的留言")
    if not rows:
        st.info("你还没有留言。")
    for row in rows:
        st.write(f"{row['subject'] or '回复'} · {row['created_at']} · 👍 {row['likes_count']}")
        st.write(row["content"])


def show_notifications():
    user = current_user()
    if not user:
        st.info("请先登录。")
        return
    rows = notification_rows(user["account"])
    st.header("通知")
    if st.button("全部标记为已读"):
        mark_notifications_read(user["account"])
        st.rerun()
    if not rows:
        st.info("暂无通知。")
    for row in rows:
        st.write(f"{'未读 · ' if not row['is_read'] else ''}{row['title']} · {row['created_at']}")
        st.info(row["body"])


def show_book_admin():
    if not is_admin():
        st.error("只有管理员可以管理书籍。")
        return
    st.header("书籍管理")
    all_books = books(include_disabled=True)
    with st.form("add_book"):
        st.subheader("添加书籍")
        isbn = st.text_input("ISBN")
        name = st.text_input("书名")
        author = st.text_input("作者")
        theme = st.text_input("主题")
        icon = st.text_input("图标", value="📚")
        if st.form_submit_button("添加"):
            if not isbn.strip() or not name.strip():
                st.error("ISBN 和书名不能为空。")
            else:
                try:
                    with connect_db() as db:
                        db.execute("INSERT INTO books(isbn,name,author,theme,icon,enabled,created_at) VALUES(?,?,?,?,?,1,?)", (isbn.strip(), name.strip(), author.strip(), theme.strip(), icon.strip() or "📚", now_text()))
                    st.success("书籍已添加。")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("该 ISBN 已存在。")
    if all_books:
        selected = st.selectbox("选择要编辑的书籍", [book["isbn"] for book in all_books])
        book = next(book for book in all_books if book["isbn"] == selected)
        with st.form(f"edit_book_{selected}"):
            name = st.text_input("书名", value=book["name"])
            author = st.text_input("作者", value=book["author"])
            theme = st.text_input("主题", value=book["theme"])
            icon = st.text_input("图标", value=book["icon"])
            enabled = st.checkbox("启用", value=bool(book["enabled"]))
            if st.form_submit_button("保存修改"):
                with connect_db() as db:
                    db.execute("UPDATE books SET name=?,author=?,theme=?,icon=?,enabled=? WHERE isbn=?", (name.strip(), author.strip(), theme.strip(), icon.strip() or "📚", int(enabled), selected))
                st.success("书籍已更新。")
                st.rerun()
        if comment_count(selected) == 0 and st.button("删除该书籍", key=f"remove_book_{selected}"):
            with connect_db() as db:
                db.execute("DELETE FROM books WHERE isbn=?", (selected,))
            st.success("书籍已删除。")
            st.rerun()
        elif comment_count(selected):
            st.caption("该书已有留言，不能删除；可以停用。")


def account_panel():
    user = current_user()
    if user:
        unread = len([row for row in notification_rows(user["account"]) if not row["is_read"]])
        st.sidebar.write(f"已登录：{user['name']}{'（管理员）' if is_admin() else ''}")
        if st.sidebar.button(f"通知（{unread}）"):
            st.session_state.page = "通知"
            st.rerun()
        if is_admin() and st.sidebar.button("书籍管理"):
            st.session_state.page = "书籍管理"
            st.rerun()
        if st.sidebar.button("我的留言"):
            st.session_state.page = "我的留言"
            st.rerun()
        if st.sidebar.button("退出登录"):
            st.session_state.user = None
            st.session_state.page = "首页"
            st.rerun()
        return
    mode = st.sidebar.radio("账户", ["登录", "注册"], horizontal=True)
    if mode == "注册":
        with st.sidebar.form("register"):
            account = st.text_input("账号")
            name = st.text_input("昵称")
            password = st.text_input("密码", type="password")
            confirm = st.text_input("确认密码", type="password")
            submit = st.form_submit_button("注册")
        if submit:
            if not account.strip() or not password:
                st.sidebar.error("账号和密码不能为空。")
            elif account.strip() == ADMIN_ACCOUNT or account.strip() in admin_accounts_from_secrets():
                st.sidebar.error("管理员账号不能注册为普通用户。")
            elif password != confirm:
                st.sidebar.error("两次密码不一致。")
            else:
                try:
                    with connect_db() as db:
                        db.execute("INSERT INTO users(account,name,password_hash,created_at) VALUES(?,?,?,?)", (account.strip(), name.strip() or account.strip(), password_hash(password), now_text()))
                    st.sidebar.success("注册成功，请登录。")
                except sqlite3.IntegrityError:
                    st.sidebar.error("该账号已存在。")
    else:
        with st.sidebar.form("login"):
            account = st.text_input("账号")
            password = st.text_input("密码", type="password")
            submit = st.form_submit_button("登录")
        if submit:
            account = account.strip()
            admin = admin_accounts_from_secrets().get(account)
            if admin and password == admin["password"]:
                st.session_state.user = {"account": account, "name": admin["name"], "role": "admin"}
                st.rerun()
            with connect_db() as db:
                user = db.execute("SELECT * FROM users WHERE account=?", (account,)).fetchone()
            if user and user["password_hash"] == password_hash(password):
                st.session_state.user = {"account": account, "name": user["name"], "role": "user"}
                st.rerun()
            st.sidebar.error("账号或密码错误。")


init_db()
if "user" not in st.session_state:
    st.session_state.user = None
if "page" not in st.session_state:
    st.session_state.page = "首页"
if "current_book" not in st.session_state:
    st.session_state.current_book = None
if "expanded_replies" not in st.session_state:
    st.session_state.expanded_replies = set()
if "reply_limits" not in st.session_state:
    st.session_state.reply_limits = {}
if "search_results" not in st.session_state:
    st.session_state.search_results = []
if "remote_results" not in st.session_state:
    st.session_state.remote_results = []
if "search_query" not in st.session_state:
    st.session_state.search_query = ""
record_visit()


with st.sidebar:
    st.header("账户")
    account_panel()
    st.divider()
    with st.form("search"):
        query = st.text_input("搜索书名、作者或 ISBN")

        if st.form_submit_button("搜索"):
            query = query.strip()

            st.session_state.search_query = query
            st.session_state.search_results = search_books(query)
            st.session_state.remote_results = []

            if query and not st.session_state.search_results:
                st.session_state.remote_results = lookup_open_library(query)
    st.file_uploader("上传旧照片", type=["jpg", "jpeg", "png"])


st.title("图书馆跨时空留言板")
page = st.session_state.page
if st.session_state.current_book:
    show_book_page(st.session_state.current_book)
elif page == "我的留言":
    show_my_messages()
elif page == "通知":
    show_notifications()
elif page == "书籍管理":
    show_book_admin()
else:
    results = st.session_state.get("search_results", [])
    if st.session_state.get("search_query"):
        st.subheader(f"搜索结果：{st.session_state.search_query}")
        for book in results:
            if st.button(f"{book['icon']} {book['name']} · {book['isbn']}", key=f"result_{book['isbn']}"):
                open_book(book["isbn"])
    remote_results = st.session_state.get("remote_results", [])

    if remote_results:
        st.subheader("在线书籍")

        for book in remote_results:
            st.write(
                f"{book['icon']} **{book['name']}**"
                f" · {book['author']}"
                f" · ISBN：{book['isbn']}"
            )

            if is_admin():
                if st.button(
                        "导入到书库",
                        key=f"import_{book['isbn']}"
                ):
                    save_remote_book(book)
                    st.session_state.remote_results = []
                    st.success("书籍已自动导入到书库。")
                    st.rerun()
            else:
                st.caption("只有管理员可以导入书籍。")

    if st.session_state.get("search_query") and not results and not remote_results:
        st.info("本地书库和在线书籍资料库都没有找到相关书籍，或在线服务暂时不可用。")

    st.subheader("书籍")
    visible_books = books()
    cols = st.columns(3)
    for index, book in enumerate(visible_books):
        with cols[index % 3]:
            st.write(f"{book['icon']} **{book['name']}**")
            st.caption(f"{book['author']} · {book['theme']} · 留言 {comment_count(book['isbn'])}")
            if st.button("查看留言", key=f"book_{book['isbn']}"):
                open_book(book["isbn"])
    st.subheader("热门搜索")
    with connect_db() as db:
        hot_searches = [row[0] for row in db.execute("SELECT query FROM searches ORDER BY count DESC, last_used DESC LIMIT 10")]
        stats = db.execute("SELECT COALESCE(SUM(count),0) FROM visits").fetchone()[0]
    st.info("暂无热门搜索。" if not hot_searches else "、".join(hot_searches))
    st.subheader("访问统计")
    st.info("暂无访问统计。" if not stats else f"累计访问：{stats}")
