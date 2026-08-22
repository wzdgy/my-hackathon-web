import streamlit as st
import pandas as pd
from datetime import datetime
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
        color: #8b4513 !important; /* 鞍褐色标题 */
        border-bottom: 2px solid #d2b48c; /* 底部装饰线 */
        padding-bottom: 10px;
    }

    /* 输入框样式 */
    .stTextInput > div > div > input, 
    .stTextArea > div > div > textarea {
        background-color: #fffef0;
        border: 1px solid #d2b48c;
        color: #5c4033;
        font-family: 'Georgia', serif;
    }

    /* 按钮样式 */
    .stButton > button {
        background-color: #8b4513 !important;
        color: #fffef0 !important;
        border-radius: 5px;
        border: 1px solid #5c4033;
        font-family: 'Georgia', serif;
        font-weight: bold;
    }
    .stButton > button:hover {
        background-color: #a0522d !important;
        color: #fff !important;
    }

    /* 留言卡片样式 */
    .message-card {
        background-color: #fffef0;
        border: 1px solid #d2b48c;
        padding: 15px;
        margin-bottom: 15px;
        border-radius: 8px;
        box-shadow: 2px 2px 5px rgba(139, 69, 19, 0.1);
    }
    .message-meta {
        font-size: 0.85em;
        color: #8b5a2b;
        margin-bottom: 5px;
        font-style: italic;
    }
    .message-book-tag {
        display: inline-block;
        background-color: #eaddcf;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.8em;
        color: #5c4033;
        margin-top: 5px;
        border: 1px dashed #8b5a2b;
    }
</style>
""", unsafe_allow_html=True)

# --- 3. 数据读写函数 ---
DATA_FILE = "messages_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- 4. 初始化 Session State ---
if "messages" not in st.session_state:
    st.session_state.messages = load_data()

# --- 5. 侧边栏：热点统计 ---
with st.sidebar:
    st.header("🔥 借阅热点")
    
    if st.session_state.messages:
        # 安全提取书名，过滤掉空值
        books = [msg.get("book", "") for msg in st.session_state.messages if msg.get("book", "")]
        
        if books:
            counter = Counter(books)
            top_books = counter.most_common(5)
            
            for rank, (book, count) in enumerate(top_books, 1):
                st.metric(label=f"Top {rank}", value=book, delta=f"{count} 次推荐")
        else:
            st.info("暂无热门书籍数据，快去留言推荐吧！")
    else:
        st.info("暂无数据，快来写下第一条留言吧！")

# --- 6. 主界面：留言输入区 ---
st.title("📜 图书馆跨时空留言板")
st.caption("在这里留下你的阅读感悟，或推荐一本好书给后来的读者。")

with st.form("message_form"):
    col1, col2 = st.columns([1, 2])
    with col1:
        name = st.text_input("你的名字", placeholder="例如：张三")
    with col2:
        book = st.text_input("推荐书籍 (选填)", placeholder="例如：《百年孤独》")
    
    content = st.text_area("留言内容", placeholder="写下你想说的话...", height=100)
    
    submitted = st.form_submit_button("🖋️ 留下墨宝")

    if submitted:
        if name and content:
            new_msg = {
                "name": name,
                "content": content,
                "book": book.strip() if book else "", # 确保存入的是字符串
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            st.session_state.messages.insert(0, new_msg) # 新留言在最前
            save_data(st.session_state.messages)
            st.success("✨ 留言已刻入历史卷轴！")
            st.rerun() # 刷新页面显示新留言
        else:
            st.error("名字和内容是必填的哦！")

# --- 7. 主界面：历史留言展示区 ---
st.divider()
st.subheader("📖 历史回响")

if st.session_state.messages:
    for msg in st.session_state.messages:
        # --- 核心修复点在这里 ---
        # 使用 str() 包裹并处理 None 值，防止报错
        raw_book = msg.get("book")
        book_display = str(raw_book).strip() if raw_book else "" 
        
        with st.container():
            st.markdown(f"""
            <div class="message-card">
                <div class="message-meta">
                    🖋️ **{msg.get('name', '匿名')}** · 🕰️ {msg.get('time', '')}
                </div>
                <div style="margin: 10px 0; line-height: 1.6;">
                    {msg.get('content', '')}
                </div>
                {f'<div class="message-book-tag">📚 推荐书籍：{book_display}</div>' if book_display else ''}
            </div>
            """, unsafe_allow_html=True)
else:
    st.empty()
