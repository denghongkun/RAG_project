"""项目配置。"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


def _is_ascii_path(path: Path) -> bool:
    """判断路径是否仅包含 ASCII 字符。"""
    try:
        str(path).encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def _default_vector_dir(base_dir: Path) -> Path:
    """
    为 FAISS 选择默认向量库目录。

    说明：
    - Windows 下某些 FAISS 版本对非 ASCII 路径支持不稳定。
    - 若项目路径含中文，则回退到系统临时目录下的 ASCII 路径，避免写入失败。
    """
    project_default = base_dir / "data" / "vector_store"
    if _is_ascii_path(project_default):
        return project_default
    return Path(tempfile.gettempdir()) / "campus_rag_vector_store"


@dataclass
class Settings:
    """统一管理项目运行参数。"""

    base_dir: Path = Path(__file__).resolve().parent.parent
    upload_dir: Path = base_dir / "uploads"
    vector_dir: Path = Path(
        os.getenv("VECTOR_DIR", str(_default_vector_dir(base_dir)))
    )
    history_db_path: Path = Path(
        os.getenv("HISTORY_DB_PATH", str(base_dir / "data" / "chat_history.db"))
    )
    history_json_path: Path = Path(
        os.getenv("HISTORY_JSON_PATH", str(base_dir / "data" / "chat_history.json"))
    )

    # 百炼 API Key，用户已在系统环境变量中设置
    dashscope_api_key: str | None = os.getenv("DASHSCOPE_API_KEY")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "admin123")

    # 百炼模型名称（可按需修改）
    llm_model_name: str = os.getenv("LLM_MODEL_NAME", "qwen-plus")
    embedding_model_name: str = os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-v3")

    # 文本切分参数
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "800"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "120"))

    # 检索参数
    top_k: int = int(os.getenv("TOP_K", "4"))


settings = Settings()
