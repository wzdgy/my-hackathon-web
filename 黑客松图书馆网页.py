from __future__ import annotations

import copy
import datetime as dt
import hashlib
import html
import json
import secrets
from collections import Counter
from pathlib import Path
from typing import Any

import streamlit as st


# =========================
# 页面配置
# =========================

st.set_page_config(
    page_title="图书馆跨时空留言板",
    page_icon="📜",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =========================
# 文件与数据配置
# =========================

BASE_DIR = Path(__file__).resolve().parent

MESSAGES_FILE = BASE_DIR / "messages_data.json"
HOT_DATA_FILE = BASE_DIR / "hot_data.json"
USERS_FILE = BASE_DIR / "users.json"


BOOKS_DATABASE: dict[str, dict[str, str]] = {
    "9787544291163": {
        "name": "百年孤独",
        "author": "加西亚·马尔克斯",
        "theme": "魔幻现实主义",
        "cover_emoji": "📚",
    },
    "9787020002207": {
        "name": "红楼梦",
        "author": "曹雪芹",
        "theme": "古典文学",
        "cover_emoji": "🏮",
    },
    "9787544253994": {
        "name": "三体",
        "author": "刘慈欣",
        "theme": "科幻",
        "cover_emoji": "🌌",
    },
    "9787532769278": {
        "name": "活着",
        "author": "余华",
        "theme": "现实主义",
        "cover_emoji": "🕯️",
    },
    "9787540480590": {
        "name": "围城",
        "author": "钱钟书",
        "theme": "讽刺文学",
        "cover_emoji": "🏛️",
    },
    "9787020024759": {
        "name": "平凡的世界",
        "author": "路遥",
        "theme": "现实主义",
        "cover_emoji": "🌾",
    },
}


DEFAULT_MESSAGES: dict[str, list[dict[str, Any]]] = {
    "9787544291163": [
        {
            "username": "past_reader",
            "subject": "枫叶还在吗？",
            "name": "来自1998年的读者",
            "contact": "",
            "location": "第120页",
            "content": "我在《百年孤独》的第120页夹了一片枫叶，不知道现在的它还在吗？",
            "notes": "这是一封来自过去的留言。",
            "date": "1998-05-12 14:30:00",
        },
        {
            "username": "library_ai",
            "subject": "给未来的读者",
            "name": "图书管理员 AI",
            "contact": "",
            "location": "馆员工作台",
            "content": "那片枫叶已经化作书签永存了。欢迎来到跨时空留言板。",
            "notes": "",
            "date": "2026-08-22 09:00:00",
        },
    ],
    "9787544253994": [
        {
            "username": "space_reader",
            "subject": "如果三体人真的到来",
            "name": "仰望星空",
            "contact": "",
            "location": "序章旁白",
            "content": "我们该如何判断，沉默究竟是善意还是危险？",
            "notes": "欢迎留下你的答案。",
            "date": "2026-08-20 18:20:00",
        }
    ],
}


DEFAULT_HOT_DATA: dict[str, Any] = {
    "book_visits": {
        "9787544291163": 18,
        "9787544253994": 15,
        "9787020002207": 10,
        "9787532769278": 8,
    },
    "book_searches": {
        "百年孤独": 12,
        "三体": 9,
        "红楼梦": 7,
    },
    "discussion_topics": {
        "9787544291163::枫叶还在吗？": {
            "book_isbn": "9787544291163",
            "subject": "枫叶还在吗？",
            "views": 11,
            "replies": 2,
        },
        "9787544253994::如果三体人真的到来": {
            "book_isbn": "9787544253994",
            "subject": "如果三体人真的到来",
            "views": 8,
            "replies": 1,
        },
    },
    "daily_stats": {},
}


# =========================
# JSON 数据读写
# =========================

def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return copy.deepcopy(default)

    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return copy.deepcopy(default)


def save_json(path: Path, value: Any) -> None:
    try:
        with path.open("w", encoding="utf-8") as file:
            json.dump(value, file, ensure_ascii=False, indent=2)
    except OSError as error:
        st.warning(f"数据暂时无法保存：{error}")


def load_messages() -> dict[str, list[dict[str, Any]]]:
    value = load_json(MESSAGES_FILE, DEFAULT_MESSAGES)

    if not isinstance(value, dict):
        return copy.deepcopy(DEFAULT_MESSAGES)

    return {
        str(isbn): entries
        for isbn, entries in value.items()
        if isinstance(entries, list)
    }


def load_hot_data() -> dict[str, Any]:
    value = load_json(HOT_DATA_FILE, DEFAULT_HOT_DATA)

    if not isinstance(value, dict):
        return copy.deepcopy(DEFAULT_HOT_DATA)

    data = copy.deepcopy(DEFAULT_HOT_DATA)

    for key in data:
        if isinstance(value.get(key), dict):
            data[key].update(value[key])

    return data


# =========================
# 用户注册、登录与密码加密
# =========================

def load_users() -> dict[str, str]:
    value = load_json(USERS_FILE, {})
    return value if isinstance(value, dict) else {}


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        200000,
    ).hex()

    return f"{salt}${password_hash}"


