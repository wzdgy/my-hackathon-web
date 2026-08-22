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
        color: #8b4513 !important; /* 鞍褐色 */
        border-bottom: 2px solid #8b4513;
        padding-bottom: 10px;
    }

    /* 输入框样式 */
    .stTextInput > div > div > input, .stTextArea > div > div > textarea {
        background-color: #fffef0;
        color: #5c4033;
        border: 1px solid #d2b48c;
        font-family: 'Courier New', Courier, monospace; /* 打字机字体 */
    }

    /* 按钮样式 */
    .stButton > button {
        background-color: #8b4513;
        color: #fffef0;
        border: none;
        font-family: 'Georgia', serif;
        font-weight: bold;
        border-radius: 5px;
    }
    .stButton > button:hover {
        background-color: #a0522d;
        color: white;
    }

    /* 留言卡片样式 */
    .msg-card {
        background-color: #fff8dc; /* 玉米丝色 */
        border: 1px solid #deb887;
        padding: 15px;
        margin-bottom: 15px;
        border-radius: 8px;
        box-shadow: 3px 3px 5px rgba(139, 69, 19, 0.1);
    }
    
    .msg-header {
        font-size: 0.9em;
        color: #8b4513;
        margin-bottom: 5px;
        font-weight: bold;
    }

    .msg-content {
        font-size: 1.1em;
        line-height: 1.5;
    }
    
    .book-tag {
        display: inline-block;
        background-color: #8b4513;
        color: white;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.8em;
        margin-top: 5px;
    }
</style>
""", unsafe_allow_html=True)

# --- 3. 数据处理函数 ---
DATA_FILE = "messages_data.json"

def load_data():
    """加载留言数据"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []

def save_data(data):
    """保存留言数据"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- 4. 主程序逻辑 ---

# 初始化 Session State
if "messages" not in st.session_state:
    st.session_state.messages = load_data()

# === 侧边栏：热点统计 ===
with st.sidebar:
    st.header("🔥 借阅热点")
    
    # 统计书籍出现次数
    book_counter = Counter()
    for msg in st.session_state.messages:
        # 【关键修复】使用 .get('book') 防止旧数据没有 book 字段导致报错
        book = msg.get("book", "").strip()
        if book:
            book_counter[book] += 1
            
    if book_counter:
        # 获取前 5 名
        top_books = book_counter.most_common(5)
        for rank, (book, count) in enumerate(top_books, 1):
            st.markdown(f"**No.{rank}** 《{book}》 - {count}人推荐")
    else:
        st.info("暂无热门书籍数据，快去留言推荐吧！")

# === 主区域：留言功能 ===
st.title("📜 图书馆跨时空留言板")
st.caption("在这里留下你的阅读感悟，或推荐一本好书给后来的读者。")

st.divider()

# 输入区
col1, col2 = st.columns([1, 1])
with col1:
    user_name = st.text_input("你的名字", placeholder="例如：张三")
with col2:
    book_name = st.text_input("推荐书籍 (选填)", placeholder="例如：《百年孤独》")

message_content = st.text_area("留言内容", height=100, placeholder="写下你想说的话...")

if st.button("🪶 刻下留言", use_container_width=True):
    if user_name and message_content:
        new_msg = {
            "name": user_name,
            "content": message_content,
            "book": book_name, # 即使为空也没关系，后面会处理
            "time": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        
        # 添加到列表头部（最新的在最上面）
        st.session_state.messages.insert(0, new_msg)
        save_data(st.session_state.messages)
        st.success("✨ 留言已刻入历史！")
        st.rerun() # 刷新页面以更新热点统计
    else:
        st.error("请填写名字和留言内容哦！")

# === 展示区：历史回响 ===
st.divider()
st.subheader("📖 历史回响")

if not st.session_state.messages:
    st.markdown("*暂无留言，快来抢沙发...*")
else:
    for msg in st.session_state.messages:
        # 【关键修复】安全获取字段，防止 KeyError
        name = msg.get("name", "匿名")
        content = msg.get("content", "")
        time = msg.get("time", "")
        book = msg.get("book", "").strip() # 去除可能的空格
        
        # 构建书籍标签 HTML
        book_html = ""
        if book:
            book_html = f'<div class="book-tag">📚 推荐了《{book}》</div>'

        # 渲染卡片
        st.markdown(f"""
        <div class="msg-card">
            <div class="msg-header">
                ✒️ {name} <span style="float:right; font-weight:normal; font-size:0.8em">🕰️ {time}</span>
            </div>
            <div class="msg-content">{content}</div>
            {book_html}
        </div>
        """, unsafe_allow_html=True)
