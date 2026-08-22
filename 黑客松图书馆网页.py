import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import json
import os
from collections import Counter

# --- 1. 页面基础配置 ---
st.set_page_config(
    page_title="图书馆跨时空留言板",
    page_icon="📚",
    layout="wide"
)

# --- 2. CSS 样式定制 (羊皮纸复古风) ---
st.markdown("""
<style>
    /* 全局背景与字体 */
    .main {
        background-color: #f4ecd8; /* 羊皮纸底色 */
        background-image: url('https://www.transparenttextures.com/patterns/aged-paper.png'); /* 纸张纹理 */
        color: #5c4033; /* 深褐色文字 */
        font-family: 'Georgia', 'Times New Roman', serif; /* 衬线字体 */
    }

    /* 侧边栏样式 */
    section[data-testid="stSidebar"] {
        background-color: #eaddcf;
        border-right: 2px solid #8b5a2b;
    }
    
    /* 修复侧边栏文字颜色 */
    section[data-testid="stSidebar"] * {
        color: #5c4033 !important;
    }

    /* 标题样式 */
    h1, h2, h3 {
        color: #8b4513; /* 马鞍棕 */
        font-weight: bold;
        text-shadow: 1px 1px 2px rgba(0,0,0,0.1);
    }

    /* 留言卡片样式 (时间轴节点) */
    .message-card {
        background-color: #fffaf0;
        border: 1px solid #d2b48c;
        border-left: 5px solid #8b4513;
        padding: 15px;
        margin-bottom: 20px;
        border-radius: 4px;
        box-shadow: 2px 2px 5px rgba(139, 69, 19, 0.1);
        position: relative;
    }

    /* 模拟墨迹效果 */
    .ink-text {
        color: #2f4f4f;
        font-style: italic;
    }

    /* 按钮复古化 */
    div.stButton > button {
        background-color: #8b4513 !important;
        color: #fff !important;
        border-radius: 5px;
        border: 1px solid #5c4033;
    }
</style>
""", unsafe_allow_html=True)

# --- 3. 数据存储与初始化 ---
DATA_FILE = "messages_data.json"
HOT_DATA_FILE = "hot_data.json"

def load_messages():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_messages(messages):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)

def load_hot_data():
    """加载热点数据"""
    if os.path.exists(HOT_DATA_FILE):
        with open(HOT_DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "book_visits": {},
        "book_searches": {},
        "discussion_topics": {},
        "daily_stats": {}
    }

