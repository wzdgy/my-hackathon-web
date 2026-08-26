import streamlit as st
import datetime
# --- 1. 页面基础配置 ---
st.set_page_config(
    page_title="图书馆跨时空留言板",
    page_icon="📜",
    layout="wide",
    initial_sidebar_state="expanded"
)
# --- 2. CSS 样式定制 (羊皮纸复古风) ---
# 使用 st.markdown 注入自定义 CSS
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
# --- 3. 初始化 Session State (用于存储留言数据) ---
if 'messages' not in st.session_state:
    st.session_state.messages = [
        {
            "user": "来自1998年的读者",
            "time": "1998-05-12 14:30",
            "content": "我在《百年孤独》的第120页夹了一片枫叶，不知道现在的它还在吗？"
        },
        {
            "user": "图书管理员 AI",
            "time": "2026-08-22 09:00",
            "content": "那片枫叶已经化作书签永存了。欢迎来到跨时空留言板。"
        }
    ]
# --- 4. 侧边栏功能 ---
with st.sidebar:
    st.header("🔍 检索与上传")
    # ISBN 查询框
    isbn = st.text_input("输入 ISBN 码:", placeholder="例如: 978-7-xxx")
    # 上传旧照片按钮
    uploaded_file = st.file_uploader("📷 上传旧照片", type=["jpg", "png"])
    if uploaded_file is not None:
        st.image(uploaded_file, caption="已加载的历史影像", use_column_width=True)
    st.divider()
    st.caption("© 2026 图书馆黑客松项目组")
# --- 5. 主界面：发送留言区 ---
st.title("📜 图书馆跨时空留言板")
st.markdown("在这里留下你的疑问，或者回应百年前读者的低语...")
col1, col2, col3 = st.columns([3, 1, 1])
with col1:
    nickname = st.text_input("你的昵称", value="时空旅行者")
with col2:
    # 占位，保持布局平衡
    pass
with col3:
    # 发送按钮
    if st.button("✒️ 发送留言"):
        new_msg = {
            "user": nickname if nickname else "匿名访客",
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "content": f"刚刚发送了一条关于 ISBN:{isbn if isbn else '未知书籍'} 的新留言..."
        }
        # 将新留言插入到列表最前面
        st.session_state.messages.insert(0, new_msg)
        st.rerun()  # 刷新页面以显示新留言
st.divider()
# --- 6. 主界面：时间轴展示区 ---
st.subheader("⏳ 历史回响")
for msg in st.session_state.messages:
    with st.container():
        # 使用 HTML 构建卡片结构
        st.markdown(f"""
        <div class="message-card">
            <div style="display:flex; justify-content:space-between; margin-bottom:5px;">
                <strong style="color:#8b4513;">@{msg['user']}</strong>
                <span style="font-size:0.8em; color:#a0522d;">{msg['time']}</span>
            </div>
            <div class="ink-text">
                "{msg['content']}"
            </div>
        </div>
        """, unsafe_allow_html=True)