def verify_password(password: str, saved_password: str) -> bool:
    try:
        salt, old_hash = saved_password.split("$", 1)
    except ValueError:
        return False

    new_hash = hash_password(password, salt).split("$", 1)[1]

    return secrets.compare_digest(new_hash, old_hash)


def register_user(username: str, password: str) -> tuple[bool, str]:
    username = username.strip()
    users = load_users()

    if not username or not password:
        return False, "账号和密码不能为空。"

    if len(username) < 2:
        return False, "账号至少需要 2 个字符。"

    if len(password) < 6:
        return False, "密码至少需要 6 个字符。"

    if username in users:
        return False, "该账号已经注册过了。"

    users[username] = hash_password(password)
    save_json(USERS_FILE, users)

    return True, "注册成功，请登录。"


def login_user(username: str, password: str) -> tuple[bool, str]:
    username = username.strip()
    users = load_users()

    if username not in users:
        return False, "账号不存在。"

    if not verify_password(password, users[username]):
        return False, "密码错误。"

    return True, "登录成功。"


# =========================
# 热点统计
# =========================

def record_book_visit(isbn: str) -> None:
    visits = st.session_state.hot_data.setdefault("book_visits", {})
    visits[isbn] = int(visits.get(isbn, 0)) + 1

    today = dt.datetime.now().strftime("%Y-%m-%d")
    daily_stats = st.session_state.hot_data.setdefault("daily_stats", {})
    daily_stats.setdefault(today, {})
    daily_stats[today][isbn] = daily_stats[today].get(isbn, 0) + 1

    save_json(HOT_DATA_FILE, st.session_state.hot_data)


def record_book_search(query: str) -> None:
    query = query.strip()

    if not query:
        return

    searches = st.session_state.hot_data.setdefault("book_searches", {})
    searches[query] = int(searches.get(query, 0)) + 1

    save_json(HOT_DATA_FILE, st.session_state.hot_data)


def record_discussion_topic(isbn: str, subject: str) -> None:
    subject = subject.strip()

    if not subject:
        return

    topic_key = f"{isbn}::{subject}"
    topics = st.session_state.hot_data.setdefault("discussion_topics", {})

    topic = topics.setdefault(
        topic_key,
        {
            "book_isbn": isbn,
            "subject": subject,
            "views": 0,
            "replies": 0,
        },
    )

    topic["views"] = int(topic.get("views", 0)) + 1

    save_json(HOT_DATA_FILE, st.session_state.hot_data)


def get_hot_books(limit: int = 6):
    visits = st.session_state.hot_data.get("book_visits", {})

    books = [
        (
            isbn,
            info,
            int(visits.get(isbn, 0)),
        )
        for isbn, info in BOOKS_DATABASE.items()
    ]

    books.sort(key=lambda item: item[2], reverse=True)

    return books[:limit]


def get_hot_discussions(limit: int = 5):
    topics = st.session_state.hot_data.get("discussion_topics", {})

    sorted_topics = sorted(
        topics.values(),
        key=lambda topic: int(topic.get("views", 0)),
        reverse=True,
    )

    result = []

    for topic in sorted_topics:
        isbn = topic.get("book_isbn")

        if isbn in BOOKS_DATABASE:
            result.append(
                {
                    **topic,
                    "book_name": BOOKS_DATABASE[isbn]["name"],
                }
            )

    return result[:limit]


