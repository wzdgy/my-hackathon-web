from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import secrets
from collections import Counter
from pathlib import Path
from typing import Any

import streamlit as st


# ==================================================
# 页面与文件配置
# ==================================================

st.set_page_config(
    page_title="图书馆跨时空留言板",
    page_icon="📜",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE_DIR = Path(__file__).resolve().parent

MESSAGES_FILE = BASE_DIR / "messages_data.json"
HOT_DATA_FILE = BASE_DIR / "hot_data.json"
USERS_FILE = BASE_DIR / "users.json"


# ==================================================
# 书籍数据
# ==================================================

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


# ==================================================
# JSON 数据读写
# ==================================================

def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return copy.deepcopy(default)

    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return copy.deepcopy(default)


def save_json(path: Path, value: Any) -> bool:
    try:
        with path.open("w", encoding="utf-8") as file:
            json.dump(
                value,
                file,
                ensure_ascii=False,
                indent=2,
            )
        return True
    except OSError as error:
        st.error(f"数据保存失败：{error}")
        return False


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


# ==================================================
# 管理员配置
# ==================================================

def get_admin_credentials() -> tuple[str, str]:
    """
    从 Streamlit Secrets 获取管理员账号和密码。

    如果没有配置 Secrets，则返回空字符串，
    普通用户功能仍然可以正常使用。
    """
    try:
        username = str(
            st.secrets.get("ADMIN_USERNAME", "")
        ).strip()

        password = str(
            st.secrets.get("ADMIN_PASSWORD", "")
        )

        return username, password

    except Exception:
        return "", ""


def admin_is_configured() -> bool:
    username, password = get_admin_credentials()
    return bool(username and password)


def current_user_is_admin() -> bool:
    return (
        st.session_state.get("current_user") is not None
        and st.session_state.get("current_role") == "admin"
    )


# ==================================================
# 普通用户注册与登录
# ==================================================

def load_users() -> dict[str, str]:
    value = load_json(USERS_FILE, {})

    if not isinstance(value, dict):
        return {}

    return {
        str(username): str(password_hash)
        for username, password_hash in value.items()
    }


def hash_password(
    password: str,
    salt: str | None = None,
) -> str:
    salt = salt or secrets.token_hex(16)

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        200_000,
    ).hex()

    return f"{salt}${password_hash}"


def verify_password(
    password: str,
    saved_password: str,
) -> bool:
    try:
        salt, old_hash = saved_password.split("$", 1)
    except ValueError:
        return False

    new_hash = hash_password(
        password,
        salt,
    ).split("$", 1)[1]

    return secrets.compare_digest(
        new_hash,
        old_hash,
    )


def register_user(
    username: str,
    password: str,
) -> tuple[bool, str]:
    username = username.strip()
    users = load_users()

    admin_username, _ = get_admin_credentials()

    if not username or not password:
        return False, "账号和密码不能为空。"

    if len(username) < 2:
        return False, "账号至少需要 2 个字符。"

    if len(password) < 6:
        return False, "密码至少需要 6 个字符。"

    if admin_username and username == admin_username:
        return False, "该账号为管理员专用账号，不能公开注册。"

    if username in users:
        return False, "该账号已经注册。"

    users[username] = hash_password(password)

    if not save_json(USERS_FILE, users):
        return False, "用户数据保存失败。"

    return True, "注册成功，请前往登录。"


def login_user(
    username: str,
    password: str,
) -> tuple[bool, str, str]:
    username = username.strip()

    admin_username, admin_password = get_admin_credentials()

    # 优先检查管理员账号
    if admin_username and username == admin_username:
        if secrets.compare_digest(
            password,
            admin_password,
        ):
            return True, "管理员登录成功。", "admin"

        return False, "管理员密码错误。", ""

    # 普通用户登录
    users = load_users()

    if username not in users:
        return False, "账号不存在。", ""

    if not verify_password(password, users[username]):
        return False, "密码错误。", ""

    return True, "登录成功。", "user"


# ==================================================
# 页面状态
# ==================================================

def go_home() -> None:
    st.session_state.current_page = "home"
    st.session_state.current_book = None
    st.session_state.current_message = None
    st.session_state.pending_delete = None
    st.rerun()


