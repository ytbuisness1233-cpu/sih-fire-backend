from fastapi import APIRouter, Depends, status, HTTPException
from fastapi.security.oauth2 import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import anyio  # FastAPI's built-in async worker pool engine
from .. import database, schemas, models, utils, oauth2

router = APIRouter(tags=['Authentication'])

@router.post('/login', response_model=schemas.Token)
async def login(
    user_credentials: OAuth2PasswordRequestForm = Depends(), 
    db: AsyncSession = Depends(database.get_db)
):
    # 1. Fetch user securely using the async engine execution
    result = await db.execute(select(models.User).where(models.User.email == user_credentials.username))
    user = result.scalars().first()
    
    # 2. Defensive check to prevent immediate short-circuit timing attacks
    if not user:
        # Run a fake verification calculation to match server processing latency
        await anyio.to_thread.run_sync(utils.verify, user_credentials.password, "$2b$12$FakeHashToPreventTimingAttacks...")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Invalid Credentials"
        )
    
    # 3. Offload the heavy cryptographic verification to a background worker thread
    is_password_correct = await anyio.to_thread.run_sync(
        utils.verify, 
        user_credentials.password, 
        user.password
    )
    
    if not is_password_correct:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Invalid Credentials"
        )
    
    # 4. Explicitly cast the primary key id to a string for JWT compatibility layers
    access_token = oauth2.create_access_token(data={"user_id": str(user.id)})
    
    return {"access_token": access_token, "token_type": "bearer"}
