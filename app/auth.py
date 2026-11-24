from fastapi import HTTPException, Request


def require_auth(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="未登入")
    return user_id
