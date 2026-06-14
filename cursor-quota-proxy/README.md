# Cursor Quota Proxy

用您的 Cursor 账号 **Admin API Key** 搭建一个中间层服务，为其他用户分配独立的访问密钥和 **Token 配额**，所有 Cloud Agent 请求通过您的账号发起，用量从您的 Cursor 账户扣费。

## 重要说明

### Cursor 官方能力

| 方案 | 适用场景 | 说明 |
|------|----------|------|
| **Enterprise Admin API** | 企业团队 | 官方支持按成员设置 `$` 消费上限（`/teams/user-spend-limit`），需 Enterprise 计划 |
| **本代理服务** | 个人 Ultra/Pro 账号 | 自行实现 Token 配额控制，非 Cursor 官方功能 |

### 风险与限制

1. **所有费用从您的账号扣除** — 代理只控制「谁能用、用多少」，不能创造额外额度
2. **Admin Key 权限很高** — 必须只放在服务端，绝不能暴露给前端或第三方
3. **Token 计量为近似值** — 基于 Cloud Agents API 的 `/v1/agents/{id}/usage` 接口异步同步
4. **服务条款** — 请确认 Cursor 服务条款是否允许此类代理共享；企业场景建议使用官方 Teams/Enterprise

## 快速开始

### 1. 安装依赖

```bash
cd cursor-quota-proxy
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入您的 CURSOR_API_KEY 和管理员密钥
```

从 [Cursor Dashboard → API Keys](https://cursor.com/dashboard/api) 复制您的 Admin Key（格式 `crsr_...`）。

### 3. 启动服务

```bash
python main.py
# 或
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

### 4. 创建用户并分配配额（管理员操作）

```bash
# 创建一个用户，分配 500,000 tokens 配额
curl -X POST http://localhost:8080/admin/users \
  -H "X-Admin-Secret: your-admin-secret" \
  -H "Content-Type: application/json" \
  -d '{"name": "张三", "token_quota": 500000}'
```

响应中会返回该用户的独立 `api_key`（格式 `cqk_...`），将此 Key 交给对方使用。

### 5. 用户使用代理调用 Cloud Agent

```bash
# 查看剩余配额
curl http://localhost:8080/v1/quota \
  -H "Authorization: Bearer cqk_用户密钥"

# 创建 Cloud Agent
curl -X POST http://localhost:8080/v1/agents \
  -H "Authorization: Bearer cqk_用户密钥" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": {"text": "为 README 添加安装说明"},
    "repos": [{"url": "https://github.com/your-org/your-repo", "startingRef": "main"}]
  }'
```

## API 概览

### 管理员接口（需 `X-Admin-Secret` 请求头）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/admin/users` | 创建用户并设置 Token 配额 |
| GET | `/admin/users` | 列出所有用户及用量 |
| PATCH | `/admin/users/{id}/quota` | 修改用户配额 |
| POST | `/admin/users/{id}/reset-usage` | 重置已用量为 0 |
| DELETE | `/admin/users/{id}` | 禁用用户 |

### 用户接口（需 `Authorization: Bearer cqk_...`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v1/quota` | 查看剩余配额 |
| POST | `/v1/agents` | 创建 Cloud Agent（代理至 Cursor API） |
| GET | `/v1/agents/{id}` | 查询 Agent 状态 |
| GET | `/v1/agents/{id}/usage` | 查询 Token 用量 |
| POST | `/v1/agents/{id}/followup` | 继续对话 |
| GET | `/v1/agents` | 列出该用户创建的 Agent |

## 架构

```
┌─────────────┐     cqk_用户Key      ┌──────────────────┐    crsr_AdminKey    ┌─────────────┐
│  第三方用户  │ ──────────────────► │  Quota Proxy     │ ──────────────────► │ Cursor API  │
│             │ ◄────────────────── │  (本服务)         │ ◄────────────────── │             │
└─────────────┘   配额检查 + 转发    └──────────────────┘   实际扣费           └─────────────┘
                                           │
                                           ▼
                                    SQLite 用户/用量 DB
```

## 生产部署建议

- 使用 HTTPS（Nginx / Caddy 反向代理）
- 将 `ADMIN_SECRET` 和 `CURSOR_API_KEY` 存入密钥管理服务
- 考虑改用 PostgreSQL 替代 SQLite
- 添加请求速率限制（如 slowapi）
- 定期备份数据库

## 如果您是企业用户

若您有 **Enterprise** 计划，更推荐使用 Cursor 官方方案：

- [Service Accounts](https://cursor.com/docs/account/enterprise/service-accounts) — 为自动化任务创建独立服务账号
- [Admin API - Set User Spend Limit](https://cursor.com/docs/account/teams/admin-api) — 按成员设置美元消费上限
- [Spending Dashboard](https://cursor.com/docs/account/teams/dashboard) — 可视化监控团队用量