def save_hot_data(hot_data):
    """保存热点数据"""
    with open(HOT_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(hot_data, f, ensure_ascii=False, indent=2)

if 'messages' not in st.session_state:
    st.session_state.messages = load_messages()
if 'hot_data' not in st.session_state:
    st.session_state.hot_data = load_hot_data()
if 'current_book' not in st.session_state:
    st.session_state.current_book = None
if 'current_message' not in st.session_state:
    st.session_state.current_message = None

# --- 4. 书籍数据库 ---
BOOKS_DATABASE = {
    "9787544291163": {"name": "百年孤独", "author": "加西亚·马尔克斯", "theme": "魔幻现实主义", "cover_emoji": "🌴"},
    "9787020002207": {"name": "红楼梦", "author": "曹雪芹", "theme": "古典文学", "cover_emoji": "🏮"},
    "9787544253994": {"name": "三体", "author": "刘慈欣", "theme": "科幻", "cover_emoji": "🌌"},
    "9787532769278": {"name": "活着", "author": "余华", "theme": "现实主义", "cover_emoji": "🌾"},
    "9787540480590": {"name": "围城", "author": "钱钟书", "theme": "讽刺文学", "cover_emoji": "🏰"},
    "9787020024759": {"name": "平凡的世界", "author": "路遥", "theme": "现实主义", "cover_emoji": "⛰️"}
}

# --- 5. 功能函数 ---
def record_book_visit(book_isbn):
    """记录书籍访问"""
    today = datetime.now().strftime("%Y-%m-%d")
    if book_isbn not in st.session_state.hot_data["book_visits"]:
        st.session_state.hot_data["book_visits"][book_isbn] = 0
    st.session_state.hot_data["book_visits"][book_isbn] += 1

    if today not in st.session_state.hot_data["daily_stats"]:
        st.session_state.hot_data["daily_stats"][today] = {}
    if book_isbn not in st.session_state.hot_data["daily_stats"][today]:
        st.session_state.hot_data["daily_stats"][today][book_isbn] = 0
    st.session_state.hot_data["daily_stats"][today][book_isbn] += 1
    save_hot_data(st.session_state.hot_data)

def record_book_search(query):
    """记录书籍搜索"""
    if query not in st.session_state.hot_data["book_searches"]:
        st.session_state.hot_data["book_searches"][query] = 0
    st.session_state.hot_data["book_searches"][query] += 1
    save_hot_data(st.session_state.hot_data)

def record_discussion_topic(book_isbn, subject):
    """记录讨论话题"""
    topic_key = f"{book_isbn}::{subject}"
    if topic_key not in st.session_state.hot_data["discussion_topics"]:
        st.session_state.hot_data["discussion_topics"][topic_key] = {
            "book_isbn": book_isbn,
            "subject": subject,
            "views": 0,
            "replies": 0
        }
    st.session_state.hot_data["discussion_topics"][topic_key]["views"] += 1
    save_hot_data(st.session_state.hot_data)

def get_hot_books(limit=5):
    """获取热门书籍"""
    visits = st.session_state.hot_data["book_visits"]
    sorted_books = sorted(visits.items(), key=lambda x: x[1], reverse=True)
    hot_books = []
    for isbn, count in sorted_books[:limit]:
        if isbn in BOOKS_DATABASE:
            book_info = BOOKS_DATABASE[isbn].copy()
            book_info["isbn"] = isbn
            book_info["visit_count"] = count
            hot_books.append(book_info)
    return hot_books

def get_hot_discussions(limit=5):
    """获取热门讨论话题"""
    topics = st.session_state.hot_data["discussion_topics"]
    sorted_topics = sorted(topics.items(), key=lambda x: x[1]["views"], reverse=True)
    hot_discussions = []
    for key, topic_info in sorted_topics[:limit]:
        book_isbn = topic_info["book_isbn"]
        if book_isbn in BOOKS_DATABASE:
            book_name = BOOKS_DATABASE[book_isbn]["name"]
            hot_discussions.append({
                "book_name": book_name,
                "book_isbn": book_isbn,
                "subject": topic_info["subject"],
                "views": topic_info["views"]
            })
    return hot_discussions

def get_trending_searches(limit=5):
    """获取热门搜索词"""
    searches = st.session_state.hot_data["book_searches"]
    sorted_searches = sorted(searches.items(), key=lambda x: x[1], reverse=True)
    return sorted_searches[:limit]

def search_book(query):
    """搜索书籍"""
    results = []
    query = query.strip().lower()
    for isbn, info in BOOKS_DATABASE.items():
        if query in isbn or query in info['name'].lower() or query in info['author'].lower():
            results.append((isbn, info))
    return results

def display_hot_books_section():
    """显示热门书籍区域"""
    st.markdown("---")
    st.subheader("🔥 热门书籍")
    hot_books = get_hot_books(6)
    if hot_books:
        cols = st.columns(3)
        for idx, book in enumerate(hot_books):
            with cols[idx % 3]:
                with st.container():
                    st.markdown(f"""
                    <div style="padding: 15px; border: 1px solid #d2b48c; border-radius: 10px; margin-bottom: 10px; background-color: #fffaf0;">
                        <h3 style="margin: 0; color: #8b4513;">{book['cover_emoji']} {book['name']}</h3>
                        <p style="margin: 5px 0; color: #5c4033;">作者：{book['author']}</p>
                        <p style="margin: 5px 0; color: #8b5a2b;">主题：{book['theme']}</p>
                        <p style="margin: 5px 0; color: #8b4513;">🔥 访问 {book['visit_count']} 次</p>
                    </div>
                    """, unsafe_allow_html=True)
                    if st.button(f"查看留言", key=f"hot_book_{book['isbn']}"):
                        st.session_state.current_book = (book['isbn'], BOOKS_DATABASE[book['isbn']])
                        st.session_state.current_message = None
                        record_book_visit(book['isbn'])
                        st.rerun()
    else:
        st.info("暂无热门书籍数据，快去探索书籍吧！")

def display_hot_discussions_section():
    """显示热门讨论区域"""
    st.markdown("---")
    st.subheader("💬 热门讨论话题")
    hot_discussions = get_hot_discussions(5)
    if hot_discussions:
        for discussion in hot_discussions:
            with st.container():
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.write(f"📖 **{discussion['book_name']}** - {discussion['subject']}")
                with col2:
                    st.write(f"👁️ {discussion['views']} 次浏览")
                with col3:
                    if st.button("查看", key=f"hot_disc_{discussion['book_isbn']}_{discussion['subject']}"):
                        st.session_state.current_book = (discussion['book_isbn'], BOOKS_DATABASE[discussion['book_isbn']])
                        st.session_state.current_message = None
                        record_book_visit(discussion['book_isbn'])
                        st.rerun()
                st.divider()
    else:
        st.info("暂无热门讨论话题")

def display_trending_searches_section():
    """显示热门搜索词"""
    st.markdown("---")
    st.subheader("🔍 热门搜索")
    trending = get_trending_searches(8)
    if trending:
        cols = st.columns(4)
        for idx, (query, count) in enumerate(trending):
            with cols[idx % 4]:
                if st.button(f"🔍 {query} ({count})", key=f"trend_{query}"):
                    results = search_book(query)
                    if results:
                        for isbn, info in results:
                            st.session_state.current_book = (isbn, info)
                            st.session_state.current_message = None
                            record_book_visit(isbn)
                            st.rerun()
    else:
        st.info("暂无搜索数据")

def display_book_messages(book_isbn, book_info):
    """显示书籍的留言列表"""
    st.header(f"📖 {book_info['name']}")
    st.subheader(f"作者：{book_info['author']} | 主题：{book_info['theme']}")

    book_messages = st.session_state.messages.get(book_isbn, [])
    if not book_messages:
        st.info("暂无留言，成为第一个留言的人吧！")
    else:
        st.subheader(f"💬 留言列表（共{len(book_messages)}条）")
        for idx, msg in enumerate(book_messages):
            with st.container():
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    if st.button(f"📝 {msg['subject']}", key=f"msg_{book_isbn}_{idx}"):
                        st.session_state.current_message = msg
                        record_discussion_topic(book_isbn, msg['subject'])
                        st.rerun()
                with col2:
                    st.text(f"👤 {msg['name']}")
                with col3:
                    st.text(f"📅 {msg['date'][:10]}")
                st.divider()
        if st.button("✏️ 添加新留言", type="primary"):
            st.session_state.current_message = "new"
            st.rerun()

def display_message_detail(book_isbn, book_info, message):
    """显示留言详情"""
    st.header(f"📖 {book_info['name']}")
    st.subheader(f"留言主题：{message['subject']}")
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**留言者：** {message['name']}")
        st.write(f"**联系方式：** {message.get('contact', '未填写')}")
    with col2:
        st.write(f"**留言时间：** {message['date']}")
        st.write(f"**疑问位置：** {message.get('location', '未指定')}")
    st.divider()
    st.write("**疑问内容：**")
    st.write(message['content'])
    if message.get('notes'):
        st.write("**备注：**")
        st.write(message['notes'])
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔙 返回留言列表"):
            st.session_state.current_message = None
            st.rerun()
    with col2:
        if st.button("📚 返回首页"):
            st.session_state.current_book = None
            st.session_state.current_message = None
            st.rerun()

def add_new_message(book_isbn, book_info):
    """添加新留言"""
    st.header(f"✏️ 为《{book_info['name']}》添加留言")
    with st.form("new_message_form"):
        subject = st.text_input("留言主题（简略介绍）*", placeholder="请输入留言主题")
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("姓名（可选匿名）", placeholder="输入姓名或留空匿名")
        with col2:
            contact = st.text_input("联系方式（可不填）", placeholder="邮箱/电话等")
        location = st.text_input("疑问存在位置（如页数）", placeholder="例如：第120页")
        content = st.text_area("疑问具体内容*", placeholder="请详细描述您的疑问...", height=150)
        notes = st.text_area("备注（可不填）", placeholder="其他补充信息...", height=100)
        submitted = st.form_submit_button("提交留言", type="primary")
        if submitted:
            if not subject or not content:
                st.error("请填写留言主题和疑问内容！")
                return
            new_message = {
                "subject": subject,
                "name": name if name else "匿名用户",
                "contact": contact,
                "location": location,
                "content": content,
                "notes": notes,
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            if book_isbn not in st.session_state.messages:
                st.session_state.messages[book_isbn] = []
            st.session_state.messages[book_isbn].append(new_message)
            save_messages(st.session_state.messages)
            record_discussion_topic(book_isbn, subject)
            st.success("留言添加成功！")
            st.session_state.current_message = None
            st.rerun()
    if st.button("取消"):
        st.session_state.current_message = None
        st.rerun()

def main():
    """主页面"""
    st.title("📚 图书馆跨时空留言板")
    st.markdown("---")
    
    # 搜索区域
    with st.container():
        st.subheader("🔍 搜索书籍")
        col1, col2 = st.columns([3, 1])
        with col1:
            search_query = st.text_input("输入书籍名称、作者或ISBN", placeholder="例如：百年孤独、刘慈欣 或 9787544291163", label_visibility="collapsed")
        with col2:
            search_button = st.button("搜索", type="primary", use_container_width=True)
        
        if search_button and search_query:
            results = search_book(search_query)
            if results:
                st.success(f"找到 {len(results)} 本书")
                record_book_search(search_query)
                for isbn, info in results:
                    if st.button(f"📖 {info['name']} - {info['author']}", key=f"book_{isbn}"):
                        st.session_state.current_book = (isbn, info)
                        st.session_state.current_message = None
                        record_book_visit(isbn)
                        st.rerun()
            else:
                st.error("未找到相关书籍，请检查输入")

    # 显示当前页面
    if st.session_state.current_message == "new" and st.session_state.current_book:
        book_isbn, book_info = st.session_state.current_book
        add_new_message(book_isbn, book_info)
    elif st.session_state.current_message and st.session_state.current_book:
        book_isbn, book_info = st.session_state.current_book
        display_message_detail(book_isbn, book_info, st.session_state.current_message)
    elif st.session_state.current_book:
        book_isbn, book_info = st.session_state.current_book
        display_book_messages(book_isbn, book_info)
    else:
        st.info("👆 请在上方搜索框输入书籍名称、作者或ISBN开始探索")
        display_hot_books_section()
        display_hot_discussions_section()
        display_trending_searches_section()

if __name__ == "__main__":
    main()
