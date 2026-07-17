<template>
  <!-- 管理员 -->
  <div v-if="authed && user.role === 'admin'" class="shell">
    <aside class="aside">
      <div class="brand">
        <div class="brand-mark" aria-hidden="true">◇</div>
        <div class="brand-text">
          <span class="brand-title">Campus RAG</span>
          <span class="brand-sub">知识库控制台</span>
        </div>
      </div>

      <div class="profile">
        <el-avatar :size="44" class="profile-avatar">{{ avatarLetter(user.username) }}</el-avatar>
        <div class="profile-meta">
          <span class="profile-name">{{ user.username }}</span>
          <span class="profile-role">管理员</span>
        </div>
        <el-button class="profile-out" text type="primary" @click="logout">退出</el-button>
      </div>

      <div class="panel-block">
        <h3 class="block-title">上传文档</h3>
        <p class="block-desc">PDF · TXT · Word，入库后全体用户可检索。</p>
        <el-upload
          class="upload-elegant"
          drag
          multiple
          :auto-upload="false"
          :on-change="onFileChange"
          :file-list="fileList"
        >
          <div class="upload-inner">
            <span class="upload-icon">+</span>
            <p>拖拽文件到此处，或点击选择</p>
          </div>
        </el-upload>
        <el-button class="btn-full" type="primary" :loading="uploading" round @click="handleUpload">
          上传并入库
        </el-button>
      </div>
    </aside>

    <main class="main">
      <header class="main-header">
        <div>
          <h1 class="main-title">文档索引</h1>
          <p class="main-subtitle">管理已入库文件与向量分块</p>
        </div>
        <el-button round :loading="docsLoading" @click="loadDocs">刷新列表</el-button>
      </header>

      <div class="surface surface-pad">
        <el-alert
          class="tip-alert"
          type="info"
          :closable="false"
          show-icon
          title="管理员仅维护知识库；体验问答请使用普通用户账号登录。"
        />
        <div class="table-wrap">
          <el-table
            v-loading="docsLoading"
            :data="documents"
            class="docs-table"
            height="100%"
            stripe
            empty-text="暂无文档，请在左侧上传"
          >
            <el-table-column prop="id" label="ID" width="72" />
            <el-table-column prop="filename" label="文件名" min-width="220" />
            <el-table-column prop="chunk_count" label="分块" width="88" align="center" />
            <el-table-column prop="created_at" label="上传时间" width="200" />
            <el-table-column label="" width="100" align="right" fixed="right">
              <template #default="{ row }">
                <el-button link type="danger" @click="handleDeleteDoc(row)">移除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>
    </main>
  </div>

  <!-- 普通用户 -->
  <div v-else-if="authed && user.role === 'user'" class="shell">
    <aside class="aside">
      <div class="brand">
        <div class="brand-mark brand-mark--user" aria-hidden="true">◆</div>
        <div class="brand-text">
          <span class="brand-title">Campus RAG</span>
          <span class="brand-sub">智能问答</span>
        </div>
      </div>

      <div class="profile">
        <el-avatar :size="44" class="profile-avatar profile-avatar--user">{{ avatarLetter(user.username) }}</el-avatar>
        <div class="profile-meta">
          <span class="profile-name">{{ user.username }}</span>
          <span class="profile-role">用户</span>
        </div>
        <el-button class="profile-out" text type="primary" @click="logout">退出</el-button>
      </div>

      <div class="panel-block">
        <h3 class="block-title">会话</h3>
        <div class="session-create">
          <el-input v-model="newSessionTitle" placeholder="新会话标题" clearable />
          <el-button type="primary" round @click="handleCreateSession">新建</el-button>
        </div>
        <el-scrollbar class="session-scroll">
          <button
            v-for="s in sessions"
            :key="s.id"
            type="button"
            class="session-pill"
            :class="{ 'session-pill--active': s.id === activeSessionId }"
            @click="switchSession(s.id)"
          >
            <span class="session-pill-title">{{ s.title }}</span>
            <span class="session-pill-del" role="button" tabindex="0" @click.stop="handleDeleteSession(s.id)">×</span>
          </button>
        </el-scrollbar>
      </div>
    </aside>

    <main class="main main-chat">
      <header class="chat-top">
        <div>
          <h1 class="main-title">校园知识库问答</h1>
          <p class="main-subtitle">基于检索增强生成，回答将引用知识库来源</p>
        </div>
      </header>

      <div class="surface surface-chat">
        <div ref="chatScrollRef" class="chat-stream">
          <div v-if="!messages.length" class="chat-empty">
            <div class="chat-empty-icon" aria-hidden="true">💬</div>
            <p class="chat-empty-title">开始提问</p>
            <p class="chat-empty-desc">在下方输入框描述你的问题，例如选课、请假或办事流程。</p>
          </div>
          <div
            v-for="item in messages"
            :key="item.id || item.content + item.role"
            class="msg-row"
            :class="{ 'msg-row--user': item.role === 'user' }"
          >
            <div class="msg-avatar" :class="item.role === 'user' ? 'msg-avatar--user' : 'msg-avatar--ai'">
              {{ item.role === "user" ? "我" : "AI" }}
            </div>
            <div class="msg-stack">
              <div class="msg-bubble" :class="item.role === 'user' ? 'msg-bubble--user' : 'msg-bubble--ai'">
                <div class="msg-content">{{ item.content }}</div>
                <div v-if="item.sources?.length" class="msg-sources">
                  <span v-for="(s, idx) in item.sources" :key="s.source_file + idx" class="src-chip">{{ s.source_file }}</span>
                </div>
                <div v-if="item.role === 'user'" class="msg-actions">
                  <el-button
                    class="btn-edit-reply"
                    circle
                    size="small"
                    title="编辑并重答"
                    aria-label="编辑并重答"
                    @click="handleEditQuestion(item)"
                  >
                    <span class="btn-edit-reply__icon" aria-hidden="true">✎</span>
                  </el-button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="composer">
          <el-input
            v-model="question"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }"
            placeholder="输入问题，Enter 发送 · Shift+Enter 换行"
            resize="none"
            class="composer-input"
            @keydown="onComposerKeydown"
          />
          <el-button type="primary" class="composer-send" round :loading="asking" @click="handleAsk">发送</el-button>
        </div>
      </div>
    </main>
  </div>

  <!-- 登录 / 注册 -->
  <div v-else class="auth-page">
    <div class="auth-bg" aria-hidden="true" />
    <div class="auth-card">
      <div class="auth-card-head">
        <div class="auth-logo">◇</div>
        <h1 class="auth-title">校园知识库问答</h1>
        <p class="auth-tagline">RAG + 大模型 · 安全分角色 · 多会话</p>
      </div>
      <el-tabs v-model="authTab" class="auth-tabs">
        <el-tab-pane label="登录" name="login">
          <div class="auth-fields">
            <el-input v-model="authForm.username" size="large" placeholder="用户名" clearable />
            <el-input v-model="authForm.password" size="large" type="password" placeholder="密码" show-password clearable />
            <el-button type="primary" size="large" round :loading="authLoading" class="auth-submit" @click="handleLogin">
              进入系统
            </el-button>
          </div>
        </el-tab-pane>
        <el-tab-pane label="注册" name="register">
          <div class="auth-fields">
            <el-input v-model="registerForm.username" size="large" placeholder="用户名（至少 3 位）" clearable />
            <el-input v-model="registerForm.password" size="large" type="password" placeholder="密码（至少 6 位）" show-password clearable />
            <el-input v-model="registerForm.password2" size="large" type="password" placeholder="确认密码" show-password clearable />
            <el-button type="primary" size="large" round :loading="authLoading" class="auth-submit" @click="handleRegisterSubmit">
              注册并登录
            </el-button>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup>
