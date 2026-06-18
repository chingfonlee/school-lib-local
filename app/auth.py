from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse


def require_auth(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        if request.headers.get("accept", "").startswith("application/json"):
            raise HTTPException(status_code=401, detail="未登入")
        raise HTTPException(status_code=401, detail="未登入")
    return user_id
