"""文档读取与切分模块。"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from langchain_community.document_loaders import (
    Docx2txtLoader,
    PyPDFLoader,
    TextLoader,
    UnstructuredWordDocumentLoader,
)
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.config import settings


class DocumentProcessor:
    """负责将上传文档转换为可入库的文档块。"""

    def __init__(self) -> None:
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
        )

    def load_documents(self, file_paths: Iterable[Path]) -> list[Document]:
        """读取多个文件并返回原始文档列表。"""
        all_docs: list[Document] = []
        for file_path in file_paths:
            suffix = file_path.suffix.lower()
            if suffix == ".pdf":
                docs = PyPDFLoader(str(file_path)).load()
            elif suffix == ".txt":
                docs = TextLoader(str(file_path), encoding="utf-8").load()
            elif suffix == ".docx":
                # 优先使用 docx2txt，失败时回退到 unstructured
                try:
                    docs = Docx2txtLoader(str(file_path)).load()
                except Exception:
                    docs = UnstructuredWordDocumentLoader(str(file_path)).load()
            elif suffix == ".doc":
                docs = UnstructuredWordDocumentLoader(str(file_path)).load()
            else:
                raise ValueError(f"不支持的文件格式: {suffix}")

            for d in docs:
                d.metadata["source_file"] = file_path.name
            all_docs.extend(docs)
        return all_docs

    def split_documents(self, docs: list[Document]) -> list[Document]:
        """切分文档为更适合检索的小块。"""
        return self.splitter.split_documents(docs)
