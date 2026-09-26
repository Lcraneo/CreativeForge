Phase 11：CreativeForge Backend 第一版实现
先搭建一个真实可扩展的后端骨架，不要写一次性 Demo。
第一阶段完成：
用户 Prompt

↓

FastAPI API

↓

Agent Planner

↓

Tool Router

↓

CreativeAsset 创建

↓

PostgreSQL 持久化

↓

返回 Task 状态


Phase 11.1 项目初始化
最终目录：
CreativeForge/

├── backend/

│
├── app/

│   ├── main.py
│   │
│   ├── api/
│   │   ├── asset.py
│   │   └── task.py
│   │
│   ├── core/
│   │   ├── config.py
│   │   └── database.py
│   │
│   ├── models/
│   │   ├── asset.py
│   │   └── task.py
│   │
│   ├── schemas/
│   │   ├── asset.py
│   │   └── task.py
│   │
│   ├── agent/
│   │   ├── planner.py
│   │   └── router.py
│   │
│   ├── tools/
│   │   ├── base.py
│   │   └── registry.py
│   │
│   └── services/
│       └── asset_service.py
│
├── requirements.txt
└── docker-compose.yml


Phase 11.2 技术确定
Backend
FastAPI
原因：
● 异步支持
● AI生态兼容
● WebSocket方便后续Agent流式输出

ORM
使用：
SQLAlchemy 2.0
不用：
SQLModel
原因：
后期复杂关系：
Asset
↓
Version
↓
Animation
↓
Export
SQLAlchemy扩展性更好。

数据校验
Pydantic v2

数据库
PostgreSQL

Phase 11.3 requirements.txt
fastapi==0.115.6
uvicorn[standard]==0.34.0

sqlalchemy==2.0.36
asyncpg==0.30.0

pydantic==2.10.4
pydantic-settings==2.7.0

python-dotenv==1.0.1

langgraph==0.2.60
langchain-core==0.3.28

alembic==1.14.0

Phase 11.4 配置模块
app/core/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    DATABASE_URL: str = (
        "postgresql+asyncpg://"
        "postgres:postgres@localhost:5432/creativeforge"
    )


    class Config:
        env_file = ".env"


settings = Settings()


Phase 11.5 数据库连接
app/core/database.py
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker
)

from app.core.config import settings


engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False
)


AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False
)


async def get_db():

    async with AsyncSessionLocal() as session:
        yield session


Phase 11.6 数据模型设计
Asset 表
对应：
CreativeAsset Contract。
数据库：
asset

id

project_id

name

type

status

metadata

created_at


app/models/asset.py
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import (
    Column,
    String,
    JSON,
    DateTime
)

from datetime import datetime


class Base(DeclarativeBase):
    pass



class Asset(Base):

    __tablename__ = "assets"


    id = Column(
        String,
        primary_key=True
    )


    project_id = Column(
        String,
        nullable=False
    )


    name = Column(
        String,
        nullable=False
    )


    asset_type = Column(
        String,
        default="character"
    )


    status = Column(
        String,
        default="created"
    )


    metadata_json = Column(
        JSON,
        default={}
    )


    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )


Task表
Agent执行需要。
app/models/task.py
from sqlalchemy import (
    Column,
    String,
    JSON,
    DateTime
)

from datetime import datetime

from app.models.asset import Base



class Task(Base):

    __tablename__="tasks"


    id = Column(
        String,
        primary_key=True
    )


    goal = Column(
        String,
        nullable=False
    )


    status = Column(
        String,
        default="pending"
    )


    plan = Column(
        JSON
    )


    result = Column(
        JSON
    )


    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )


Phase 11.7 Agent Planner
现在先实现基础版本。
目标：
输入：
创建一个机械猫战士
输出：
{
tasks:[
"generate",
"structure",
"dna",
"export"
]
}


app/agent/planner.py
class Planner:


    def create_plan(
        self,
        goal:str
    ):


        tasks=[]


        if "创建" in goal or "生成" in goal:

            tasks.extend(
                [
                    "generate_asset",
                    "structure_asset",
                    "create_dna",
                    "export_asset"
                ]
            )


        return {
            "goal":goal,
            "tasks":tasks
        }



planner = Planner()


Phase 11.8 Tool Registry
核心：
所有能力插件化。
以后：
加入：
● Windup
● SAM2
● MotionAlign
只需要注册。

tools/base.py
from abc import ABC, abstractmethod



class BaseTool(ABC):


    name:str


    @abstractmethod
    async def run(
        self,
        params:dict
    ):
        pass


tools/registry.py
class ToolRegistry:


    def __init__(self):

        self.tools={}



    def register(
        self,
        tool
    ):

        self.tools[
            tool.name
        ] = tool



    def get(
        self,
        name
    ):

        return self.tools.get(name)



registry = ToolRegistry()


Phase 11.9 第一个 Tool
模拟：
Generate Asset。
以后替换 Windup。
tools/generate.py
from app.tools.base import BaseTool


class GenerateAssetTool(
    BaseTool
):


    name="generate_asset"


    async def run(
        self,
        params
    ):

        return {

            "image":
            "generated_character.png",

            "style":
            "anime"

        }


注册：
from app.tools.registry import registry
from app.tools.generate import GenerateAssetTool


registry.register(
    GenerateAssetTool()
)


Phase 11.10 Service层
负责串联：
API
↓
Agent
↓
Tool

services/asset_service.py
import uuid

from app.agent.planner import planner
from app.tools.registry import registry



async def create_asset(
    goal:str
):


    plan = planner.create_plan(
        goal
    )


    results={}


    for task in plan["tasks"]:

        tool = registry.get(
            task
        )


        if tool:

            result = await tool.run(
                {
                    "goal":goal
                }
            )

            results[task]=result



    return {

        "task_id":
        str(uuid.uuid4()),


        "plan":
        plan,


        "result":
        results

    }


Phase 11.11 API
api/asset.py
from fastapi import APIRouter

from app.services.asset_service import create_asset


router = APIRouter()



@router.post(
    "/create"
)
async def create(
    data:dict
):


    result = await create_asset(
        data["prompt"]
    )


    return result


Phase 11.12 main.py
from fastapi import FastAPI

from app.api.asset import router


app = FastAPI(
    title="CreativeForge API"
)



app.include_router(
    router,
    prefix="/api/v1/assets"
)


@app.get("/health")
async def health():

    return {
        "status":"ok"
    }


现在完成后的调用
请求：
POST

/api/v1/assets/create
Body:
{
"prompt":
"创建一个机械猫战士"
}

返回：
{
"task_id":
"xxx",


"plan":
{

"tasks":[

"generate_asset",

"structure_asset",

"create_dna",

"export_asset"

]

},


"result":

{

"generate_asset":

{

"image":
"generated_character.png"

}

}

}

