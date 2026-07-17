from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.config import UPLOAD_DIR
from app.deps import error_response, get_current_user, require_admin
from app.db import Base, SessionLocal, engine, get_db
from app.migrations import apply_sqlite_migrations
from app.models import ChatMessage, ChatSession, DocumentRecord, OperationLog, User
from app.rag_service import RagService
from app.schemas import (
    AskRequest,
    AskResponse,
    EditQuestionRequest,
    EditQuestionResponse,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)
from app.security import create_access_token, hash_password, verify_password


def _sse_line(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


SSE_STREAM_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


app = FastAPI(title="Campus RAG API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)
apply_sqlite_migrations(engine)
rag_service = RagService()


@app.on_event("startup")
def seed_admin() -> None:
    db = SessionLocal()
    try:
        exists = db.query(User).filter(User.username == "admin").first()
        if not exists:
            db.add(User(username="admin", password_hash=hash_password("admin123"), role="admin"))
            db.commit()
    finally:
        db.close()


def log_action(db: Session, user_id: int, action: str, target: str = "", detail: str = "") -> None:
    db.add(OperationLog(user_id=user_id, action=action, target=target, detail=detail))
    db.commit()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/register", response_model=TokenResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    exists = db.query(User).filter(User.username == req.username).first()
    if exists:
        raise error_response(400, "USERNAME_EXISTS", "用户名已存在")
    # 公开注册仅创建普通用户，管理员由系统预置或后台分配
    user = User(username=req.username, password_hash=hash_password(req.password), role="user")
    db.add(user)
    db.commit()
    token = create_access_token(req.username, user.role)
    return TokenResponse(access_token=token, username=user.username, role=user.role)


@app.post("/auth/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise error_response(401, "LOGIN_FAILED", "用户名或密码错误")
    token = create_access_token(user.username, user.role)
    return TokenResponse(access_token=token, username=user.username, role=user.role)


@app.get("/auth/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "username": user.username, "role": user.role}


@app.post("/sessions")
def create_session(
    title: str = Query(default="新会话"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = ChatSession(user_id=user.id, title=title)
    db.add(session)
    db.commit()
    db.refresh(session)
    log_action(db, user.id, "create_session", str(session.id), title)
    return {"id": session.id, "title": session.title, "created_at": session.created_at.isoformat()}


@app.get("/sessions")
def list_sessions(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(ChatSession).filter(ChatSession.user_id == user.id)
    total = q.count()
    rows = (
        q.order_by(desc(ChatSession.updated_at))
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return {
        "items": [
            {"id": s.id, "title": s.title, "updated_at": s.updated_at.isoformat()} for s in rows
        ],
        "page": page,
        "size": size,
        "total": total,
    }


@app.delete("/sessions/{session_id}")
def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.user_id == user.id)
        .first()
    )
    if not session:
        raise error_response(404, "SESSION_NOT_FOUND", "会话不存在")
    db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id, ChatMessage.user_id == user.id
    ).delete()
    db.delete(session)
    db.commit()
    log_action(db, user.id, "delete_session", str(session_id), "")
    return {"ok": True}


@app.post("/documents/upload")
async def upload_documents(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    saved: list[tuple[UploadFile, Path]] = []
    for file in files:
        target = UPLOAD_DIR / file.filename
        target.write_bytes(await file.read())
        saved.append((file, target))
    raw_total, chunk_total = 0, 0
    for file, path in saved:
        # 同名重传：先删旧向量块与数据库记录，再写入新内容
        try:
            rag_service.vector_store.delete(where={"source_file": file.filename})
        except Exception:
            pass
        db.query(DocumentRecord).filter(DocumentRecord.filename == file.filename).delete()
        rc, cc = rag_service.ingest_file(path)
        raw_total += rc
        chunk_total += cc
        db.add(DocumentRecord(user_id=user.id, filename=file.filename, chunk_count=cc))
    db.commit()
    log_action(db, user.id, "upload_documents", ",".join(f.filename for f in files), "")
    return {"raw_count": raw_total, "chunk_count": chunk_total}


@app.get("/documents")
def list_documents(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    q = db.query(DocumentRecord)
    total = q.count()
    docs = q.order_by(desc(DocumentRecord.id)).offset((page - 1) * size).limit(size).all()
    return {
        "items": [
            {
                "id": d.id,
                "filename": d.filename,
                "chunk_count": d.chunk_count,
                "created_at": d.created_at.isoformat(),
            }
            for d in docs
        ],
        "page": page,
        "size": size,
        "total": total,
    }


@app.delete("/documents/{document_id}")
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    row = db.query(DocumentRecord).filter(DocumentRecord.id == document_id).first()
    if not row:
        raise error_response(404, "DOC_NOT_FOUND", "文档不存在")
    try:
        rag_service.remove_file(row.filename)
    except ValueError as exc:
        raise error_response(400, "INVALID_DOC", str(exc)) from exc
    except Exception as exc:
        raise error_response(500, "DELETE_FAILED", str(exc)) from exc
    db.delete(row)
    db.commit()
    if db.query(DocumentRecord).count() == 0:
        rag_service.reset_kb()
    log_action(db, user.id, "delete_document", str(document_id), row.filename)
    return {"ok": True}


@app.post("/chat/ask", response_model=AskResponse)
def ask(
    req: AskRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == req.session_id, ChatSession.user_id == user.id)
        .first()
    )
    if not session:
        raise error_response(404, "SESSION_NOT_FOUND", "会话不存在")
    history_rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == req.session_id, ChatMessage.user_id == user.id)
        .order_by(ChatMessage.id.asc())
        .all()
    )
    history = [{"role": row.role, "content": row.content} for row in history_rows]
    question = req.question.strip()
    try:
        # 先做输入过滤，提前返回可解释的错误
        question = rag_service.validate_question(question)
    except ValueError as exc:
        raise error_response(400, "INVALID_QUESTION", str(exc)) from exc

    try:
        result = rag_service.ask(question, history, user.id)
    except Exception as exc:
        raise error_response(500, "RAG_ERROR", str(exc)) from exc
    db.add(ChatMessage(session_id=req.session_id, user_id=user.id, role="user", content=question))
    db.add(ChatMessage(session_id=req.session_id, user_id=user.id, role="assistant", content=result["answer"]))
    session.updated_at = datetime.utcnow()
    db.commit()
    log_action(db, user.id, "ask", str(req.session_id), req.question[:120])
    return result


@app.post("/chat/ask/stream")
def ask_stream(
    req: AskRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == req.session_id, ChatSession.user_id == user.id)
        .first()
    )
    if not session:
        raise error_response(404, "SESSION_NOT_FOUND", "会话不存在")
    history_rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == req.session_id, ChatMessage.user_id == user.id)
        .order_by(ChatMessage.id.asc())
        .all()
    )
    history = [{"role": row.role, "content": row.content} for row in history_rows]
    try:
        question = rag_service.validate_question(req.question.strip())
    except ValueError as exc:
        raise error_response(400, "INVALID_QUESTION", str(exc)) from exc

    def event_gen():
        final: dict | None = None
        try:
            for event in rag_service.iter_ask_events(question, history, user.id):
                yield _sse_line(event)
                if event.get("type") == "done":
                    final = event
                if event.get("type") == "error":
                    return
        except Exception as exc:  # noqa: BLE001
            yield _sse_line({"type": "error", "message": str(exc)})
            return
        if not final:
            yield _sse_line({"type": "error", "message": "未收到完整回答"})
            return
        try:
            db.add(ChatMessage(session_id=req.session_id, user_id=user.id, role="user", content=question))
            db.add(
                ChatMessage(
                    session_id=req.session_id,
                    user_id=user.id,
                    role="assistant",
                    content=final["answer"],
                )
            )
            session.updated_at = datetime.utcnow()
            db.commit()
            log_action(db, user.id, "ask", str(req.session_id), req.question[:120])
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            yield _sse_line({"type": "error", "message": f"保存失败：{exc}"})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers=dict(SSE_STREAM_HEADERS),
    )


