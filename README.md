# 校园知识库问答系统（专业版重构）

技术栈：
- 前端：Vue3 + Element Plus
- 后端：FastAPI
- 数据：SQLite + Chroma
- RAG：LangChain + 百炼模型

## 企业化能力

- 登录鉴权：JWT（注册/登录/当前用户）
- 角色权限：管理员可上传文档，普通用户仅提问
- 会话管理：创建/列表/删除，会话隔离
- 全局知识库：管理员维护一套校园知识库，所有普通用户可检索
- 接口规范：统一错误码（如 `AUTH_REQUIRED`、`PERMISSION_DENIED`）
- 分页能力：会话、文档、聊天历史、操作日志
- 操作日志：记录关键操作（建会话、上传、提问、删会话）

## 目录

```text
project/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── rag_service.py
│   │   ├── db.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   └── config.py
│   ├── data/
│   ├── uploads/
│   └── requirements.txt
└── frontend/
    ├── package.json
    ├── vite.config.js
    └── src/
        ├── App.vue
        ├── main.js
        └── api/client.js
```

## 后端启动

```powershell
cd backend
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

环境变量（必需）：

```powershell
$env:DASHSCOPE_API_KEY="your_key"
```

## 前端启动

```powershell
cd frontend
npm install
npm run dev
```

打开 `http://127.0.0.1:5173` 即可使用。

开发模式下前端通过 **Vite 代理** 访问接口（`/api` → `http://127.0.0.1:8000`），请先启动后端再打开页面，否则登录会失败。

### 若浏览器控制台出现 `net::ERR_CONNECTION_REFUSED`

说明请求没有到达可用服务，请按顺序检查：

1. **后端必须先启动**（另开一个终端）：
   ```powershell
   cd backend
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```
2. 浏览器访问 [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health) 应返回 `{"status":"ok"}`。
3. 再启动前端：`cd frontend` → `npm run dev`，用页面登录。

生产环境部署时，可设置前端构建变量 `VITE_API_BASE` 指向实际 API 根地址。

## 默认管理员

- 启动后端后若数据库为空，会自动创建：
  - 用户名：`admin`
  - 密码：`admin123`

## TDD-for-AI 测试体系

已按课程要求引入 `pytest` 测试，覆盖两个层级：

- **安全测试**：输入过滤（注入/越狱）、输出规范（敏感词泄露拦截、超长截断）
- **集成测试**：认证、会话、问答、权限控制的端到端接口验证

测试目录：`backend/tests/`

运行方式：

```powershell
cd backend
python -m pytest -q
```

当前用例数：**15**（满足“>=10 条”要求）。
