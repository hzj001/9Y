import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config import settings
from cursor_client import CursorClient
from database import SessionLocal, get_db, init_db
from models import AgentRecord, User

cursor = CursorClient()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Cursor Quota Proxy",
    description="用您的 Cursor 账号 API Key 为其他用户提供带配额限制的 Cloud Agent 访问",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------- Schemas ----------


class CreateUserRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    token_quota: int = Field(..., ge=0, description="允许使用的 token 总量上限")


class UpdateQuotaRequest(BaseModel):
    token_quota: int = Field(..., ge=0)


class UserResponse(BaseModel):
    id: int
    name: str
    api_key: str
    token_quota: int
    tokens_used: int
    tokens_remaining: int
    is_active: bool


class CreateAgentRequest(BaseModel):
    prompt: dict
    model: dict | None = None
    name: str | None = None
    repos: list[dict] | None = None
    env: dict | None = None
    autoCreatePR: bool | None = None
    mode: str | None = None


class FollowupRequest(BaseModel):
    prompt: dict
    model: dict | None = None


# ---------- Auth helpers ----------


def verify_admin(x_admin_secret: str = Header(...)):
    if x_admin_secret != settings.admin_secret:
        raise HTTPException(status_code=401, detail="无效的管理员密钥")


def get_user_by_api_key(api_key: str, db: Session) -> User:
    user = db.query(User).filter(User.api_key == api_key, User.is_active.is_(True)).first()
    if not user:
        raise HTTPException(status_code=401, detail="无效的 API Key")
    return user


def verify_user(authorization: str = Header(...), db: Session = Depends(get_db)) -> User:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="请使用 Bearer Token 认证")
    api_key = authorization.removeprefix("Bearer ").strip()
    return get_user_by_api_key(api_key, db)


def check_quota(user: User, estimated_tokens: int = 0):
    remaining = user.token_quota - user.tokens_used
    if remaining <= 0:
        raise HTTPException(
            status_code=402,
            detail=f"配额已用尽（已用 {user.tokens_used}/{user.token_quota} tokens）",
        )
    if estimated_tokens and remaining < estimated_tokens:
        raise HTTPException(
            status_code=402,
            detail=f"剩余配额不足（剩余 {remaining} tokens，需要约 {estimated_tokens}）",
        )


async def sync_agent_usage(agent_record_id: int, retries: int = 10):
    """轮询 Cursor API，将 agent 的 token 用量计入用户配额。"""
    db = SessionLocal()
    try:
        agent_record = db.query(AgentRecord).filter(AgentRecord.id == agent_record_id).first()
        if not agent_record:
            return

        previous_charged = agent_record.tokens_charged

        for _ in range(retries):
            await asyncio.sleep(3)
            try:
                usage_data = await cursor.get_agent_usage(
                    agent_record.agent_id, agent_record.run_id
                )
            except Exception:
                continue

            total = usage_data.get("totalUsage", {}).get("totalTokens", 0)
            if total <= previous_charged:
                try:
                    agent_data = await cursor.get_agent(agent_record.agent_id)
                    status = agent_data.get("agent", {}).get("status", "")
                    if status in ("COMPLETED", "FAILED", "CANCELLED"):
                        agent_record.status = status.lower()
                        db.commit()
                        break
                except Exception:
                    pass
                continue

            delta = total - previous_charged
            user = db.query(User).filter(User.id == agent_record.user_id).with_for_update().first()
            if not user:
                break

            user.tokens_used += delta
            agent_record.tokens_charged = total
            agent_record.status = "active"
            db.commit()
            previous_charged = total

            try:
                agent_data = await cursor.get_agent(agent_record.agent_id)
                status = agent_data.get("agent", {}).get("status", "")
                if status in ("COMPLETED", "FAILED", "CANCELLED"):
                    agent_record.status = status.lower()
                    db.commit()
                    break
            except Exception:
                pass
    finally:
        db.close()


def user_to_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        name=user.name,
        api_key=user.api_key,
        token_quota=user.token_quota,
        tokens_used=user.tokens_used,
        tokens_remaining=max(0, user.token_quota - user.tokens_used),
        is_active=user.is_active,
    )


# ---------- Admin routes ----------


@app.post("/admin/users", response_model=UserResponse, dependencies=[Depends(verify_admin)])
def create_user(body: CreateUserRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.name == body.name).first():
        raise HTTPException(status_code=409, detail="用户名已存在")

    user = User(name=body.name, api_key=User.generate_api_key(), token_quota=body.token_quota)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user_to_response(user)


@app.get("/admin/users", response_model=list[UserResponse], dependencies=[Depends(verify_admin)])
def list_users(db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id).all()
    return [user_to_response(u) for u in users]


