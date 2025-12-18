import os
from jose import jwt, JWTError
from typing import Dict, Any
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from datetime import datetime, timedelta
from schema import schemas
from typing import Optional

SECRET_KEY = os.getenv("SECRET_KEY", "-dt8lK9P8ULpvQQ-GDm5EQoUSkbF-CabowHCUUepbGMGGs8p6kZIUEljfS_57M13IZVjz0jG8H9-Y4GwuWT7Xw")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/exam-login")

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Generates a JWT token containing student and schedule IDs."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_active_student(token: str = Depends(oauth2_scheme)) -> schemas.TokenData:
    """
    Decodes the JWT token, validates its signature and expiration, 
    and returns the student/class information.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        student_id: int = payload.get("student_id")
        class_id: int = payload.get("class_id")
        
        if student_id is None or class_id is None:
            raise credentials_exception
            
        token_data = schemas.TokenData(
            student_id=student_id, 
            class_id=class_id, 
            sub=payload.get("sub"),
            schedule_id=payload.get("schedule_id")
        )
        
    except JWTError:
        raise credentials_exception
        
    return token_data

async def get_current_admin_user():
    return {"user_id": 1, "role": "admin"}





