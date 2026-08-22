import streamlit as st
import pandas as pd
from datetime import datetime
import json
import os

# --- 1. 页面基础配置 ---
st.set_page_config(
    page_title="图书馆跨时空留言板",
    page_icon="📚",
    layout="wide"
)

# --- 2. CSS 样式定制 (羊皮纸复古风) ---
# 这是从代码1中移植过来的“皮肤”
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


def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


if 'messages_data' not in st.session_state:
    st.session_state.messages_data = load_data()
if 'current_book' not in st.session_state:
    st.session_state.current_book = None
if 'view_message' not in st.session_state:
    st.session_state.view_message = None

# --- 4. 书籍数据库 ---
BOOKS_DATABASE = {
    "9787544291163": {"name": "百年孤独", "author": "加西亚·马尔克斯", "theme": "魔幻现实主义"},
    "9787020002207": {"name": "红楼梦", "author": "曹雪芹", "theme": "古典文学"},
    "9787544253994": {"name": "三体", "author": "刘慈欣", "theme": "科幻"},
    "9787508684031": {"name": "活着", "author": "余华", "theme": "现实主义"}
}


def search_book(query):
    """搜索书籍"""
    results = []
    query = query.strip().lower()
    for isbn, info in BOOKS_DATABASE.items():
        if query in isbn or query in info["name"].lower():
            results.append({**info, "isbn": isbn})
    return results


# --- 5. 功能函数 ---
def display_book_messages(book_key):
    """显示书籍的留言列表"""
    if book_key not in st.session_state.messages_data:
        st.session_state.messages_data[book_key] = []
    messages = st.session_state.messages_data[book_key]

    if not messages:
        st.info("📭 暂无留言，成为第一个留言的人吧！")
        return

    st.subheader(f"📝 共 {len(messages)} 条留言")
    for idx, msg in enumerate(messages):
        with st.container():
            # 使用自定义的message-card样式
            st.markdown(f"""
            <div class="message-card">
                <div style="display:flex; justify-content:space-between; margin-bottom:5px;">
                    <strong style="color:#8b4513;">{msg['message_title']}</strong>
                    <span style="font-size:0.8em; color:#a0522d;">{msg['timestamp']}</span>
                </div>
                <div class="ink-text">
                    留言者：{msg['name']}
                </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"查看详情", key=f"view_{book_key}_{idx}"):
                st.session_state.view_message = msg
                st.rerun()
            st.divider()


def display_message_detail(message):
    """显示留言详情"""
    st.subheader("📖 留言详情")
    col1, col2 = st.columns(2)
    with col1:
        st.write("**留言主题：**", message['message_title'])
        st.write("**留言者：**", message['name'])
        st.write("**联系方式：**", message.get('contact', '未填写'))
    with col2:
        st.write("**留言时间：**", message['timestamp'])
        st.write("**疑问位置：**", message.get('location', '未指定'))
    st.write("**疑问内容：**")
    st.info(message['content'])
    if message.get('notes'):
        st.write("**备注：**")
        st.write(message['notes'])
    if st.button("返回留言列表"):
        st.session_state.view_message = None
        st.rerun()


def add_message_form(book_key, book_info):
    """添加留言表单"""
    st.subheader("✏️ 添加新留言")
    with st.form(key="message_form"):
        message_title = st.text_input("留言主题（简略介绍）*", placeholder="例如：关于第3章的疑问")
        name = st.text_input("姓名（可选匿名）", placeholder="输入您的姓名或留空匿名")
        contact = st.text_input("联系方式（可选）", placeholder="邮箱或电话")
        location = st.text_input("疑问位置（可选）", placeholder="例如：第120页")
        content = st.text_area("疑问内容*", placeholder="请详细描述你的问题或感想...")
        notes = st.text_area("备注（可选）")

        submitted = st.form_submit_button("提交留言")
        if submitted:
            if message_title and content:
                new_message = {
                    "message_title": message_title,
                    "name": name if name else "匿名",
                    "contact": contact,
                    "location": location,
                    "content": content,
                    "notes": notes,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
                }
                if book_key not in st.session_state.messages_data:
                    st.session_state.messages_data[book_key] = []
                st.session_state.messages_data[book_key].insert(0, new_message)
                save_data(st.session_state.messages_data)
                st.success("留言成功！")
                st.rerun()
            else:
                st.error("留言主题和内容是必填项哦！")


# --- 6. 主程序入口 ---
def main():
    st.title("📚 图书馆跨时空留言板")
    st.markdown("在这里留下你的疑问，或者回应百年前读者的低语...")

    # 侧边栏：搜索书籍
    with st.sidebar:
        st.header("🔍 检索书籍")
        query = st.text_input("输入书名或ISBN", placeholder="例如：百年孤独")
        if query:
            results = search_book(query)
            if results:
                for book in results:
                    if st.button(f"{book['name']} - {book['author']}"):
                        st.session_state.current_book = book['isbn']
                        st.session_state.view_message = None
            else:
                st.info("未找到相关书籍")
        else:
            st.caption("请输入关键词搜索")

        st.divider()
        st.caption("© 2026 图书馆黑客松项目组")

    # 主区域逻辑
    if st.session_state.view_message:
        display_message_detail(st.session_state.view_message)
    elif st.session_state.current_book:
        book_info = BOOKS_DATABASE.get(st.session_state.current_book)
        st.header(f"当前书籍：《{book_info['name']}》")
        tab1, tab2 = st.tabs(["📝 查看留言", "✏️ 我要留言"])
        with tab1:
            display_book_messages(st.session_state.current_book)
        with tab2:
            add_message_form(st.session_state.current_book, book_info)
    else:
        st.info("👈 请在左侧搜索并选择一本书籍开始留言")


if __name__ == "__main__":
    main()
