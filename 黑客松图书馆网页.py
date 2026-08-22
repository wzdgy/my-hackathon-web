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
        color: #8b4513 !important; /*  saddlebrown */
        border-bottom: 2px solid #8b4513;
        padding-bottom: 10px;
    }

    /* 输入框样式 */
    .stTextInput > div > div > input, .stTextArea > div > div > textarea {
        background-color: #fff8dc; /* cornsilk */
        color: #5c4033;
        border: 1px solid #8b5a2b;
        font-family: 'Courier New', Courier, monospace;
    }

    /* 按钮复古化 */
    div.stButton > button {
        background-color: #8b4513 !important;
        color: #fff !important;
        border-radius: 5px;
        border: 1px solid #5c4033;
        font-family: 'Georgia', serif;
        font-weight: bold;
    }
    div.stButton > button:hover {
        background-color: #a0522d !important; /* sienna */
    }

    /* 留言卡片样式 */
    .message-card {
        background-color: #fffaf0; /* floralwhite */
        border: 1px solid #deb887;
        padding: 15px;
        margin-bottom: 15px;
        border-radius: 4px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
    }
    .message-author {
        font-weight: bold;
        color: #8b4513;
        font-size: 1.1em;
    }
    .message-time {
        font-size: 0.8em;
        color: #888;
        float: right;
    }
</style>
""", unsafe_allow_html=True)

# --- 3. 数据存储与初始化 ---
DATA_FILE = "messages_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# 初始化 Session State
if 'messages' not in st.session_state:
    st.session_state.messages = load_data()

# --- 4. 侧边栏：热点统计 ---
with st.sidebar:
    st.title("🔥 借阅热点")
    
    # 统计逻辑
    all_books = []
    for msg in st.session_state.messages:
        if "book" in msg and msg["book"]:
            all_books.append(msg["book"])
            
    if all_books:
        book_counts = Counter(all_books).most_common(5)
        df_books = pd.DataFrame(book_books, columns=["书名", "提及次数"])
        
        # 简单的复古表格样式
        st.dataframe(
            df_books, 
            hide_index=True,
            use_container_width=True
        )
        st.caption("注：基于留言板提及次数统计")
    else:
        st.info("暂无热门书籍数据，快去留言推荐吧！")

# --- 5. 主页面：留言功能 ---
st.title("📜 图书馆跨时空留言板")
st.markdown("在这里留下你的阅读感悟，或推荐一本好书给后来的读者。")

# 输入区域
col1, col2 = st.columns([1, 2])
with col1:
    user_name = st.text_input("你的名字", placeholder="例如：张三")
with col2:
    book_name = st.text_input("推荐书籍 (选填)", placeholder="例如：《百年孤独》")

message_content = st.text_area("留言内容", height=100, placeholder="写下你想说的话...")

submit_btn = st.button("🖋️ 刻下留言")

# 处理提交
if submit_btn:
    if user_name and message_content:
        new_message = {
            "name": user_name,
            "book": book_name,
            "content": message_content,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # 更新数据
        st.session_state.messages.insert(0, new_message) # 新留言插在最前面
        save_data(st.session_state.messages) # 保存到文件
        
        st.success("留言已刻录到时光卷轴中！")
        st.rerun() # 刷新页面显示新留言
    else:
        st.error("请填写名字和留言内容哦！")

# --- 6. 展示区域 ---
st.divider()
st.subheader("📖 历史回响")

if not st.session_state.messages:
    st.markdown("*暂无留言，来做第一个留名的人吧...*")
else:
    for msg in st.session_state.messages:
        book_tag = f" 📚 推荐了《{msg['book']}》" if msg.get('book') else ""
        
        st.markdown(f"""
        <div class="message-card">
            <div class="message-time">{msg['time']}</div>
            <div class="message-author">{msg['name']}{book_tag}</div>
            <p>{msg['content']}</p>
        </div>
        """, unsafe_allow_html=True)