@app.post("/chat/edit", response_model=EditQuestionResponse)
def edit_question(
    req: EditQuestionRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    target_msg = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.id == req.message_id,
            ChatMessage.user_id == user.id,
            ChatMessage.role == "user",
        )
        .first()
    )
    if not target_msg:
        raise error_response(404, "MESSAGE_NOT_FOUND", "要修改的提问不存在")

    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == target_msg.session_id, ChatSession.user_id == user.id)
        .first()
    )
    if not session:
        raise error_response(404, "SESSION_NOT_FOUND", "会话不存在")

    question = req.question.strip()
    try:
        question = rag_service.validate_question(question)
    except ValueError as exc:
        raise error_response(400, "INVALID_QUESTION", str(exc)) from exc

    # 删除该提问之后的全部对话（含旧回答及后续轮次）
    deleted_count = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == target_msg.session_id,
            ChatMessage.user_id == user.id,
            ChatMessage.id > target_msg.id,
        )
        .delete(synchronize_session=False)
    )

    # 更新目标用户提问
    target_msg.content = question
    db.flush()

    # 用“修改后的提问之前历史”作为上下文，重新生成该轮回答
    history_rows = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == target_msg.session_id,
            ChatMessage.user_id == user.id,
            ChatMessage.id < target_msg.id,
        )
        .order_by(ChatMessage.id.asc())
        .all()
    )
    history = [{"role": row.role, "content": row.content} for row in history_rows]
    try:
        result = rag_service.ask(question, history, user.id)
    except Exception as exc:
        raise error_response(500, "RAG_ERROR", str(exc)) from exc

    db.add(
        ChatMessage(
            session_id=target_msg.session_id,
            user_id=user.id,
            role="assistant",
            content=result["answer"],
        )
    )
    session.updated_at = datetime.utcnow()
    db.commit()
    log_action(db, user.id, "edit_question", str(target_msg.id), question[:120])
    return {
        "answer": result["answer"],
        "sources": result["sources"],
        "deleted_count": deleted_count,
    }


