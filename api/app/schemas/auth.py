from pydantic import BaseModel, EmailStr


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    school_id: int | None = None
    is_admin: bool

    class Config:
        from_attributes = True
