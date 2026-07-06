from pydantic import BaseModel

class RegisterRequest(BaseModel):
    fullname: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str