@app.patch(
    "/admin/users/{user_id}/quota",
    response_model=UserResponse,
    dependencies=[Depends(verify_admin)],
)
def update_quota(user_id: int, body: UpdateQuotaRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.token_quota = body.token_quota
    db.commit()
    db.refresh(user)
    return user_to_response(user)


@app.delete("/admin/users/{user_id}", dependencies=[Depends(verify_admin)])
def deactivate_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.is_active = False
    db.commit()
    return {"message": f"用户 {user.name} 已禁用"}


@app.post("/admin/users/{user_id}/reset-usage", dependencies=[Depends(verify_admin)])
def reset_usage(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.tokens_used = 0
    db.commit()
    return {"message": f"用户 {user.name} 用量已重置为 0"}


# ---------- User routes (proxy to Cursor) ----------


@app.get("/v1/me")
async def me(user: User = Depends(verify_user)):
    check_quota(user)
    data = await cursor.get_me()
    return {
        **data,
        "quota": {
            "token_quota": user.token_quota,
            "tokens_used": user.tokens_used,
            "tokens_remaining": max(0, user.token_quota - user.tokens_used),
        },
    }


@app.get("/v1/quota")
def get_quota(user: User = Depends(verify_user)):
    return {
        "name": user.name,
        "token_quota": user.token_quota,
        "tokens_used": user.tokens_used,
        "tokens_remaining": max(0, user.token_quota - user.tokens_used),
    }


@app.post("/v1/agents")
async def create_agent(
    body: CreateAgentRequest,
    user: User = Depends(verify_user),
    db: Session = Depends(get_db),
):
    check_quota(user)
    payload = body.model_dump(exclude_none=True)

    try:
        result = await cursor.create_agent(payload)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Cursor API 调用失败: {exc}") from exc

    agent_id = result.get("agent", {}).get("id") or result.get("id")
    run_id = result.get("run", {}).get("id")

    if agent_id:
        record = AgentRecord(user_id=user.id, agent_id=agent_id, run_id=run_id, status="pending")
        db.add(record)
        db.commit()
        db.refresh(record)
        asyncio.create_task(sync_agent_usage(record.id))

    return {
        **result,
        "quota": {
            "tokens_remaining": max(0, user.token_quota - user.tokens_used),
        },
    }


@app.get("/v1/agents/{agent_id}")
async def get_agent(agent_id: str, user: User = Depends(verify_user), db: Session = Depends(get_db)):
    record = (
        db.query(AgentRecord)
        .filter(AgentRecord.agent_id == agent_id, AgentRecord.user_id == user.id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Agent 不存在或无权访问")

    return await cursor.get_agent(agent_id)


@app.get("/v1/agents/{agent_id}/usage")
async def get_agent_usage(
    agent_id: str,
    runId: str | None = None,
    user: User = Depends(verify_user),
    db: Session = Depends(get_db),
):
    record = (
        db.query(AgentRecord)
        .filter(AgentRecord.agent_id == agent_id, AgentRecord.user_id == user.id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Agent 不存在或无权访问")

    usage = await cursor.get_agent_usage(agent_id, runId)
    return {
        **usage,
        "quota": {
            "token_quota": user.token_quota,
            "tokens_used": user.tokens_used,
            "tokens_remaining": max(0, user.token_quota - user.tokens_used),
        },
    }


@app.post("/v1/agents/{agent_id}/followup")
async def followup_agent(
    agent_id: str,
    body: FollowupRequest,
    user: User = Depends(verify_user),
    db: Session = Depends(get_db),
):
    check_quota(user)

    record = (
        db.query(AgentRecord)
        .filter(AgentRecord.agent_id == agent_id, AgentRecord.user_id == user.id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Agent 不存在或无权访问")

    payload = body.model_dump(exclude_none=True)
    result = await cursor.followup_agent(agent_id, payload)
    run_id = result.get("run", {}).get("id")

    if run_id:
        new_record = AgentRecord(
            user_id=user.id, agent_id=agent_id, run_id=run_id, status="pending"
        )
        db.add(new_record)
        db.commit()
        db.refresh(new_record)
        asyncio.create_task(sync_agent_usage(new_record.id))

    return result


@app.get("/v1/agents")
async def list_agents(
    limit: int = 20,
    user: User = Depends(verify_user),
    db: Session = Depends(get_db),
):
    records = (
        db.query(AgentRecord)
        .filter(AgentRecord.user_id == user.id)
        .order_by(AgentRecord.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "agents": [
            {
                "agent_id": r.agent_id,
                "run_id": r.run_id,
                "tokens_charged": r.tokens_charged,
                "status": r.status,
                "created_at": r.created_at.isoformat(),
            }
            for r in records
        ]
    }


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=True)