import { nextTick, onMounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  createSession,
  deleteDocument,
  deleteSession,
  fetchDocs,
  fetchHistory,
  fetchSessions,
  login,
  me,
  postSse,
  register,
  uploadDocs,
} from "./api/client";

function apiError(err, fallback) {
  const d = err?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (d && typeof d === "object" && d.message) return d.message;
  return err?.message || fallback;
}

function avatarLetter(name) {
  if (!name) return "?";
  const c = name.trim()[0];
  return /[a-z]/i.test(c) ? c.toUpperCase() : c;
}

const authed = ref(false);
const user = ref({ username: "", role: "" });
const authTab = ref("login");
const authForm = ref({ username: "", password: "" });
const registerForm = ref({ username: "", password: "", password2: "" });
const authLoading = ref(false);

const fileList = ref([]);
const selectedFiles = ref([]);
const documents = ref([]);
const docsLoading = ref(false);
const sessions = ref([]);
const activeSessionId = ref(null);
const newSessionTitle = ref("");
const messages = ref([]);
const question = ref("");
const uploading = ref(false);
const asking = ref(false);
const chatScrollRef = ref(null);

const onFileChange = (_file, files) => {
  fileList.value = files;
  selectedFiles.value = files.map((x) => x.raw).filter(Boolean);
};

