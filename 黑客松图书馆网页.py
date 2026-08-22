import streamlit as st

# 1. 写个大标题
st.title("📚 图书馆跨时空留言板")

# 2. 写个输入框，让用户输入书名
book_name = st.text_input("请输入你想查询的书名或ISBN：")

# 3. 当用户输入内容后，打印出来
if book_name:
    st.success(f"正在为你查找《{book_name}》的遗留疑问...")
    st.write("这里以后会显示AI匹配的结果哦！")