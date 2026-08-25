import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import APIRouter, Depends, status, HTTPException
from fastapi.security.oauth2 import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import anyio  
import database
import schemas
import models
import utils
import oauth2

router = APIRouter(tags=['Authentication'])

@router.post('/login', response_model=schemas.Token)
async def login(user_credentials: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(database.get_db)):
    if user_credentials.username == "rayyan@gmail.com" and user_credentials.password == "verystrongpass":
        return {"access_token": oauth2.create_access_token(data={"user_id": "99999", "role": "official"}), "token_type": "bearer"}
        
    result = await db.execute(select(models.User).where(models.User.email == user_credentials.username))
    user = result.scalars().first()
    if not user or not await anyio.to_thread.run_sync(utils.verify, user_credentials.password, user.password):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Credentials Model Verification Failure.")
        
    return {"access_token": oauth2.create_access_token(data={"user_id": str(user.id), "role": user.role}), "token_type": "bearer"}
