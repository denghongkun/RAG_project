"""RAG 核心服务：向量化、检索、生成答案。"""

from __future__ import annotations

from pathlib import Path

from langchain_community.chat_models import ChatTongyi
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough

from src.config import settings
from src.document_processor import DocumentProcessor

_KB_SUFFIXES = frozenset({".pdf", ".txt", ".doc", ".docx"})


class RagService:
    """封装完整 RAG 流程，供 UI 层调用。"""

    def __init__(self) -> None:
        self._check_env()
        self.processor = DocumentProcessor()
        self.embeddings = DashScopeEmbeddings(
            model=settings.embedding_model_name,
            dashscope_api_key=settings.dashscope_api_key,
        )
        self.llm = ChatTongyi(
            model_name=settings.llm_model_name,
            dashscope_api_key=settings.dashscope_api_key,
            temperature=0.1,
        )
        self.vector_store: FAISS | None = None
        self._ensure_dirs()
        self._try_load_vector_store()

    @staticmethod
    def _is_kb_file(path: Path) -> bool:
        return path.is_file() and path.suffix.lower() in _KB_SUFFIXES

    def list_kb_files(self) -> list[str]:
        """列出 uploads 目录下已入库支持的文档文件名（有序）。"""
        if not settings.upload_dir.exists():
            return []
        return sorted(p.name for p in settings.upload_dir.iterdir() if self._is_kb_file(p))

    def _clear_vector_store_files(self) -> None:
        for name in ("index.faiss", "index.pkl"):
            p = settings.vector_dir / name
            if p.exists():
                p.unlink()
        self.vector_store = None

    def rebuild_kb_from_uploads(self) -> tuple[int, int]:
        """根据 uploads 目录现有文件全量重建向量索引。"""
        paths = sorted(
            p for p in settings.upload_dir.iterdir() if self._is_kb_file(p)
        )
        self._clear_vector_store_files()
        if not paths:
            return 0, 0
        return self.ingest_files(paths)

    def delete_kb_file(self, filename: str) -> tuple[int, int]:
        """删除 uploads 中的指定文件并重建索引。filename 不得包含路径分隔符。"""
        if not filename or filename != Path(filename).name:
            raise ValueError("非法文件名。")
        target = (settings.upload_dir / filename).resolve()
        try:
            target.relative_to(settings.upload_dir.resolve())
        except ValueError as exc:
            raise ValueError("非法文件路径。") from exc
        if not target.is_file():
            raise FileNotFoundError(f"文件不存在：{filename}")
        target.unlink()
        return self.rebuild_kb_from_uploads()

    @staticmethod
    def _check_env() -> None:
        if not settings.dashscope_api_key:
            raise EnvironmentError(
                "未检测到 DASHSCOPE_API_KEY，请先在环境变量中设置百炼 API Key。"
            )

    @staticmethod
    def _ensure_dirs() -> None:
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
        settings.vector_dir.mkdir(parents=True, exist_ok=True)

    def _try_load_vector_store(self) -> None:
        index_file = settings.vector_dir / "index.faiss"
        pkl_file = settings.vector_dir / "index.pkl"
        if index_file.exists() and pkl_file.exists():
            self.vector_store = FAISS.load_local(
                folder_path=str(settings.vector_dir),
                embeddings=self.embeddings,
                allow_dangerous_deserialization=True,
            )

    def ingest_files(self, file_paths: list[Path]) -> tuple[int, int]:
        """读取并入库文档，返回(原始文档数, 分块数)。"""
        raw_docs = self.processor.load_documents(file_paths)
        chunks = self.processor.split_documents(raw_docs)
        if not chunks:
            return 0, 0

        if self.vector_store is None:
            self.vector_store = FAISS.from_documents(chunks, self.embeddings)
        else:
            self.vector_store.add_documents(chunks)

        self.vector_store.save_local(str(settings.vector_dir))
        return len(raw_docs), len(chunks)

    @staticmethod
    def _format_history(chat_history: list[dict[str, str]] | None) -> str:
        """将最近多轮对话整理为可注入提示词的文本。"""
        if not chat_history:
            return "无"

        # 仅保留最近 6 轮（12 条消息），兼顾上下文与 token 成本。
        recent_msgs = chat_history[-12:]
        lines: list[str] = []
        for msg in recent_msgs:
            role = "用户" if msg.get("role") == "user" else "助手"
            content = msg.get("content", "").strip()
            if content:
                lines.append(f"{role}: {content}")
        return "\n".join(lines) if lines else "无"

    def ask(self, question: str, chat_history: list[dict[str, str]] | None = None) -> dict:
        """RAG 问答，返回答案和命中文档。"""
        if self.vector_store is None:
            raise ValueError("知识库为空，请先上传文档并构建向量索引。")

        retriever = self.vector_store.as_retriever(search_kwargs={"k": settings.top_k})

        prompt = ChatPromptTemplate.from_template(
            """你是校园知识库问答助手。请基于提供的上下文回答问题：

上下文：
{context}

问题：
{question}

历史对话：
{chat_history}

要求：
1. 回答尽量准确、简洁，优先使用上下文事实。
2. 如果上下文无法支持答案，明确回答“根据当前知识库内容无法确定”。
3. 不要编造不存在的信息。"""
        )

        def format_docs(docs: list[Document]) -> str:
            return "\n\n".join(
                f"[来源: {d.metadata.get('source_file', '未知')}] {d.page_content}"
                for d in docs
            )

        chain = prompt | self.llm | StrOutputParser()
        answer = chain.invoke(
            {
                "context": format_docs(retriever.invoke(question)),
                "question": question,
                "chat_history": self._format_history(chat_history),
            }
        )
        hits = retriever.invoke(question)
        return {
            "answer": answer,
            "sources": [
                {
                    "source_file": d.metadata.get("source_file", "未知"),
                    "content": d.page_content[:300],
                }
                for d in hits
            ],
        }