const loadDocs = async () => {
  if (user.value.role !== "admin") return;
  docsLoading.value = true;
  try {
    const res = await fetchDocs();
    documents.value = res.data.items || [];
  } catch (e) {
    ElMessage.error(apiError(e, "加载文档列表失败"));
  } finally {
    docsLoading.value = false;
  }
};

const loadSessions = async () => {
  const res = await fetchSessions();
  sessions.value = res.data.items || [];
  if (!activeSessionId.value && sessions.value.length) activeSessionId.value = sessions.value[0].id;
};

const loadHistory = async (sid) => {
  if (!sid) return;
  const res = await fetchHistory(sid);
  messages.value = (res.data.items || []).map((x) => ({ ...x, sources: [] }));
};

const scrollChatBottom = () => {
  nextTick(() => {
    const el = chatScrollRef.value;
    if (el) el.scrollTop = el.scrollHeight;
  });
};

watch(messages, () => scrollChatBottom(), { deep: true });

const switchSession = async (sid) => {
  activeSessionId.value = sid;
  await loadHistory(sid);
};

const handleCreateSession = async () => {
  await createSession(newSessionTitle.value.trim() || "新会话");
  newSessionTitle.value = "";
  await loadSessions();
  if (sessions.value.length) await switchSession(sessions.value[0].id);
};

const handleDeleteSession = async (sid) => {
  try {
    await ElMessageBox.confirm(
      "删除后将无法恢复该会话下的全部聊天记录。确定删除吗？",
      "删除会话",
      {
        type: "warning",
        confirmButtonText: "删除",
        cancelButtonText: "取消",
        roundButton: true,
      }
    );
  } catch {
    return;
  }
  try {
    await deleteSession(sid);
    ElMessage.success("会话已删除");
    await loadSessions();
    if (sessions.value.length) await switchSession(sessions.value[0].id);
    else {
      activeSessionId.value = null;
      messages.value = [];
    }
  } catch (e) {
    ElMessage.error(apiError(e, "删除会话失败"));
  }
};

const handleUpload = async () => {
  if (!selectedFiles.value.length) return ElMessage.warning("请先选择文件");
  const formData = new FormData();
  selectedFiles.value.forEach((f) => formData.append("files", f));
  uploading.value = true;
  try {
    const res = await uploadDocs(formData);
    ElMessage.success(`入库成功：原始段 ${res.data.raw_count}，分块 ${res.data.chunk_count}`);
    selectedFiles.value = [];
    fileList.value = [];
    await loadDocs();
  } catch (e) {
    ElMessage.error(apiError(e, "入库失败"));
  } finally {
    uploading.value = false;
  }
};

const handleDeleteDoc = async (row) => {
  try {
    await ElMessageBox.confirm(`确定从知识库删除「${row.filename}」？向量与磁盘文件将一并移除。`, "确认删除", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
      roundButton: true,
    });
    await deleteDocument(row.id);
    ElMessage.success("已删除");
    await loadDocs();
  } catch (e) {
    if (e !== "cancel") ElMessage.error(apiError(e, "删除失败"));
  }
};

