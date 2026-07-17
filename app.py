"""Streamlit 应用入口。"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.chat_history_store import ChatHistoryStore
from src.config import settings
from src.rag_service import RagService

st.set_page_config(page_title="校园知识库问答系统", page_icon="🎓", layout="wide")
st.title("🎓 基于 RAG + LLM 的校园知识库问答系统")
st.caption("支持 PDF / Word / TXT 上传、检索增强生成、多轮会话持久记忆。")


@st.cache_resource
def get_rag_service() -> RagService:
    return RagService()


@st.cache_resource
def get_history_store() -> ChatHistoryStore:
    return ChatHistoryStore()


def save_upload_file(upload_file) -> Path:
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    target = settings.upload_dir / upload_file.name
    with open(target, "wb") as f:
        f.write(upload_file.getbuffer())
    return target


def _session_option_label(session: dict) -> str:
    pin = "📌 " if session.get("is_pinned") else ""
    return f"{pin}{session['title']} ({session['msg_count']}条)"


def _load_active_session(store: ChatHistoryStore, session_id: str) -> None:
    st.session_state["session_id"] = session_id
    st.session_state["chat_history"] = store.load_history(session_id)


def _render_role_panel() -> bool:
    """渲染角色面板，返回是否为已认证管理员。"""
    st.sidebar.markdown("### 身份")
    role = st.sidebar.radio("选择身份", ["用户", "管理员"], key="role_select", horizontal=True)
    if "is_admin_authenticated" not in st.session_state:
        st.session_state["is_admin_authenticated"] = False

    if role == "管理员":
        password = st.sidebar.text_input(
            "管理员口令", type="password", placeholder="请输入管理员口令", key="admin_password_input"
        )
        if st.sidebar.button("管理员登录", use_container_width=True, key="btn_admin_login"):
            if password == settings.admin_password:
                st.session_state["is_admin_authenticated"] = True
                st.sidebar.success("管理员登录成功。")
            else:
                st.session_state["is_admin_authenticated"] = False
                st.sidebar.error("口令错误。")
        return bool(st.session_state["is_admin_authenticated"])

    st.session_state["is_admin_authenticated"] = False
    return False


def render_sidebar_user() -> None:
    st.sidebar.info("当前为用户身份：仅可提问，知识库由管理员在「管理员」身份下维护。")


def render_sidebar_admin_sessions(store: ChatHistoryStore) -> None:
    """管理员侧栏：会话管理（用于测试问答）。"""
    st.sidebar.markdown("### 会话管理（测试）")
    search_kw = st.sidebar.text_input("搜索会话", placeholder="输入会话标题关键词", key="input_session_search")
    all_sessions = store.list_sessions()
    sessions = store.list_sessions(query=search_kw)
    if not all_sessions:
        sid = store.create_session("新会话")
        all_sessions = store.list_sessions()
        sessions = store.list_sessions(query=search_kw)
        _load_active_session(store, sid)
    if not sessions:
        st.sidebar.info("未找到匹配会话，已显示全部会话。")
        sessions = all_sessions

    session_ids = [s["session_id"] for s in sessions]
    current_session = st.session_state.get("session_id", session_ids[0])
    if current_session not in session_ids:
        current_session = session_ids[0]
        _load_active_session(store, current_session)

    selected_id = st.sidebar.selectbox(
        "会话列表",
        options=session_ids,
        format_func=lambda x: _session_option_label(
            next(s for s in sessions if s["session_id"] == x)
        ),
        index=session_ids.index(current_session),
        key="select_session",
    )
    if selected_id != current_session:
        _load_active_session(store, selected_id)

    current_meta = next(s for s in sessions if s["session_id"] == st.session_state["session_id"])
    pin_text = "取消置顶当前会话" if current_meta.get("is_pinned") else "置顶当前会话"
    if st.sidebar.button(pin_text, use_container_width=True, key="btn_pin"):
        store.set_session_pinned(
            st.session_state["session_id"], not bool(current_meta.get("is_pinned"))
        )
        st.sidebar.success("已更新置顶状态。")

    if st.sidebar.button("清空当前会话历史", use_container_width=True, key="btn_clear"):
        st.session_state["chat_history"] = []
        store.clear_history(st.session_state["session_id"])
        st.sidebar.success("当前会话历史已清空。")

    if st.sidebar.button("新建会话", use_container_width=True, key="btn_new"):
        new_sid = store.create_session("新会话")
        _load_active_session(store, new_sid)
        st.sidebar.success("已新建会话。")

    with st.sidebar.form("rename_session_form", clear_on_submit=True):
        new_title = st.text_input("重命名当前会话", placeholder="输入新的会话标题")
        rename_submitted = st.form_submit_button("保存会话名", use_container_width=True)
    if rename_submitted:
        store.rename_session(st.session_state["session_id"], new_title)
        st.sidebar.success("会话已重命名。")

    st.sidebar.markdown("#### 删除会话")
    if "delete_confirm_mode" not in st.session_state:
        st.session_state["delete_confirm_mode"] = False

    if not st.session_state["delete_confirm_mode"]:
        if st.sidebar.button("删除当前会话", use_container_width=True, key="btn_delete"):
            st.session_state["delete_confirm_mode"] = True
    else:
        st.sidebar.warning("确认删除？该操作不可恢复。")
        col_a, col_b = st.sidebar.columns(2)
        if col_a.button("确认", use_container_width=True, key="btn_delete_confirm"):
            deleting_id = st.session_state["session_id"]
            store.delete_session(deleting_id)
            remain = store.list_sessions()
            if remain:
                _load_active_session(store, remain[0]["session_id"])
            else:
                sid = store.create_session("新会话")
                _load_active_session(store, sid)
            st.session_state["delete_confirm_mode"] = False
            st.sidebar.success("会话已删除。")
        if col_b.button("取消", use_container_width=True, key="btn_delete_cancel"):
            st.session_state["delete_confirm_mode"] = False


def render_sidebar(rag: RagService, store: ChatHistoryStore) -> bool:
    st.sidebar.header("⚙️ 控制台")
    is_admin = _render_role_panel()
    if is_admin:
        st.sidebar.markdown("### 知识库")
        st.sidebar.caption("请在主界面「知识库管理」中查看、上传或删除文档。")
        render_sidebar_admin_sessions(store)
    else:
        render_sidebar_user()
    return is_admin


def render_kb_admin_panel(rag: RagService) -> None:
    """管理员主区：知识库文件列表、上传、删除。"""
    st.subheader("📁 知识库文档")
    files = rag.list_kb_files()
    if not files:
        st.caption("暂无文档，请在下方上传。")
    else:
        for i, name in enumerate(files):
            col_a, col_b = st.columns([5, 1])
            col_a.markdown(f"- **{name}**")
            if col_b.button("删除", key=f"kb_del_{i}", use_container_width=True):
                try:
                    raw_count, chunk_count = rag.delete_kb_file(name)
                    st.success(
                        f"已删除「{name}」并重建索引：原始文档 {raw_count} 段，文本块 {chunk_count} 个。"
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(f"删除失败：{exc}")

    st.divider()
    st.markdown("#### 添加文档")
    uploads = st.file_uploader(
        "选择校园资料（可多选）",
        type=["pdf", "txt", "doc", "docx"],
        accept_multiple_files=True,
        key="kb_uploader",
    )
    if st.button("上传并入库", type="primary", use_container_width=True, key="btn_kb_ingest"):
        if not uploads:
            st.warning("请先选择至少一个文件。")
        else:
            for f in uploads:
                save_upload_file(f)
            try:
                raw_count, chunk_count = rag.rebuild_kb_from_uploads()
                st.success(
                    f"已根据当前 uploads 目录全量重建索引：原始文档 {raw_count} 段，文本块 {chunk_count} 个。"
                )
                st.rerun()
            except Exception as exc:
                st.error(f"入库失败：{exc}")


def render_chat_history() -> None:
    for msg in st.session_state["chat_history"]:
        with st.chat_message("user" if msg["role"] == "user" else "assistant"):
            st.write(msg["content"])
            if msg["role"] == "assistant" and msg.get("sources"):
                with st.expander("查看本轮参考片段"):
                    for idx, item in enumerate(msg["sources"], start=1):
                        st.markdown(f"**{idx}. 来源文件：{item['source_file']}**")
                        st.write(item["content"])


def render_header_metrics(*, compact: bool) -> None:
    total_msgs = len(st.session_state["chat_history"])
    user_msgs = sum(1 for x in st.session_state["chat_history"] if x["role"] == "user")
    assistant_msgs = total_msgs - user_msgs
    if compact:
        st.caption(
            f"消息 {total_msgs} 条（问 {user_msgs} / 答 {assistant_msgs}） · "
            f"LLM `{settings.llm_model_name}` · Embedding `{settings.embedding_model_name}` · Top-K `{settings.top_k}`"
        )
        return
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("当前会话ID", st.session_state["session_id"][:8])
    col2.metric("总消息数", total_msgs)
    col3.metric("用户提问", user_msgs)
    col4.metric("助手回答", assistant_msgs)


def render_chat_block(rag: RagService, history_store: ChatHistoryStore, *, compact_metrics: bool) -> None:
    render_header_metrics(compact=compact_metrics)
    st.subheader("💬 智能问答")
    render_chat_history()

    question = st.chat_input("请输入你的问题，例如：学校请假流程需要提交哪些材料？")
    if question:
        user_msg = {"role": "user", "content": question}
        st.session_state["chat_history"].append(user_msg)
        history_store.append_message(
            st.session_state["session_id"], "user", question.strip()
        )
        with st.chat_message("user"):
            st.write(question)

        with st.chat_message("assistant"):
            with st.spinner("正在检索知识库并生成答案..."):
                try:
                    result = rag.ask(
                        question.strip(),
                        chat_history=st.session_state["chat_history"][:-1],
                    )
                except Exception as exc:
                    st.error(f"问答失败：{exc}")
                    st.stop()

            st.write(result["answer"])
            with st.expander("查看本轮参考片段"):
                for idx, item in enumerate(result["sources"], start=1):
                    st.markdown(f"**{idx}. 来源文件：{item['source_file']}**")
                    st.write(item["content"])

        assistant_msg = {
            "role": "assistant",
            "content": result["answer"],
            "sources": result["sources"],
        }
        st.session_state["chat_history"].append(assistant_msg)
        history_store.append_message(
            st.session_state["session_id"],
            "assistant",
            result["answer"],
            sources=result["sources"],
        )


def main() -> None:
    try:
        rag = get_rag_service()
        history_store = get_history_store()
    except Exception as exc:
        st.error(f"初始化失败：{exc}")
        st.stop()

    if "session_id" not in st.session_state:
        sessions = history_store.list_sessions()
        st.session_state["session_id"] = (
            sessions[0]["session_id"] if sessions else history_store.create_session("新会话")
        )
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = history_store.load_history(st.session_state["session_id"])

    is_admin = render_sidebar(rag, history_store)

    if is_admin:
        tab_kb, tab_chat = st.tabs(["知识库管理", "智能问答"])
        with tab_kb:
            render_kb_admin_panel(rag)
        with tab_chat:
            right = st.columns([2.2, 1])
            with right[0]:
                render_chat_block(rag, history_store, compact_metrics=False)
            with right[1]:
                st.subheader("🧠 系统状态")
                st.info(
                    f"身份: `管理员`\n\n"
                    f"LLM: `{settings.llm_model_name}`\n\n"
                    f"Embedding: `{settings.embedding_model_name}`\n\n"
                    f"Top-K: `{settings.top_k}`"
                )
                st.caption("历史消息保存在 SQLite，并同步输出 JSON 快照。")
    else:
        render_chat_block(rag, history_store, compact_metrics=True)


if __name__ == "__main__":
    main()