def get_trending_searches(limit: int = 8):
    searches = st.session_state.hot_data.get("book_searches", {})

    return sorted(
        (
            (str(query), int(count))
            for query, count in searches.items()
        ),
        key=lambda item: item[1],
        reverse=True,
    )[:limit]


# =========================
# 搜索与留言
# =========================

def search_books(query: str):
    normalized = query.strip().lower()

    if not normalized:
        return []

    return [
        (isbn, info)
        for isbn, info in BOOKS_DATABASE.items()
        if (
            normalized in isbn
            or normalized in info["name"].lower()
            or normalized in info["author"].lower()
            or normalized in info["theme"].lower()
        )
    ]


def get_all_messages():
    result = []

    for isbn, entries in st.session_state.messages.items():
        if not isinstance(entries, list):
            continue

        for message in entries:
            if isinstance(message, dict):
                result.append(
                    {
                        **message,
                        "isbn": isbn,
                        "book": BOOKS_DATABASE.get(isbn, {}).get(
                            "name",
                            isbn,
                        ),
                    }
                )

    return result


def open_book(isbn: str) -> None:
    st.session_state.current_book = isbn
    st.session_state.current_message = None
    st.session_state.current_page = "home"

    record_book_visit(isbn)

    st.rerun()


# =========================
# 搜索结果
# =========================

def render_search_results() -> None:
    query = st.session_state.get("search_query", "")
    results = st.session_state.get("search_results", [])

    if not query:
        return

    st.subheader(f"🔎 检索结果：{query}")

    if not results:
        st.warning("没有找到相关书籍，请尝试书名、作者或 ISBN。")
        return

    for isbn, info in results:
        col1, col2 = st.columns([4, 1])

        with col1:
            st.markdown(
                f"**{info['cover_emoji']} "
                f"{html.escape(info['name'])}**　"
                f"作者：{html.escape(info['author'])}　"
                f"主题：{html.escape(info['theme'])}"
            )
            st.caption(f"ISBN：{isbn}")

        with col2:
            if st.button(
                "进入书页",
                key=f"search_book_{isbn}",
                use_container_width=True,
            ):
                open_book(isbn)

        st.divider()


# =========================
# 热点区域
# =========================

