from fastapi import APIRouter, Depends
from backend.dependencies import get_user_repository, require_role
from infrastructure.repositories.lmdb_repositories import LMDBUserRepository

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

@router.get("/users", summary="All Users")
def list_users(
    u: dict = Depends(require_role("admin")),
    user_repository: LMDBUserRepository = Depends(get_user_repository)
):
    users = user_repository.load_all_users()
    return {"users": [
        {k: v for k, v in user.to_dict().items() if k not in ("password_hash", "totp_secret")}
        for user in users
    ]}