@app.post("/chat/edit/stream")
def edit_question_stream(
    req: EditQuestionRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    target_msg = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.id == req.message_id,
            ChatMessage.user_id == user.id,
            ChatMessage.role == "user",
        )
        .first()
    )
    if not target_msg:
        raise error_response(404, "MESSAGE_NOT_FOUND", "要修改的提问不存在")

    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == target_msg.session_id, ChatSession.user_id == user.id)
        .first()
    )
    if not session:
        raise error_response(404, "SESSION_NOT_FOUND", "会话不存在")

    question = req.question.strip()
    try:
        question = rag_service.validate_question(question)
    except ValueError as exc:
        raise error_response(400, "INVALID_QUESTION", str(exc)) from exc

    deleted_count = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == target_msg.session_id,
            ChatMessage.user_id == user.id,
            ChatMessage.id > target_msg.id,
        )
        .delete(synchronize_session=False)
    )
    target_msg.content = question
    db.commit()
    db.refresh(session)

    history_rows = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == target_msg.session_id,
            ChatMessage.user_id == user.id,
            ChatMessage.id < target_msg.id,
        )
        .order_by(ChatMessage.id.asc())
        .all()
    )
    history = [{"role": row.role, "content": row.content} for row in history_rows]

    def event_gen():
        yield _sse_line({"type": "meta", "deleted_count": deleted_count})
        final: dict | None = None
        try:
            for event in rag_service.iter_ask_events(question, history, user.id):
                yield _sse_line(event)
                if event.get("type") == "done":
                    final = event
                if event.get("type") == "error":
                    return
        except Exception as exc:  # noqa: BLE001
            yield _sse_line({"type": "error", "message": str(exc)})
            return
        if not final:
            yield _sse_line({"type": "error", "message": "未收到完整回答"})
            return
        try:
            db.add(
                ChatMessage(
                    session_id=target_msg.session_id,
                    user_id=user.id,
                    role="assistant",
                    content=final["answer"],
                )
            )
            session.updated_at = datetime.utcnow()
            db.commit()
            log_action(db, user.id, "edit_question", str(target_msg.id), question[:120])
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            yield _sse_line({"type": "error", "message": f"保存失败：{exc}"})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers=dict(SSE_STREAM_HEADERS),
    )


@app.get("/chat/history/{session_id}")
def chat_history(
    session_id: int,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id, ChatMessage.user_id == user.id
    )
    total = q.count()
    rows = q.order_by(ChatMessage.id.asc()).offset((page - 1) * size).limit(size).all()
    return {
        "items": [{"id": r.id, "role": r.role, "content": r.content} for r in rows],
        "page": page,
        "size": size,
        "total": total,
    }


@app.get("/logs")
def list_logs(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    q = db.query(OperationLog).filter(OperationLog.user_id == user.id)
    total = q.count()
    rows = q.order_by(desc(OperationLog.id)).offset((page - 1) * size).limit(size).all()
    return {
        "items": [
            {
                "id": x.id,
                "action": x.action,
                "target": x.target,
                "detail": x.detail,
                "created_at": x.created_at.isoformat(),
            }
            for x in rows
        ],
        "page": page,
        "size": size,
        "total": total,
    }