def open_book(isbn: str) -> None:
    st.session_state.current_page = "home"
    st.session_state.current_book = isbn
    st.session_state.current_message = None
    st.session_state.pending_delete = None

    record_book_visit(isbn)
    st.rerun()


# ==================================================
# 热点统计
# ==================================================

def record_book_visit(isbn: str) -> None:
    visits = st.session_state.hot_data.setdefault(
        "book_visits",
        {},
    )

    visits[isbn] = int(visits.get(isbn, 0)) + 1

    today = dt.datetime.now().strftime("%Y-%m-%d")

    daily_stats = st.session_state.hot_data.setdefault(
        "daily_stats",
        {},
    )

    daily_stats.setdefault(today, {})
    daily_stats[today][isbn] = (
        daily_stats[today].get(isbn, 0) + 1
    )

    save_json(
        HOT_DATA_FILE,
        st.session_state.hot_data,
    )


def record_book_search(query: str) -> None:
    query = query.strip()

    if not query:
        return

    searches = st.session_state.hot_data.setdefault(
        "book_searches",
        {},
    )

    searches[query] = int(searches.get(query, 0)) + 1

    save_json(
        HOT_DATA_FILE,
        st.session_state.hot_data,
    )


def record_discussion_topic(
    isbn: str,
    subject: str,
) -> None:
    subject = subject.strip()

    if not subject:
        return

    topic_key = f"{isbn}::{subject}"

    topics = st.session_state.hot_data.setdefault(
        "discussion_topics",
        {},
    )

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

    save_json(
        HOT_DATA_FILE,
        st.session_state.hot_data,
    )


def get_hot_books(limit: int = 6):
    visits = st.session_state.hot_data.get(
        "book_visits",
        {},
    )

    books = [
        (
            isbn,
            info,
            int(visits.get(isbn, 0)),
        )
        for isbn, info in BOOKS_DATABASE.items()
    ]

    books.sort(
        key=lambda item: item[2],
        reverse=True,
    )

    return books[:limit]


def get_hot_discussions(limit: int = 5):
    topics = st.session_state.hot_data.get(
        "discussion_topics",
        {},
    )

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
                    "book_name": (
                        BOOKS_DATABASE[isbn]["name"]
                    ),
                }
            )

    return result[:limit]


def get_trending_searches(limit: int = 8):
    searches = st.session_state.hot_data.get(
        "book_searches",
        {},
    )

    return sorted(
        (
            (str(query), int(count))
            for query, count in searches.items()
        ),
        key=lambda item: item[1],
        reverse=True,
    )[:limit]


# ==================================================
# 搜索与留言数据
# ==================================================

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

        for index, message in enumerate(entries):
            if not isinstance(message, dict):
                continue

            result.append(
                {
                    **message,
                    "isbn": isbn,
                    "message_index": index,
                    "book": (
                        BOOKS_DATABASE
                        .get(isbn, {})
                        .get("name", isbn)
                    ),
                }
            )

    return result


# ==================================================
# 删除权限
# ==================================================

def user_can_delete_message(
    isbn: str,
    message_index: int,
) -> bool:
    """
    服务端再次校验删除权限。

    管理员可以删除全部留言；
    普通用户只能删除 username 与当前账号相同的留言。
    """
    current_user = st.session_state.get("current_user")

    if not current_user:
        return False

    entries = st.session_state.messages.get(isbn, [])

    if (
        not isinstance(entries, list)
        or message_index < 0
        or message_index >= len(entries)
    ):
        return False

    if current_user_is_admin():
        return True

    message = entries[message_index]

    return (
        isinstance(message, dict)
        and message.get("username") == current_user
    )


def delete_message(
    isbn: str,
    message_index: int,
) -> tuple[bool, str]:
    if not user_can_delete_message(
        isbn,
        message_index,
    ):
        return False, "您没有权限删除这条留言。"

    entries = st.session_state.messages[isbn]
    deleted_message = entries.pop(message_index)

    if save_json(
        MESSAGES_FILE,
        st.session_state.messages,
    ):
        st.session_state.pending_delete = None
        return True, "留言已删除。"

    # 文件保存失败时恢复留言
    entries.insert(
        message_index,
        deleted_message,
    )

    return False, "留言删除失败，数据已恢复。"