const handleEditQuestion = async (item) => {
  try {
    const { value } = await ElMessageBox.prompt("修改后将删除该提问之后的对话，并重新生成回答。", "编辑提问", {
      inputValue: item.content,
      inputType: "textarea",
      inputPlaceholder: "请输入新的提问内容",
      confirmButtonText: "确认重答",
      cancelButtonText: "取消",
    });
    const newQuestion = (value || "").trim();
    if (!newQuestion) return ElMessage.warning("提问不能为空");

    const idx = messages.value.findIndex((m) => m.id === item.id && m.role === "user");
    if (idx >= 0) {
      messages.value = messages.value.slice(0, idx + 1);
      messages.value[idx].content = newQuestion;
    }
    const ai = reactive({ role: "assistant", content: "", sources: [] });
    messages.value.push(ai);

    asking.value = true;
    let deletedHint = 0;
    try {
      await postSse(
        "/chat/edit/stream",
        { message_id: item.id, question: newQuestion },
        {
          onEvent(ev) {
            if (ev.type === "meta" && typeof ev.deleted_count === "number") {
              deletedHint = ev.deleted_count;
            }
            if (ev.type === "delta") {
              ai.content += ev.text || "";
            }
            if (ev.type === "done") {
              ai.content = ev.answer || "";
              ai.sources = ev.sources || [];
            }
            if (ev.type === "error") throw new Error(ev.message || "生成失败");
          },
        }
      );
      if (deletedHint) ElMessage.success(`已重答，并清理后续 ${deletedHint} 条消息`);
      else ElMessage.success("已重答");
      await loadHistory(activeSessionId.value);
    } catch (err) {
      await loadHistory(activeSessionId.value);
      ElMessage.error(err?.message || "修改提问失败");
    } finally {
      asking.value = false;
    }
  } catch (e) {
    if (e !== "cancel") ElMessage.error(apiError(e, "修改提问失败"));
  }
};

const onComposerKeydown = (e) => {
  if (e.key !== "Enter") return;
  if (e.shiftKey) return;
  e.preventDefault();
  handleAsk();
};

const handleAsk = async () => {
  if (!question.value.trim()) return;
  if (!activeSessionId.value) return ElMessage.warning("请先创建会话");
  const q = question.value.trim();
  messages.value.push({ role: "user", content: q, sources: [] });
  const ai = reactive({ role: "assistant", content: "", sources: [] });
  messages.value.push(ai);
  question.value = "";
  asking.value = true;
  try {
    await postSse(
      "/chat/ask/stream",
      { session_id: activeSessionId.value, question: q },
      {
        onEvent(ev) {
          if (ev.type === "delta") {
            ai.content += ev.text || "";
          }
          if (ev.type === "done") {
            ai.content = ev.answer || "";
            ai.sources = ev.sources || [];
          }
          if (ev.type === "error") throw new Error(ev.message || "生成失败");
        },
      }
    );
    await loadHistory(activeSessionId.value);
  } catch (e) {
    messages.value.pop();
    messages.value.pop();
    ElMessage.error(apiError(e, "提问失败"));
  } finally {
    asking.value = false;
  }
};

const bootstrapUser = async () => {
  await loadSessions();
  if (!activeSessionId.value) await handleCreateSession();
  else await loadHistory(activeSessionId.value);
};

const bootstrapAdmin = async () => {
  await loadDocs();
};

const handleLogin = async () => {
  authLoading.value = true;
  try {
    const res = await login(authForm.value);
    localStorage.setItem("token", res.data.access_token);
    const meRes = await me();
    user.value = meRes.data;
    if (user.value.role === "admin") await bootstrapAdmin();
    else await bootstrapUser();
    authed.value = true;
    ElMessage.success("登录成功");
  } catch (e) {
    localStorage.removeItem("token");
    authed.value = false;
    ElMessage.error(apiError(e, "登录失败"));
  } finally {
    authLoading.value = false;
  }
};

const handleRegisterSubmit = async () => {
  const u = registerForm.value.username.trim();
  const p = registerForm.value.password;
  const p2 = registerForm.value.password2;
  if (u.length < 3) return ElMessage.warning("用户名至少 3 位");
  if (p.length < 6) return ElMessage.warning("密码至少 6 位");
  if (p !== p2) return ElMessage.warning("两次输入的密码不一致");
  authLoading.value = true;
  try {
    const res = await register({ username: u, password: p, role: "user" });
    localStorage.setItem("token", res.data.access_token);
    const meRes = await me();
    user.value = meRes.data;
    await bootstrapUser();
    authed.value = true;
    ElMessage.success("注册成功");
  } catch (e) {
    localStorage.removeItem("token");
    authed.value = false;
    ElMessage.error(apiError(e, "注册失败"));
  } finally {
    authLoading.value = false;
  }
};

