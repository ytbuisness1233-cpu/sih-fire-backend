from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import anyio
from .. import models, schemas, utils, database

router = APIRouter(prefix="/users", tags=['Users'])

@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.UserOut)
async def create_user(user: schemas.UserCreate, db: AsyncSession = Depends(database.get_db)):
    result = await db.execute(select(models.User).where(models.User.email == user.email))
    existing_user = result.scalars().first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
        
    user_data = user.model_dump()
    # SECURITY HARDENING: Overwrite any incoming role parameter to lock public access out completely
    user_data["role"] = models.RoleEnum.user
    
    hashed_password = await anyio.to_thread.run_sync(utils.hash, user_data["password"])
    user_data["password"] = hashed_password
    
    new_user = models.User(**user_data)
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user