def render_hot_sections() -> None:
    st.subheader("🔥 热点书籍")

    columns = st.columns(3)

    for index, (isbn, info, count) in enumerate(get_hot_books()):
        with columns[index % 3]:
            st.markdown(
                f"""
                <div class="book-card">
                    <div class="book-title">
                        {info['cover_emoji']} {html.escape(info['name'])}
                    </div>
                    <div>作者：{html.escape(info['author'])}</div>
                    <div>主题：{html.escape(info['theme'])}</div>
                    <div class="hot-count">🔥 访问 {count} 次</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if st.button(
                "查看留言",
                key=f"hot_book_{isbn}",
                use_container_width=True,
            ):
                open_book(isbn)

    st.subheader("💬 热门讨论")

    discussions = get_hot_discussions()

    if not discussions:
        st.info("暂时还没有热门讨论，欢迎发表第一条留言。")

    for index, topic in enumerate(discussions):
        col1, col2, col3 = st.columns([4, 1, 1])

        with col1:
            st.markdown(
                f"**📖 {html.escape(topic['book_name'])}**　"
                f"{html.escape(topic['subject'])}"
            )

        with col2:
            st.caption(f"👁 {topic.get('views', 0)} 次")

        with col3:
            if st.button(
                "查看",
                key=f"hot_topic_{index}",
                use_container_width=True,
            ):
                open_book(topic["book_isbn"])

    st.subheader("📈 热门搜索")

    searches = get_trending_searches()

    if not searches:
        st.info("暂时还没有搜索记录。")

    search_columns = st.columns(4)

    for index, (query, count) in enumerate(searches):
        with search_columns[index % 4]:
            if st.button(
                f"🔍 {query}（{count}）",
                key=f"trending_{index}_{query}",
                use_container_width=True,
            ):
                st.session_state.search_query = query
                st.session_state.search_results = search_books(query)
                st.rerun()


# =========================
# 历史回响
# =========================

def render_timeline() -> None:
    messages = get_all_messages()

    messages.sort(
        key=lambda message: message.get("date", ""),
        reverse=True,
    )

    st.subheader("⏳ 历史回响")

    if not messages:
        st.info("还没有留言。")
        return

    for message in messages[:10]:
        user = html.escape(
            str(message.get("name", "匿名访客"))
        )
        content = html.escape(
            str(message.get("content", ""))
        )
        subject = html.escape(
            str(message.get("subject", "未命名主题"))
        )
        date = html.escape(
            str(message.get("date", ""))
        )
        book_name = html.escape(
            str(message.get("book", "未知书籍"))
        )

        st.markdown(
            f"""
            <div class="message-card">
                <div class="message-meta">
                    <strong>@{user}</strong>
                    <span>{date}</span>
                </div>
                <div class="message-book">
                    📖 {book_name} · {subject}
                </div>
                <div class="ink-text">
                    “{content}”
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# =========================
# 留言统计
# =========================

def render_message_statistics() -> None:
    all_messages = get_all_messages()

    st.subheader("📊 留言统计")

    if not all_messages:
        st.info("暂时没有留言统计数据。")
        return

    book_counts = Counter(
        message["isbn"]
        for message in all_messages
    )

    statistics = []

    for isbn, count in book_counts.most_common():
        book_info = BOOKS_DATABASE.get(isbn, {})

        statistics.append(
            {
                "书名": book_info.get("name", isbn),
                "作者": book_info.get("author", "未知作者"),
                "ISBN": isbn,
                "留言数量": count,
            }
        )

    col1, col2 = st.columns(2)

    with col1:
        st.metric("全部留言", len(all_messages))

    with col2:
        st.metric("涉及书籍", len(book_counts))

    st.dataframe(
        statistics,
        hide_index=True,
        use_container_width=True,
    )


# =========================
# 我的留言
# =========================

def render_my_messages() -> None:
    username = st.session_state.current_user

    my_messages = [
        message
        for message in get_all_messages()
        if message.get("username") == username
    ]

    st.header(f"📬 {username} 的留言")

    if not my_messages:
        st.info("您还没有发表过留言。")
    else:
        st.success(
            f"您一共发表了 {len(my_messages)} 条留言。"
        )

        for message in sorted(
            my_messages,
            key=lambda item: item.get("date", ""),
            reverse=True,
        ):
            book_name = html.escape(
                str(message.get("book", "未知书籍"))
            )
            subject = html.escape(
                str(message.get("subject", "未命名主题"))
            )
            content = html.escape(
                str(message.get("content", ""))
            )
            date = html.escape(
                str(message.get("date", ""))
            )

            st.markdown(
                f"""
                <div class="message-card">
                    <div class="message-meta">
                        <strong>{book_name}</strong>
                        <span>{date}</span>
                    </div>
                    <div class="message-book">
                        📜 {subject}
                    </div>
                    <div class="ink-text">
                        “{content}”
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    if st.button(
        "↩ 返回首页",
        key="back_home_from_mine",
    ):
        st.session_state.current_page = "home"
        st.rerun()


# =========================
# 留言详情
# =========================

def render_message_detail(isbn: str, index: int) -> None:
    info = BOOKS_DATABASE[isbn]
    entries = st.session_state.messages.get(isbn, [])

    if index < 0 or index >= len(entries):
        st.session_state.current_message = None
        st.rerun()

    message = entries[index]

    st.header(
        f"{info['cover_emoji']} {info['name']}"
    )

    st.subheader(
        f"留言主题：{message.get('subject', '未命名主题')}"
    )

    st.write(
        f"**留言者：** "
        f"{message.get('name', '匿名访客')}"
    )

    st.write(
        f"**留言时间：** "
        f"{message.get('date', '')}"
    )

    st.write(
        f"**疑问位置：** "
        f"{message.get('location') or '未指定'}"
    )

    st.divider()

    st.write(message.get("content", ""))

    if message.get("notes"):
        st.caption(
            f"备注：{message['notes']}"
        )

    if st.button(
        "↩ 返回留言列表",
        key="back_to_messages",
    ):
        st.session_state.current_message = None
        st.rerun()


# =========================
# 添加留言
# =========================

def render_add_message(isbn: str) -> None:
    info = BOOKS_DATABASE[isbn]

    st.header(
        f"✒️ 给《{info['name']}》添加留言"
    )

    with st.form(f"new_message_form_{isbn}"):
        subject = st.text_input(
            "留言主题 *",
            placeholder="例如：枫叶还在吗？",
        )

        col1, col2 = st.columns(2)

        with col1:
            name = st.text_input(
                "昵称",
                placeholder="留空则使用登录账号",
            )

        with col2:
            location = st.text_input(
                "疑问位置",
                placeholder="例如：第120页",
            )

        content = st.text_area(
            "留言内容 *",
            height=150,
        )

        notes = st.text_area(
            "备注（可选）",
            height=90,
        )

        submitted = st.form_submit_button(
            "提交留言",
            type="primary",
        )

    if submitted:
        if not st.session_state.current_user:
            st.warning("请先登录后再提交留言。")
            return

        if not subject.strip() or not content.strip():
            st.error("请填写留言主题和留言内容。")
            return

        new_message = {
            "username": st.session_state.current_user,
            "subject": subject.strip(),
            "name": name.strip() or st.session_state.current_user,
            "contact": "",
            "location": location.strip(),
            "content": content.strip(),
            "notes": notes.strip(),
            "date": dt.datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        }

        st.session_state.messages.setdefault(
            isbn,
            [],
        ).append(new_message)

        save_json(
            MESSAGES_FILE,
            st.session_state.messages,
        )

        record_discussion_topic(isbn, subject)

        st.success("留言添加成功！")

        st.session_state.current_message = None
        st.rerun()

    if st.button(
        "取消",
        key="cancel_new_message",
    ):
        st.session_state.current_message = None
        st.rerun()


# =========================
# 书籍页面
# =========================

def render_book_page(isbn: str) -> None:
    info = BOOKS_DATABASE[isbn]
    current_message = st.session_state.current_message

    if current_message == "new":
        render_add_message(isbn)
        return

    if isinstance(current_message, int):
        render_message_detail(isbn, current_message)
        return

    st.header(
        f"{info['cover_emoji']} {info['name']}"
    )

    st.caption(
        f"作者：{info['author']}　"
        f"|　主题：{info['theme']}　"
        f"|　ISBN：{isbn}"
    )

    entries = st.session_state.messages.get(isbn, [])

    st.subheader(
        f"💬 留言列表（共 {len(entries)} 条）"
    )

    if not entries:
        st.info(
            "暂时没有留言，成为第一个留言的人吧！"
        )

    for index, message in enumerate(entries):
        col1, col2, col3 = st.columns([4, 1, 1])

        with col1:
            st.markdown(
                f"**📜 "
                f"{html.escape(str(message.get('subject', '未命名主题')))}**"
            )

        with col2:
            st.caption(
                f"👤 "
                f"{html.escape(str(message.get('name', '匿名访客')))}"
            )

        with col3:
            if st.button(
                "查看",
                key=f"message_{isbn}_{index}",
                use_container_width=True,
            ):
                st.session_state.current_message = index

                record_discussion_topic(
                    isbn,
                    str(message.get("subject", "")),
                )

                st.rerun()

        st.divider()

    if st.button(
        "✒️ 添加新留言",
        type="primary",
        key=f"add_message_{isbn}",
    ):
        if not st.session_state.current_user:
            st.warning("请先登录后再添加留言。")
        else:
            st.session_state.current_message = "new"
            st.rerun()

    if st.button(
        "↩ 返回首页",
        key=f"back_home_{isbn}",
    ):
        st.session_state.current_book = None
        st.session_state.current_message = None
        st.session_state.current_page = "home"
        st.rerun()


# =========================
# 复古 UI
# =========================

st.markdown(
    """
    <style>
    .stApp {
        background-color: #f4ecd8;
        background-image: url("https://www.transparenttextures.com/patterns/aged-paper.png");
        color: #5c4033;
        font-family: Georgia, "Times New Roman", serif;
    }

    section[data-testid="stSidebar"] {
        background: #eaddcf;
        border-right: 2px solid #8b5a2b;
    }

    h1, h2, h3 {
        color: #8b4513;
        text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.1);
    }

    .message-card,
    .book-card {
        background: rgba(255, 250, 240, 0.92);
        border: 1px solid #d2b48c;
        border-left: 5px solid #8b4513;
        border-radius: 6px;
        padding: 15px;
        margin-bottom: 14px;
        box-shadow: 2px 2px 5px rgba(139, 69, 19, 0.12);
    }

    .book-title {
        color: #8b4513;
        font-size: 1.15rem;
        font-weight: 700;
        margin-bottom: 8px;
    }

    .hot-count {
        color: #a0522d;
        margin-top: 8px;
    }

    .message-meta {
        display: flex;
        justify-content: space-between;
        color: #8b4513;
        margin-bottom: 6px;
    }

    .message-meta span {
        color: #a0522d;
        font-size: 0.8rem;
    }

    .message-book {
        color: #a0522d;
        margin-bottom: 6px;
    }

    .ink-text {
        color: #2f4f4f;
        font-style: italic;
        white-space: pre-wrap;
        overflow-wrap: anywhere;
    }

    div.stButton > button {
        background: #8b4513 !important;
        color: #fff !important;
        border: 1px solid #5c4033;
        border-radius: 5px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================
# Session State
# =========================

defaults = {
    "messages": load_messages(),
    "hot_data": load_hot_data(),
    "current_book": None,
    "current_message": None,
    "current_page": "home",
    "search_query": "",
    "search_results": [],
    "current_user": None,
}

for key, default in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = default


# =========================
# 侧边栏
# =========================

with st.sidebar:
    st.header("👤 用户中心")

    if st.session_state.current_user:
        st.success(
            f"已登录：{st.session_state.current_user}"
        )

        if st.button(
            "📬 我的留言",
            key="my_messages_button",
        ):
            st.session_state.current_page = "mine"
            st.session_state.current_book = None
            st.session_state.current_message = None
            st.rerun()

        if st.button(
            "退出登录",
            key="logout_button",
        ):
            st.session_state.current_user = None
            st.session_state.current_page = "home"
            st.rerun()

    else:
        login_tab, register_tab = st.tabs(
            ["登录", "注册"]
        )

        with login_tab:
            login_name = st.text_input(
                "账号",
                key="login_name",
            )

            login_password = st.text_input(
                "密码",
                type="password",
                key="login_password",
            )

            if st.button(
                "登录",
                key="login_button",
            ):
                success, message = login_user(
                    login_name,
                    login_password,
                )

                if success:
                    st.session_state.current_user = (
                        login_name.strip()
                    )
                    st.session_state.current_page = "home"
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)

        with register_tab:
            register_name = st.text_input(
                "新账号",
                key="register_name",
            )

            register_password = st.text_input(
                "新密码",
                type="password",
                key="register_password",
            )

            if st.button(
                "注册",
                key="register_button",
            ):
                success, message = register_user(
                    register_name,
                    register_password,
                )

                if success:
                    st.success(message)
                else:
                    st.error(message)

    st.divider()

    st.header("🔍 检索与上传")

    with st.form("sidebar_search_form"):
        query = st.text_input(
            "书名、作者或 ISBN",
            placeholder="例如：百年孤独 / 余华 / ISBN",
        )

        search_submitted = st.form_submit_button(
            "检索书籍",
            use_container_width=True,
        )

    if search_submitted:
        st.session_state.search_query = query.strip()
        st.session_state.search_results = search_books(query)
        record_book_search(query)

    uploaded_file = st.file_uploader(
        "📷 上传旧照片",
        type=["jpg", "jpeg", "png"],
    )

    if uploaded_file is not None:
        st.image(
            uploaded_file,
            caption="已加载的历史影像",
            use_container_width=True,
        )

    st.divider()
    st.caption("© 2026 图书馆黑客松项目组")


# =========================
# 主页面
# =========================

st.title("📜 图书馆跨时空留言板")

st.markdown(
    "在这里留下你的疑问，或者回应百年前读者的低语……"
)


if st.session_state.current_page == "mine":
    render_my_messages()

elif st.session_state.current_book:
    render_book_page(
        st.session_state.current_book
    )

else:
    render_search_results()

    if not st.session_state.search_query:
        st.info(
            "请在左侧输入书名、作者或 ISBN，"
            "开始探索书籍与历史留言。"
        )

    render_hot_sections()
    render_message_statistics()
    render_timeline()