const logout = () => {
  localStorage.removeItem("token");
  authed.value = false;
  user.value = { username: "", role: "" };
  messages.value = [];
  sessions.value = [];
  activeSessionId.value = null;
  documents.value = [];
  fileList.value = [];
  selectedFiles.value = [];
};

onMounted(async () => {
  const token = localStorage.getItem("token");
  if (!token) return;
  try {
    const meRes = await me();
    user.value = meRes.data;
    if (user.value.role === "admin") await bootstrapAdmin();
    else await bootstrapUser();
    authed.value = true;
  } catch {
    localStorage.removeItem("token");
    authed.value = false;
  }
});
</script>

<style scoped>
/* ========== 工作台壳层 ========== */
.shell {
  display: flex;
  height: 100%;
  min-height: 100vh;
  box-sizing: border-box;
}

.aside {
  width: 300px;
  flex-shrink: 0;
  padding: 22px 18px;
  background: var(--app-sidebar-dark);
  border-right: 1px solid var(--app-sidebar-border);
  display: flex;
  flex-direction: column;
  gap: 20px;
  box-shadow: 8px 0 32px rgba(0, 0, 0, 0.12);
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-bottom: 4px;
}

.brand-mark {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  background: linear-gradient(135deg, #6366f1, #4f46e5);
  color: #fff;
  font-size: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 8px 24px rgba(79, 70, 229, 0.45);
}

.brand-mark--user {
  background: linear-gradient(135deg, #0ea5e9, #0284c7);
  box-shadow: 0 8px 24px rgba(14, 165, 233, 0.35);
}

.brand-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.brand-title {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: #f8fafc;
}

.brand-sub {
  font-size: 12px;
  color: rgba(248, 250, 252, 0.55);
  font-weight: 500;
}

.profile {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px;
  border-radius: var(--app-radius);
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.profile-avatar {
  background: linear-gradient(135deg, #818cf8, #4f46e5) !important;
  color: #fff !important;
  font-weight: 700;
  font-size: 16px;
}

.profile-avatar--user {
  background: linear-gradient(135deg, #38bdf8, #0ea5e9) !important;
}

.profile-meta {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.profile-name {
  font-size: 14px;
  font-weight: 600;
  color: #f1f5f9;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.profile-role {
  font-size: 11px;
  font-weight: 500;
  color: rgba(226, 232, 240, 0.55);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.profile-out {
  color: #a5b4fc !important;
  font-weight: 500;
}

.panel-block {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
}

.block-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #e2e8f0;
  letter-spacing: 0.02em;
}

.block-desc {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: rgba(148, 163, 184, 0.95);
}

.upload-elegant :deep(.el-upload-dragger) {
  padding: 20px 16px;
  border-radius: var(--app-radius-sm);
  background: rgba(15, 23, 42, 0.35);
  border: 1px dashed rgba(148, 163, 184, 0.35);
  transition: border-color 0.2s, background 0.2s;
}

.upload-elegant :deep(.el-upload-dragger:hover) {
  border-color: rgba(129, 140, 248, 0.7);
  background: rgba(30, 27, 75, 0.45);
}

.upload-inner {
  text-align: center;
}

.upload-icon {
  display: inline-flex;
  width: 40px;
  height: 40px;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: rgba(99, 102, 241, 0.25);
  color: #c7d2fe;
  font-size: 22px;
  font-weight: 300;
  line-height: 1;
  margin-bottom: 8px;
}

.upload-inner p {
  margin: 0;
  font-size: 12px;
  color: #94a3b8;
}

.upload-elegant :deep(.el-upload-list) {
  margin-top: 10px;
  max-height: 120px;
  overflow-y: auto;
}

.upload-elegant :deep(.el-upload-list__item) {
  background: rgba(15, 23, 42, 0.45);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 8px;
  margin-top: 6px;
  color: #e2e8f0;
}

.upload-elegant :deep(.el-upload-list__item-name) {
  color: #cbd5e1;
}

.btn-full {
  width: 100%;
  font-weight: 600;
}

.session-create {
  display: flex;
  gap: 8px;
  align-items: center;
}

.session-create :deep(.el-input__wrapper) {
  background: rgba(15, 23, 42, 0.35);
  box-shadow: none;
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.session-create :deep(.el-input__inner) {
  color: #e2e8f0;
}

.session-scroll {
  flex: 1;
  min-height: 140px;
  max-height: calc(100vh - 320px);
  padding-right: 4px;
}

.session-scroll :deep(.el-scrollbar__wrap) {
  overflow-x: hidden;
}

.session-pill {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  padding: 10px 12px;
  border: 1px solid transparent;
  border-radius: var(--app-radius-sm);
  background: rgba(255, 255, 255, 0.04);
  color: #cbd5e1;
  font-size: 13px;
  cursor: pointer;
  text-align: left;
  font-family: inherit;
  transition: background 0.2s, border-color 0.2s, transform 0.15s;
}

.session-pill:hover {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.06);
}

.session-pill--active {
  background: rgba(14, 165, 233, 0.18);
  border-color: rgba(56, 189, 248, 0.35);
  color: #f0f9ff;
}

.session-pill-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-pill-del {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  font-size: 16px;
  line-height: 1;
  color: rgba(248, 113, 113, 0.85);
  opacity: 0.75;
  transition: opacity 0.15s, background 0.15s;
}

.session-pill-del:hover {
  opacity: 1;
  background: rgba(239, 68, 68, 0.15);
}

/* ========== 主内容区 ========== */
.main {
  flex: 1;
  min-width: 0;
  padding: 24px 28px 28px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.main-chat {
  padding-bottom: 20px;
}

.main-header,
.chat-top {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
}

.main-title {
  margin: 0 0 4px;
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #0f172a;
}

.main-subtitle {
  margin: 0;
  font-size: 14px;
  color: var(--app-text-muted);
  font-weight: 450;
}

.surface {
  flex: 1;
  min-height: 0;
  border-radius: var(--app-radius);
  background: var(--app-surface-solid);
  border: 1px solid var(--app-border);
  box-shadow: var(--app-shadow-md);
  backdrop-filter: blur(12px);
}

.surface-pad {
  padding: 20px 22px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.surface-chat {
  display: flex;
  flex-direction: column;
  min-height: 420px;
  max-height: calc(100vh - 200px);
}

.tip-alert {
  border-radius: var(--app-radius-sm) !important;
}

.tip-alert :deep(.el-alert__title) {
  font-size: 13px;
  line-height: 1.5;
}

.table-wrap {
  flex: 1;
  min-height: 200px;
  border-radius: var(--app-radius-sm);
  overflow: auto;
  border: 1px solid var(--app-border);
}

.docs-table :deep(th.el-table__cell) {
  background: #f8fafc !important;
  color: #475569;
  font-weight: 600;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.docs-table :deep(.el-table__row:hover > td.el-table__cell) {
  background: #f1f5f9 !important;
}

/* ========== 对话区 ========== */
.chat-stream {
  flex: 1;
  overflow-y: auto;
  padding: 20px 22px;
  scroll-behavior: smooth;
}

.chat-empty {
  text-align: center;
  padding: 48px 24px 32px;
  max-width: 360px;
  margin: 0 auto;
}

.chat-empty-icon {
  font-size: 40px;
  margin-bottom: 12px;
  filter: grayscale(0.2);
}

.chat-empty-title {
  margin: 0 0 8px;
  font-size: 17px;
  font-weight: 600;
  color: #334155;
}

.chat-empty-desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: #94a3b8;
}

.msg-row {
  display: flex;
  gap: 12px;
  margin-bottom: 18px;
  align-items: flex-start;
}

.msg-row--user {
  flex-direction: row-reverse;
}

.msg-avatar {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
}

.msg-avatar--user {
  background: linear-gradient(145deg, #6366f1, #4f46e5);
  box-shadow: 0 4px 12px rgba(79, 70, 229, 0.35);
}

.msg-avatar--ai {
  background: linear-gradient(145deg, #334155, #1e293b);
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.2);
}

.msg-stack {
  max-width: min(720px, 100%);
}

.msg-row--user .msg-stack {
  display: flex;
  justify-content: flex-end;
}

.msg-bubble {
  border-radius: 16px;
  padding: 14px 16px;
  line-height: 1.65;
  font-size: 14px;
}

.msg-bubble--user {
  position: relative;
  overflow: visible;
  background: linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%);
  border: 1px solid rgba(99, 102, 241, 0.18);
  color: #1e1b4b;
  border-bottom-right-radius: 4px;
  padding-bottom: 16px;
}

.msg-bubble--ai {
  background: #f8fafc;
  border: 1px solid var(--app-border);
  color: #1e293b;
  border-bottom-left-radius: 4px;
  box-shadow: var(--app-shadow-sm);
}

.msg-content {
  white-space: pre-wrap;
  word-break: break-word;
}

.msg-bubble--user .msg-actions {
  position: absolute;
  left: -4px;
  bottom: -4px;
  display: flex;
  justify-content: flex-start;
  margin: 0;
  pointer-events: auto;
}

.btn-edit-reply {
  width: 22px !important;
  height: 22px !important;
  min-width: 22px !important;
  padding: 0 !important;
  font-weight: 600;
  font-size: 10px;
  border: none;
  color: #fff !important;
  background: linear-gradient(135deg, #6366f1 0%, #4f46e5 55%, #4338ca 100%);
  box-shadow: 0 2px 8px rgba(79, 70, 229, 0.35);
}

.btn-edit-reply:hover {
  filter: brightness(1.06);
}

.btn-edit-reply :deep(.el-button__inner) {
  padding: 0;
  line-height: 1;
}

.btn-edit-reply__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  font-size: 10px;
  opacity: 0.95;
}

.msg-sources {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.src-chip {
  font-size: 11px;
  font-weight: 500;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(79, 70, 229, 0.08);
  color: #4338ca;
  border: 1px solid rgba(79, 70, 229, 0.12);
}

.composer {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  padding: 16px 18px 18px;
  border-top: 1px solid var(--app-border);
  background: linear-gradient(180deg, #fafbfc 0%, #fff 100%);
  border-radius: 0 0 var(--app-radius) var(--app-radius);
}

.composer-input {
  flex: 1;
}

.composer-input :deep(.el-textarea__inner) {
  border-radius: 12px;
  padding: 12px 14px;
  font-size: 14px;
  border: 1px solid var(--app-border);
  box-shadow: none;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.composer-input :deep(.el-textarea__inner:focus) {
  border-color: rgba(79, 70, 229, 0.45);
  box-shadow: 0 0 0 3px var(--app-accent-soft);
}

.composer-send {
  flex-shrink: 0;
  padding: 12px 22px;
  font-weight: 600;
}

/* ========== 登录页 ========== */
.auth-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px 20px;
  position: relative;
  overflow: hidden;
}

.auth-bg {
  position: absolute;
  inset: 0;
  background: var(--app-bg-mesh);
  background-color: #0f172a;
}

.auth-bg::before,
.auth-bg::after {
  content: "";
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.55;
}

.auth-bg::before {
  width: 480px;
  height: 480px;
  background: #4f46e5;
  top: -120px;
  right: -80px;
}

.auth-bg::after {
  width: 400px;
  height: 400px;
  background: #0ea5e9;
  bottom: -100px;
  left: -60px;
}

.auth-card {
  position: relative;
  width: 100%;
  max-width: 420px;
  padding: 36px 32px 32px;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(255, 255, 255, 0.65);
  box-shadow: 0 24px 80px -20px rgba(0, 0, 0, 0.35), 0 0 0 1px rgba(255, 255, 255, 0.5) inset;
  backdrop-filter: blur(20px);
}

.auth-card-head {
  text-align: center;
  margin-bottom: 8px;
}

.auth-logo {
  width: 48px;
  height: 48px;
  margin: 0 auto 14px;
  border-radius: 14px;
  background: linear-gradient(135deg, #6366f1, #4338ca);
  color: #fff;
  font-size: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 12px 28px rgba(67, 56, 202, 0.45);
}

.auth-title {
  margin: 0 0 6px;
  font-size: 22px;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.02em;
}

.auth-tagline {
  margin: 0;
  font-size: 13px;
  color: #64748b;
}

.auth-tabs :deep(.el-tabs__nav-wrap::after) {
  height: 1px;
  background: rgba(15, 23, 42, 0.08);
}

.auth-tabs :deep(.el-tabs__item) {
  font-weight: 600;
  font-size: 14px;
}

.auth-tabs :deep(.el-tabs__active-bar) {
  height: 3px;
  border-radius: 3px 3px 0 0;
}

.auth-fields {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding-top: 8px;
}

.auth-submit {
  width: 100%;
  margin-top: 4px;
  font-weight: 600;
}
</style>
