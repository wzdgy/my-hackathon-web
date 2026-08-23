from __future__ import annotations

import copy
import datetime as dt
import html
import json
from collections import Counter
from pathlib import Path
from typing import Any

import streamlit as st


# =========================
# 页面与数据配置
# =========================
st.set_page_config(
    page_title="图书馆跨时空留言板",
    page_icon="📜",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE_DIR = Path(__file__).resolve().parent
MESSAGES_FILE = BASE_DIR / "messages_data.json"
HOT_DATA_FILE = BASE_DIR / "hot_data.json"

BOOKS_DATABASE: dict[str, dict[str, str]] = {
    "9787544291163": {"name": "百年孤独", "author": "加西亚·马尔克斯", "theme": "魔幻现实主义", "cover_emoji": "📚"},
    "9787020002207": {"name": "红楼梦", "author": "曹雪芹", "theme": "古典文学", "cover_emoji": "🏮"},
    "9787544253994": {"name": "三体", "author": "刘慈欣", "theme": "科幻", "cover_emoji": "🌌"},
    "9787532769278": {"name": "活着", "author": "余华", "theme": "现实主义", "cover_emoji": "🕯️"},
    "9787540480590": {"name": "围城", "author": "钱钟书", "theme": "讽刺文学", "cover_emoji": "🏛️"},
    "9787020024759": {"name": "平凡的世界", "author": "路遥", "theme": "现实主义", "cover_emoji": "🌾"},
}

DEFAULT_MESSAGES: dict[str, list[dict[str, Any]]] = {
    "9787544291163": [
        {"subject": "枫叶还在吗？", "name": "来自1998年的读者", "contact": "", "location": "第120页", "content": "我在《百年孤独》的第120页夹了一片枫叶，不知道现在的它还在吗？", "notes": "这是一封来自过去的留言。", "date": "1998-05-12 14:30:00"},
        {"subject": "给未来的读者", "name": "图书管理员 AI", "contact": "", "location": "馆员工作台", "content": "那片枫叶已经化作书签永存了。欢迎来到跨时空留言板。", "notes": "", "date": "2026-08-22 09:00:00"},
    ],
    "9787544253994": [
        {"subject": "如果三体人真的到来", "name": "仰望星空", "contact": "", "location": "序章旁白", "content": "我们该如何判断，沉默究竟是善意还是危险？", "notes": "欢迎留下你的答案。", "date": "2026-08-20 18:20:00"}
    ],
}

DEFAULT_HOT_DATA: dict[str, Any] = {
    "book_visits": {"9787544291163": 18, "9787544253994": 15, "9787020002207": 10, "9787532769278": 8},
    "book_searches": {"百年孤独": 12, "三体": 9, "红楼梦": 7},
    "discussion_topics": {
        "9787544291163::枫叶还在吗？": {"book_isbn": "9787544291163", "subject": "枫叶还在吗？", "views": 11, "replies": 2},
        "9787544253994::如果三体人真的到来": {"book_isbn": "9787544253994", "subject": "如果三体人真的到来", "views": 8, "replies": 1},
    },
    "daily_stats": {},
}


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
    return {str(isbn): entries for isbn, entries in value.items() if isinstance(entries, list)}


def load_hot_data() -> dict[str, Any]:
    value = load_json(HOT_DATA_FILE, DEFAULT_HOT_DATA)
    if not isinstance(value, dict):
        return copy.deepcopy(DEFAULT_HOT_DATA)
    data = copy.deepcopy(DEFAULT_HOT_DATA)
    for key in data:
        if isinstance(value.get(key), dict):
            data[key].update(value[key])
    return data


def record_book_visit(isbn: str) -> None:
    visits = st.session_state.hot_data.setdefault("book_visits", {})
    visits[isbn] = int(visits.get(isbn, 0)) + 1
    today = dt.datetime.now().strftime("%Y-%m-%d")
    daily = st.session_state.hot_data.setdefault("daily_stats", {})
    daily.setdefault(today, {})[isbn] = daily.setdefault(today, {}).get(isbn, 0) + 1
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
    key = f"{isbn}::{subject}"
    topics = st.session_state.hot_data.setdefault("discussion_topics", {})
    topic = topics.setdefault(key, {"book_isbn": isbn, "subject": subject, "views": 0, "replies": 0})
    topic["views"] = int(topic.get("views", 0)) + 1
    save_json(HOT_DATA_FILE, st.session_state.hot_data)


def search_books(query: str) -> list[tuple[str, dict[str, str]]]:
    normalized = query.strip().lower()
    if not normalized:
        return []
    return [(isbn, info) for isbn, info in BOOKS_DATABASE.items() if normalized in isbn or normalized in info["name"].lower() or normalized in info["author"].lower() or normalized in info["theme"].lower()]


def get_all_messages() -> list[dict[str, Any]]:
    """将按 ISBN 分组的留言展开为统一列表。"""
    all_messages: list[dict[str, Any]] = []
    grouped_messages = st.session_state.get("messages", {})

    if not isinstance(grouped_messages, dict):
        return all_messages

    for isbn, message_list in grouped_messages.items():
        if not isinstance(message_list, list):
            continue

        book_name = BOOKS_DATABASE.get(isbn, {}).get("name", isbn)
        for message in message_list:
            if isinstance(message, dict):
                all_messages.append({
                    **message,
                    "isbn": isbn,
                    "book": book_name,
                })

    return all_messages


def hot_books(limit: int = 6) -> list[tuple[str, dict[str, str], int]]:
    visits = st.session_state.hot_data.get("book_visits", {})
    ranked = [(isbn, info, int(visits.get(isbn, 0))) for isbn, info in BOOKS_DATABASE.items()]
    ranked.sort(key=lambda item: item[2], reverse=True)
    return ranked[:limit]


def hot_discussions(limit: int = 5) -> list[dict[str, Any]]:
    topics = st.session_state.hot_data.get("discussion_topics", {})
    ranked = sorted(topics.values(), key=lambda topic: int(topic.get("views", 0)), reverse=True)
    return [{**topic, "book_name": BOOKS_DATABASE[topic["book_isbn"]]["name"]} for topic in ranked if topic.get("book_isbn") in BOOKS_DATABASE][:limit]


def trending_searches(limit: int = 8) -> list[tuple[str, int]]:
    searches = st.session_state.hot_data.get("book_searches", {})
    return sorted(((str(query), int(count)) for query, count in searches.items()), key=lambda item: item[1], reverse=True)[:limit]


def open_book(isbn: str) -> None:
    st.session_state.current_book = isbn
    st.session_state.current_message = None
    record_book_visit(isbn)
    st.rerun()


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
            st.markdown(f"**{info['cover_emoji']} {html.escape(info['name'])}**　作者：{html.escape(info['author'])}　主题：{html.escape(info['theme'])}")
            st.caption(f"ISBN：{isbn}")
        with col2:
            if st.button("进入书页", key=f"search_book_{isbn}", use_container_width=True):
                open_book(isbn)
        st.divider()


def render_hot_sections() -> None:
    st.subheader("🔥 热点书籍")
    cols = st.columns(3)
    for index, (isbn, info, count) in enumerate(hot_books()):
        with cols[index % 3]:
            st.markdown(f"<div class='book-card'><div class='book-title'>{info['cover_emoji']} {html.escape(info['name'])}</div><div>作者：{html.escape(info['author'])}</div><div>主题：{html.escape(info['theme'])}</div><div class='hot-count'>🔥 访问 {count} 次</div></div>", unsafe_allow_html=True)
            if st.button("查看留言", key=f"hot_book_{isbn}", use_container_width=True):
                open_book(isbn)

    st.subheader("💬 热门讨论")
    discussions = hot_discussions()
    if not discussions:
        st.info("暂时还没有热门讨论，欢迎发表第一条留言。")
    for index, topic in enumerate(discussions):
        col1, col2, col3 = st.columns([4, 1, 1])
        with col1:
            st.markdown(f"**📖 {html.escape(topic['book_name'])}**　{html.escape(topic['subject'])}")
        with col2:
            st.caption(f"👁 {topic.get('views', 0)} 次")
        with col3:
            if st.button("查看", key=f"hot_topic_{index}", use_container_width=True):
                open_book(topic["book_isbn"])

    st.subheader("📈 热门搜索")
    searches = trending_searches()
    if not searches:
        st.info("暂时还没有搜索记录。")
    search_cols = st.columns(4)
    for index, (query, count) in enumerate(searches):
        with search_cols[index % 4]:
            if st.button(f"🔍 {query}（{count}）", key=f"trending_{index}_{query}", use_container_width=True):
                st.session_state.search_query = query
                st.session_state.search_results = search_books(query)
                st.rerun()


def render_timeline() -> None:
    messages = [(message["isbn"], message) for message in get_all_messages()]
    messages.sort(key=lambda item: item[1].get("date", ""), reverse=True)
    st.subheader("⏳ 历史回响")
    if not messages:
        st.info("还没有留言。")
        return
    for isbn, message in messages[:10]:
        user = html.escape(str(message.get("name", "匿名访客")))
        content = html.escape(str(message.get("content", "")))
        subject = html.escape(str(message.get("subject", "未命名主题")))
        date = html.escape(str(message.get("date", "")))
        book_name = html.escape(BOOKS_DATABASE.get(isbn, {}).get("name", isbn))
        st.markdown(f"<div class='message-card'><div class='message-meta'><strong>@{user}</strong><span>{date}</span></div><div class='message-book'>📖 {book_name} · {subject}</div><div class='ink-text'>“{content}”</div></div>", unsafe_allow_html=True)


def render_message_statistics() -> None:
    """显示所有留言数量及每本书的留言统计。"""
    all_messages = get_all_messages()
    st.subheader("📊 留言统计")

    if not all_messages:
        st.info("暂时没有留言统计数据。")
        return

    book_counts = Counter(message["isbn"] for message in all_messages)
    statistics = []
    for isbn, count in book_counts.most_common():
        book_info = BOOKS_DATABASE.get(isbn, {})
        statistics.append({
            "书名": book_info.get("name", isbn),
            "作者": book_info.get("author", "未知作者"),
            "ISBN": isbn,
            "留言数量": count,
        })

    col1, col2 = st.columns(2)
    with col1:
        st.metric("全部留言", len(all_messages))
    with col2:
        st.metric("涉及书籍", len(book_counts))

    st.dataframe(statistics, hide_index=True, use_container_width=True)


def render_message_detail(isbn: str, index: int) -> None:
    info = BOOKS_DATABASE[isbn]
    entries = st.session_state.messages.get(isbn, [])
    if index < 0 or index >= len(entries):
        st.session_state.current_message = None
        st.rerun()
    message = entries[index]
    st.header(f"{info['cover_emoji']} {info['name']}")
    st.subheader(f"留言主题：{message.get('subject', '未命名主题')}")
    st.write(f"**留言者：** {message.get('name', '匿名访客')}")
    st.write(f"**留言时间：** {message.get('date', '')}")
    st.write(f"**疑问位置：** {message.get('location') or '未指定'}")
    st.divider()
    st.write(message.get("content", ""))
    if message.get("notes"):
        st.caption(f"备注：{message['notes']}")
    if st.button("↩ 返回留言列表", key="back_to_messages"):
        st.session_state.current_message = None
        st.rerun()


def render_add_message(isbn: str) -> None:
    info = BOOKS_DATABASE[isbn]
    st.header(f"✒️ 给《{info['name']}》添加留言")
    with st.form(f"new_message_form_{isbn}"):
        subject = st.text_input("留言主题 *", placeholder="例如：枫叶还在吗？")
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("昵称", placeholder="留空则使用匿名访客")
        with col2:
            location = st.text_input("疑问位置", placeholder="例如：第120页")
        content = st.text_area("留言内容 *", height=150)
        notes = st.text_area("备注（可选）", height=90)
        submitted = st.form_submit_button("提交留言", type="primary")
    if submitted:
        if not subject.strip() or not content.strip():
            st.error("请填写留言主题和留言内容。")
            return
        new_message = {"subject": subject.strip(), "name": name.strip() or "匿名访客", "contact": "", "location": location.strip(), "content": content.strip(), "notes": notes.strip(), "date": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        st.session_state.messages.setdefault(isbn, []).append(new_message)
        save_json(MESSAGES_FILE, st.session_state.messages)
        record_discussion_topic(isbn, subject)
        st.success("留言添加成功！")
        st.session_state.current_message = None
        st.rerun()
    if st.button("取消", key="cancel_new_message"):
        st.session_state.current_message = None
        st.rerun()


def render_book_page(isbn: str) -> None:
    info = BOOKS_DATABASE[isbn]
    current_message = st.session_state.current_message
    if current_message == "new":
        render_add_message(isbn)
        return
    if isinstance(current_message, int):
        render_message_detail(isbn, current_message)
        return
    st.header(f"{info['cover_emoji']} {info['name']}")
    st.caption(f"作者：{info['author']}　|　主题：{info['theme']}　|　ISBN：{isbn}")
    entries = st.session_state.messages.get(isbn, [])
    st.subheader(f"💬 留言列表（共 {len(entries)} 条）")
    if not entries:
        st.info("暂时没有留言，成为第一个留言的人吧！")
    for index, message in enumerate(entries):
        col1, col2, col3 = st.columns([4, 1, 1])
        with col1:
            st.markdown(f"**📜 {html.escape(str(message.get('subject', '未命名主题')))}**")
        with col2:
            st.caption(f"👤 {html.escape(str(message.get('name', '匿名访客')))}")
        with col3:
            if st.button("查看", key=f"message_{isbn}_{index}", use_container_width=True):
                st.session_state.current_message = index
                record_discussion_topic(isbn, str(message.get("subject", "")))
                st.rerun()
        st.divider()
    if st.button("✒️ 添加新留言", type="primary", key=f"add_message_{isbn}"):
        st.session_state.current_message = "new"
        st.rerun()
    if st.button("↩ 返回首页", key=f"back_home_{isbn}"):
        st.session_state.current_book = None
        st.session_state.current_message = None
        st.rerun()


st.markdown(
    """
    <style>
    .stApp { background-color:#f4ecd8; background-image:url("https://www.transparenttextures.com/patterns/aged-paper.png"); color:#5c4033; font-family:Georgia,"Times New Roman",serif; }
    section[data-testid="stSidebar"] { background:#eaddcf; border-right:2px solid #8b5a2b; }
    h1,h2,h3 { color:#8b4513; text-shadow:1px 1px 2px rgba(0,0,0,.1); }
    .message-card,.book-card { background:rgba(255,250,240,.92); border:1px solid #d2b48c; border-left:5px solid #8b4513; border-radius:6px; padding:15px; margin-bottom:14px; box-shadow:2px 2px 5px rgba(139,69,19,.12); }
    .book-title { color:#8b4513; font-size:1.15rem; font-weight:700; margin-bottom:8px; }
    .hot-count { color:#a0522d; margin-top:8px; }
    .message-meta { display:flex; justify-content:space-between; color:#8b4513; margin-bottom:6px; }
    .message-meta span { color:#a0522d; font-size:.8rem; }
    .message-book { color:#a0522d; margin-bottom:6px; }
    .ink-text { color:#2f4f4f; font-style:italic; white-space:pre-wrap; overflow-wrap:anywhere; }
    div.stButton > button { background:#8b4513 !important; color:#fff !important; border:1px solid #5c4033; border-radius:5px; }
    </style>
    """,
    unsafe_allow_html=True,
)

for key, default in {"messages": load_messages(), "hot_data": load_hot_data(), "current_book": None, "current_message": None, "search_query": "", "search_results": []}.items():
    if key not in st.session_state:
        st.session_state[key] = default

with st.sidebar:
    st.header("🔍 检索与上传")
    with st.form("sidebar_search_form"):
        query = st.text_input("书名、作者或 ISBN", placeholder="例如：百年孤独 / 余华 / ISBN")
        search_submitted = st.form_submit_button("检索书籍", use_container_width=True)
    if search_submitted:
        st.session_state.search_query = query.strip()
        st.session_state.search_results = search_books(query)
        record_book_search(query)
    uploaded_file = st.file_uploader("📷 上传旧照片", type=["jpg", "jpeg", "png"])
    if uploaded_file is not None:
        st.image(uploaded_file, caption="已加载的历史影像", use_container_width=True)
    st.divider()
    st.caption("© 2026 图书馆黑客松项目组")

st.title("📜 图书馆跨时空留言板")
st.markdown("在这里留下你的疑问，或者回应百年前读者的低语……")

if st.session_state.current_book:
    render_book_page(st.session_state.current_book)
else:
    render_search_results()
    if not st.session_state.search_query:
        st.info("请在左侧输入书名、作者或 ISBN，开始探索书籍与历史留言。")
    render_hot_sections()
    render_message_statistics()
    render_timeline()