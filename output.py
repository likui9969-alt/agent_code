# main.py
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from typing import List, Optional

from .database import get_async_session
from .models import Base
from .schemas import ItemBase, ItemCreate, ItemUpdate, ItemOut
from .crud import (
    create_item,
    get_item,
    get_items,
    update_item,
    delete_item,
)

app = FastAPI(
    title="Item CRUD Microservice",
    description="A FastAPI-based CRUD microservice for managing items.",
    version="0.1.0",
)

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/items/", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
async def create_new_item(
    item_in: ItemCreate,
    db: AsyncSession = Depends(get_async_session),
):
    """Create a new item."""
    return await create_item(db, item_in)

@app.get("/items/{item_id}", response_model=ItemOut)
async def read_item(
    item_id: int,
    db: AsyncSession = Depends(get_async_session),
):
    """Retrieve an item by ID."""
    return await get_item(db, item_id)

@app.get("/items/", response_model=List[ItemOut])
async def read_items(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_async_session),
):
    """Retrieve a list of items with pagination."""
    if skip < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="skip must be >= 0"
        )
    if limit <= 0 or limit > 1000:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="limit must be between 1 and 1000"
        )
    return await get_items(db, skip=skip, limit=limit)

@app.patch("/items/{item_id}", response_model=ItemOut)
async def update_existing_item(
    item_id: int,
    item_in: ItemUpdate,
    db: AsyncSession = Depends(get_async_session),
):
    """Partially update an item by ID."""
    return await update_item(db, item_id, item_in)

@app.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_item(
    item_id: int,
    db: AsyncSession = Depends(get_async_session),
):
    """Delete an item by ID."""
    await delete_item(db, item_id)
    return JSONResponse(content=None, status_code=status.HTTP_204_NO_CONTENT)


# database.py
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from typing import AsyncGenerator

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./test.db")

# For SQLite, enable foreign keys and use appropriate options
if DATABASE_URL.startswith("sqlite"):
    DATABASE_URL += "?_pragma=foreign_keys=on"
    engine_kwargs = {"echo": False, "poolclass": NullPool}
else:
    engine_kwargs = {"echo": False}

engine = create_async_engine(
    DATABASE_URL,
    future=True,
    **engine_kwargs,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def init_db():
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that yields an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# models.py
from sqlalchemy import Integer, String, Boolean, DateTime
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from datetime import datetime

class Base(AsyncAttrs, DeclarativeBase):
    pass

class Item(Base):
    __tablename__ = "items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# schemas.py
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime

class ItemBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    is_active: bool = True

    @field_validator('name')
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('name cannot be empty or whitespace-only')
        return v.strip()

class ItemCreate(ItemBase):
    pass

class ItemUpdate(ItemBase):
    name: Optional[str] = Field(None, min_length=1, max_length=100)

class ItemOut(ItemBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# crud.py
from sqlalchemy import select, update, delete
from sqlalchemy.exc import NoResultFound, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
from typing import List
from .models import Item
from .schemas import ItemCreate, ItemUpdate

async def create_item(db: AsyncSession, item_in: ItemCreate) -> Item:
    """Create a new item in the database."""
    db_item = Item(**item_in.model_dump())
    db.add(db_item)
    try:
        await db.commit()
        await db.refresh(db_item)
        return db_item
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Database integrity error: {str(e)}"
        )

async def get_item(db: AsyncSession, item_id: int) -> Item:
    """Retrieve an item by ID; raises 404 if not found."""
    stmt = select(Item).where(Item.id == item_id)
    result = await db.execute(stmt)
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found"
        )
    return item

async def get_items(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[Item]:
    """Retrieve a paginated list of items."""
    stmt = select(Item).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()

async def update_item(db: AsyncSession, item_id: int, item_in: ItemUpdate) -> Item:
    """Partially update an item by ID."""
    update_data = item_in.model_dump(exclude_unset=True)
    if not update_data:
        # If no fields provided, return existing item
        return await get_item(db, item_id)
    
    stmt = update(Item).where(Item.id == item_id).values(**update_data)
    result = await db.execute(stmt)
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found"
        )
    await db.commit()
    return await get_item(db, item_id)

async def delete_item(db: AsyncSession, item_id: int) -> None:
    """Delete an item by ID."""
    stmt = delete(Item).where(Item.id == item_id)
    result = await db.execute(stmt)
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found"
        )
    await db.commit()


# __init__.py
# Package initialization to allow relative imports

# test_main.py
import pytest
import asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from unittest.mock import AsyncMock, patch

from main import app
from database import AsyncSessionLocal, engine
from models import Base
from schemas import ItemCreate, ItemUpdate

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session", autouse=True)
async def setup_test_db():
    # Use in-memory SQLite for tests
    test_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield test_engine
    await test_engine.dispose()

@pytest.fixture
def client(setup_test_db):
    app.dependency_overrides.clear()
    
    async def override_get_async_session():
        async with AsyncSessionLocal() as session:
            yield session
    
    app.dependency_overrides[get_async_session] = override_get_async_session
    return AsyncClient(app=app, base_url="http://test")

@pytest.mark.asyncio
async def test_health_check(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data

@pytest.mark.asyncio
async def test_create_item(client):
    item_data = {"name": "Test Item", "description": "A test item"}
    response = await client.post("/items/", json=item_data)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Item"
    assert data["id"] > 0

@pytest.mark.asyncio
async def test_get_item(client):
    # First create an item
    item_data = {"name": "Get Test"}
    create_resp = await client.post("/items/", json=item_data)
    item_id = create_resp.json()["id"]
    
    # Then retrieve it
    response = await client.get(f"/items/{item_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == item_id
    assert data["name"] == "Get Test"

@pytest.mark.asyncio
async def test_get_nonexistent_item(client):
    response = await client.get("/items/999999")
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_list_items(client):
    # Create two items
    await client.post("/items/", json={"name": "Item 1"})
    await client.post("/items/", json={"name": "Item 2"})
    
    response = await client.get("/items/?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2

@pytest.mark.asyncio
async def test_update_item(client):
    # Create item
    create_resp = await client.post("/items/", json={"name": "Original"})
    item_id = create_resp.json()["id"]
    
    # Update it
    update_data = {"name": "Updated", "is_active": False}
    response = await client.patch(f"/items/{item_id}", json=update_data)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated"
    assert data["is_active"] is False

@pytest.mark.asyncio
async def test_delete_item(client):
    # Create item
    create_resp = await client.post("/items/", json={"name": "To Delete"})
    item_id = create_resp.json()["id"]
    
    # Delete it
    response = await client.delete(f"/items/{item_id}")
    assert response.status_code == 204
    
    # Verify it's gone
    get_resp = await client.get(f"/items/{item_id}")
    assert get_resp.status_code == 404

@pytest.mark.asyncio
async def test_validation_errors(client):
    # Empty name
    response = await client.post("/items/", json={"name": ""})
    assert response.status_code == 422
    
    # Too long name
    long_name = "a" * 101
    response = await client.post("/items/", json={"name": long_name})
    assert response.status_code == 422


if __name__ == "__main__":
    # Run basic smoke test
    import asyncio
    from httpx import AsyncClient

    async def smoke_test():
        async with AsyncClient(app=app, base_url="http://test") as ac:
            # Health check
            response = await ac.get("/health")
            print("Health check:", response.status_code, response.json())

            # Create item
            response = await ac.post("/items/", json={"name": "Smoke Test"})
            print("Create item:", response.status_code, response.json())

            # List items
            response = await ac.get("/items/")
            print("List items:", response.status_code, len(response.json()))

    asyncio.run(smoke_test())