def render_delete_controls(
    isbn: str,
    message_index: int,
    key_prefix: str,
) -> None:
    """
    显示删除和二次确认按钮。
    """
    if not user_can_delete_message(
        isbn,
        message_index,
    ):
        return

    delete_id = f"{isbn}:{message_index}"

    if st.session_state.pending_delete != delete_id:
        if st.button(
            "删除留言",
            key=f"{key_prefix}_delete",
        ):
            st.session_state.pending_delete = delete_id
            st.rerun()

        return

    st.warning("确定要删除这条留言吗？删除后无法恢复。")

    col1, col2 = st.columns(2)

    with col1:
        if st.button(
            "确认删除",
            key=f"{key_prefix}_confirm",
            type="primary",
            use_container_width=True,
        ):
            success, message = delete_message(
                isbn,
                message_index,
            )

            if success:
                st.success(message)
                st.rerun()
            else:
                st.error(message)

    with col2:
        if st.button(
            "取消",
            key=f"{key_prefix}_cancel",
            use_container_width=True,
        ):
            st.session_state.pending_delete = None
            st.rerun()


# ==================================================
# 搜索结果
# ==================================================

def render_search_results() -> None:
    query = st.session_state.search_query
    results = st.session_state.search_results

    if not query:
        return

    st.subheader(f"检索结果：{query}")

    if not results:
        st.warning("没有找到相关书籍。")
        return

    for isbn, info in results:
        col1, col2 = st.columns([4, 1])

        with col1:
            st.write(
                f"{info['cover_emoji']} "
                f"**{info['name']}**"
            )

            st.write(
                f"作者：{info['author']}　"
                f"主题：{info['theme']}"
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


# ==================================================
# 热点区域
# ==================================================

def render_hot_sections() -> None:
    st.subheader("热点书籍")

    columns = st.columns(3)

    for index, (isbn, info, count) in enumerate(
        get_hot_books()
    ):
        with columns[index % 3]:
            st.write(
                f"{info['cover_emoji']} "
                f"**{info['name']}**"
            )

            st.write(f"作者：{info['author']}")
            st.write(f"主题：{info['theme']}")
            st.caption(f"访问次数：{count}")

            if st.button(
                "查看留言",
                key=f"hot_book_{isbn}",
                use_container_width=True,
            ):
                open_book(isbn)

            st.divider()

    st.subheader("热门讨论")

    discussions = get_hot_discussions()

    if not discussions:
        st.info("暂时还没有热门讨论。")

    for index, topic in enumerate(discussions):
        col1, col2, col3 = st.columns([4, 1, 1])

        with col1:
            st.write(
                f"**{topic['book_name']}**："
                f"{topic['subject']}"
            )

        with col2:
            st.caption(
                f"浏览 {topic.get('views', 0)} 次"
            )

        with col3:
            if st.button(
                "查看",
                key=f"hot_topic_{index}",
                use_container_width=True,
            ):
                open_book(topic["book_isbn"])

    st.divider()
    st.subheader("热门搜索")

    searches = get_trending_searches()

    if not searches:
        st.info("暂时还没有搜索记录。")
        return

    search_columns = st.columns(4)

    for index, (query, count) in enumerate(searches):
        with search_columns[index % 4]:
            if st.button(
                f"{query}（{count}）",
                key=f"trending_{index}_{query}",
                use_container_width=True,
            ):
                st.session_state.search_query = query
                st.session_state.search_results = (
                    search_books(query)
                )
                st.rerun()


# ==================================================
# 留言统计
# ==================================================

def render_message_statistics() -> None:
    messages = get_all_messages()

    st.subheader("留言统计")

    if not messages:
        st.info("暂时没有留言统计数据。")
        return

    book_counts = Counter(
        message["isbn"]
        for message in messages
    )

    col1, col2 = st.columns(2)

    col1.metric("全部留言", len(messages))
    col2.metric("涉及书籍", len(book_counts))

    rows = []

    for isbn, count in book_counts.most_common():
        book = BOOKS_DATABASE.get(isbn, {})

        rows.append(
            {
                "书名": book.get("name", isbn),
                "作者": book.get("author", "未知作者"),
                "ISBN": isbn,
                "留言数量": count,
            }
        )

    st.dataframe(
        rows,
        hide_index=True,
        use_container_width=True,
    )


# ==================================================
# 历史回响
# ==================================================

def render_timeline() -> None:
    messages = get_all_messages()

    messages.sort(
        key=lambda message: message.get("date", ""),
        reverse=True,
    )

    st.subheader("历史回响")

    if not messages:
        st.info("还没有留言。")
        return

    for message in messages[:10]:
        with st.expander(
            f"{message.get('book', '未知书籍')}｜"
            f"{message.get('subject', '未命名主题')}"
        ):
            st.write(
                f"留言者："
                f"{message.get('name', '匿名访客')}"
            )

            st.write(message.get("content", ""))
            st.caption(message.get("date", ""))


# ==================================================
# 我的留言
# ==================================================

def render_my_messages() -> None:
    username = st.session_state.current_user

    if st.button(
        "返回首页",
        key="back_home_from_mine",
        type="primary",
    ):
        go_home()

    st.header(f"{username} 的留言")

    my_messages = []

    for isbn, entries in st.session_state.messages.items():
        if not isinstance(entries, list):
            continue

        for index, message in enumerate(entries):
            if (
                isinstance(message, dict)
                and message.get("username") == username
            ):
                my_messages.append(
                    {
                        "isbn": isbn,
                        "index": index,
                        "message": message,
                    }
                )

    if not my_messages:
        st.info("您还没有发表过留言。")
        return

    st.success(
        f"您一共发表了 {len(my_messages)} 条留言。"
    )

    my_messages.sort(
        key=lambda item: (
            item["message"].get("date", "")
        ),
        reverse=True,
    )

    for item in my_messages:
        isbn = item["isbn"]
        index = item["index"]
        message = item["message"]

        book = BOOKS_DATABASE.get(isbn, {})
        book_name = book.get("name", "未知书籍")

        st.subheader(
            f"{book_name}｜"
            f"{message.get('subject', '未命名主题')}"
        )

        st.write(message.get("content", ""))

        if message.get("location"):
            st.write(
                f"疑问位置：{message['location']}"
            )

        if message.get("notes"):
            st.write(f"备注：{message['notes']}")

        st.caption(
            f"留言时间：{message.get('date', '')}"
        )

        render_delete_controls(
            isbn,
            index,
            f"my_{isbn}_{index}",
        )

        st.divider()


# ==================================================
# 管理全部留言
# ==================================================

def render_admin_messages() -> None:
    if not current_user_is_admin():
        st.error("只有管理员可以访问此页面。")

        if st.button(
            "返回首页",
            key="admin_denied_home",
        ):
            go_home()

        return

    if st.button(
        "返回首页",
        key="back_home_from_admin",
        type="primary",
    ):
        go_home()

    st.header("管理员：全部留言")

    messages = get_all_messages()

    messages.sort(
        key=lambda message: message.get("date", ""),
        reverse=True,
    )

    if not messages:
        st.info("目前没有留言。")
        return

    st.success(f"当前共有 {len(messages)} 条留言。")

    for message in messages:
        isbn = message["isbn"]
        index = message["message_index"]

        st.subheader(
            f"{message.get('book', '未知书籍')}｜"
            f"{message.get('subject', '未命名主题')}"
        )

        st.write(
            f"所属账号："
            f"{message.get('username', '旧留言，无账号记录')}"
        )

        st.write(
            f"显示昵称："
            f"{message.get('name', '匿名访客')}"
        )

        st.write(message.get("content", ""))

        st.caption(
            f"留言时间：{message.get('date', '')}"
        )

        render_delete_controls(
            isbn,
            index,
            f"admin_{isbn}_{index}",
        )

        st.divider()


# ==================================================
# 留言详情
# ==================================================

def render_message_detail(
    isbn: str,
    index: int,
) -> None:
    info = BOOKS_DATABASE[isbn]
    entries = st.session_state.messages.get(isbn, [])

    if index < 0 or index >= len(entries):
        st.session_state.current_message = None
        st.rerun()

    message = entries[index]

    if st.button(
        "返回留言列表",
        key="back_to_message_list",
    ):
        st.session_state.current_message = None
        st.session_state.pending_delete = None
        st.rerun()

    st.header(
        f"{info['cover_emoji']} {info['name']}"
    )

    st.subheader(
        message.get("subject", "未命名主题")
    )

    st.write(
        f"留言者："
        f"{message.get('name', '匿名访客')}"
    )

    st.write(
        f"留言时间："
        f"{message.get('date', '')}"
    )

    st.write(
        f"疑问位置："
        f"{message.get('location') or '未指定'}"
    )

    st.divider()
    st.write(message.get("content", ""))

    if message.get("notes"):
        st.write(f"备注：{message['notes']}")

    st.divider()

    render_delete_controls(
        isbn,
        index,
        f"detail_{isbn}_{index}",
    )


# ==================================================
# 添加留言
# ==================================================

def render_add_message(isbn: str) -> None:
    info = BOOKS_DATABASE[isbn]

    if st.button(
        "取消并返回",
        key="cancel_new_message",
    ):
        st.session_state.current_message = None
        st.rerun()

    st.header(f"给《{info['name']}》添加留言")

    with st.form(f"new_message_form_{isbn}"):
        subject = st.text_input("留言主题 *")

        name = st.text_input(
            "显示昵称",
            placeholder="留空则使用登录账号",
        )

        contact = st.text_input(
            "联系方式（可选）",
        )

        location = st.text_input(
            "疑问位置（可选）",
            placeholder="例如：第120页",
        )

        content = st.text_area(
            "留言内容 *",
            height=150,
        )

        notes = st.text_area(
            "备注（可选）",
            height=80,
        )

        submitted = st.form_submit_button(
            "提交留言",
            type="primary",
        )

    if not submitted:
        return

    if not st.session_state.current_user:
        st.warning("请先登录后再提交留言。")
        return

    if not subject.strip() or not content.strip():
        st.error("请填写留言主题和留言内容。")
        return

    new_message = {
        "username": st.session_state.current_user,
        "subject": subject.strip(),
        "name": (
            name.strip()
            or st.session_state.current_user
        ),
        "contact": contact.strip(),
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

    saved = save_json(
        MESSAGES_FILE,
        st.session_state.messages,
    )

    if not saved:
        st.session_state.messages[isbn].pop()
        return

    record_discussion_topic(
        isbn,
        subject,
    )

    st.success("留言添加成功。")
    st.session_state.current_message = None
    st.rerun()


# ==================================================
# 书籍页面
# ==================================================

def render_book_page(isbn: str) -> None:
    if isbn not in BOOKS_DATABASE:
        st.error("书籍不存在。")

        if st.button("返回首页"):
            go_home()

        return

    info = BOOKS_DATABASE[isbn]
    current_message = st.session_state.current_message

    if current_message == "new":
        render_add_message(isbn)
        return

    if isinstance(current_message, int):
        render_message_detail(
            isbn,
            current_message,
        )
        return

    if st.button(
        "返回首页",
        key=f"back_home_{isbn}",
    ):
        go_home()

    st.header(
        f"{info['cover_emoji']} {info['name']}"
    )

    st.write(f"作者：{info['author']}")
    st.write(f"主题：{info['theme']}")
    st.caption(f"ISBN：{isbn}")

    entries = st.session_state.messages.get(isbn, [])

    st.subheader(
        f"留言列表（共 {len(entries)} 条）"
    )

    if not entries:
        st.info("暂时没有留言。")

    for index, message in enumerate(entries):
        col1, col2 = st.columns([4, 1])

        with col1:
            st.write(
                f"**{message.get('subject', '未命名主题')}**"
            )

            st.caption(
                f"{message.get('name', '匿名访客')}｜"
                f"{message.get('date', '')}"
            )

        with col2:
            if st.button(
                "查看",
                key=f"message_{isbn}_{index}",
                use_container_width=True,
            ):
                st.session_state.current_message = index
                st.session_state.pending_delete = None

                record_discussion_topic(
                    isbn,
                    str(message.get("subject", "")),
                )

                st.rerun()

        st.divider()

    if st.button(
        "添加新留言",
        type="primary",
        key=f"add_message_{isbn}",
    ):
        if not st.session_state.current_user:
            st.warning("请先登录后再添加留言。")
        else:
            st.session_state.current_message = "new"
            st.rerun()


# ==================================================
# 初始化 Session State
# ==================================================

defaults = {
    "messages": load_messages(),
    "hot_data": load_hot_data(),
    "current_book": None,
    "current_message": None,
    "current_page": "home",
    "search_query": "",
    "search_results": [],
    "current_user": None,
    "current_role": None,
    "pending_delete": None,
}

for key, default in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ==================================================
# 侧边栏
# ==================================================

with st.sidebar:
    st.header("用户中心")

    if st.session_state.current_user:
        st.success(
            f"已登录：{st.session_state.current_user}"
        )

        if current_user_is_admin():
            st.info("当前身份：管理员")

            if st.button(
                "管理全部留言",
                key="open_admin_messages",
                use_container_width=True,
            ):
                st.session_state.current_page = "admin"
                st.session_state.current_book = None
                st.session_state.current_message = None
                st.session_state.pending_delete = None
                st.rerun()

        else:
            st.caption("当前身份：普通用户")

        if st.button(
            "我的留言",
            key="open_my_messages",
            use_container_width=True,
        ):
            st.session_state.current_page = "mine"
            st.session_state.current_book = None
            st.session_state.current_message = None
            st.session_state.pending_delete = None
            st.rerun()

        if st.button(
            "返回首页",
            key="sidebar_home",
            use_container_width=True,
        ):
            go_home()

        if st.button(
            "退出登录",
            key="logout",
            use_container_width=True,
        ):
            st.session_state.current_user = None
            st.session_state.current_role = None
            st.session_state.current_page = "home"
            st.session_state.current_book = None
            st.session_state.current_message = None
            st.session_state.pending_delete = None
            st.rerun()

    else:
        login_tab, register_tab = st.tabs(
            ["登录", "注册"]
        )

        with login_tab:
            with st.form("login_form"):
                login_name = st.text_input("账号")

                login_password = st.text_input(
                    "密码",
                    type="password",
                )

                login_submitted = (
                    st.form_submit_button(
                        "登录",
                        use_container_width=True,
                    )
                )

            if login_submitted:
                success, message, role = login_user(
                    login_name,
                    login_password,
                )

                if success:
                    st.session_state.current_user = (
                        login_name.strip()
                    )

                    st.session_state.current_role = role
                    st.session_state.current_page = "home"

                    st.success(message)
                    st.rerun()

                else:
                    st.error(message)

        with register_tab:
            with st.form("register_form"):
                register_name = st.text_input(
                    "新账号",
                )

                register_password = st.text_input(
                    "新密码",
                    type="password",
                )

                register_password_again = st.text_input(
                    "再次输入密码",
                    type="password",
                )

                register_submitted = (
                    st.form_submit_button(
                        "注册",
                        use_container_width=True,
                    )
                )

            if register_submitted:
                if (
                    register_password
                    != register_password_again
                ):
                    st.error("两次输入的密码不一致。")

                else:
                    success, message = register_user(
                        register_name,
                        register_password,
                    )

                    if success:
                        st.success(message)
                    else:
                        st.error(message)

        if not admin_is_configured():
            st.warning(
                "管理员账号尚未配置，"
                "请在 Streamlit Secrets 中设置。"
            )

    st.divider()
    st.header("书籍检索")

    with st.form("search_form"):
        query = st.text_input(
            "书名、作者或 ISBN",
        )

        search_submitted = st.form_submit_button(
            "检索",
            use_container_width=True,
        )

    if search_submitted:
        st.session_state.search_query = query.strip()
        st.session_state.search_results = (
            search_books(query)
        )

        st.session_state.current_page = "home"
        st.session_state.current_book = None
        st.session_state.current_message = None
        st.session_state.pending_delete = None

        record_book_search(query)

    uploaded_file = st.file_uploader(
        "上传旧照片",
        type=["jpg", "jpeg", "png"],
    )

    if uploaded_file is not None:
        st.image(
            uploaded_file,
            caption="照片预览",
            use_container_width=True,
        )


# ==================================================
# 主页面
# ==================================================

st.title("图书馆跨时空留言板")

if st.session_state.current_page == "admin":
    render_admin_messages()

elif st.session_state.current_page == "mine":
    render_my_messages()

elif st.session_state.current_book:
    render_book_page(
        st.session_state.current_book
    )

else:
    st.write(
        "搜索书籍、查看历史留言，"
        "或登录后发表自己的留言。"
    )

    render_search_results()

    if not st.session_state.search_query:
        st.info(
            "请在左侧输入书名、作者或 ISBN。"
        )

    render_hot_sections()

    st.divider()
    render_message_statistics()

    st.divider()
    render_timeline()