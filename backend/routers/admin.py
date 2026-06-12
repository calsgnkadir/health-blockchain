from fastapi import APIRouter, HTTPException, Depends
from backend.dependencies import user_repository, command_handler, require_role
from backend.schemas.requests import UserCreate
from core.cqrs.commands import CreateUserCommand

router = APIRouter(prefix="/api/admin", tags=["admin"])

@router.get("/users", summary="All Users")
def list_users(u: dict = Depends(require_role("admin"))):
    users = user_repository.load_all_users()
    return {"users": [
        {k: v for k, v in user.to_dict().items() if k not in ("password_hash", "totp_secret")}
        for user in users
    ]}

@router.post("/users", summary="Create New User")
def create_user(data: UserCreate, u: dict = Depends(require_role("admin"))):
    if user_repository.user_exists(data.username):
        raise HTTPException(409, f"Username already exists: {data.username}")

    cmd = CreateUserCommand(
        username=data.username,
        password=data.password,
        role=data.role,
        full_name=data.full_name,
        patient_id=data.patient_id,
        specialty=data.specialty,
        institution=data.institution,
        creator_username=u["username"]
    )
    new_user = command_handler.handle_create_user(cmd)

    return {"success": True, "user_id": new_user.id}
