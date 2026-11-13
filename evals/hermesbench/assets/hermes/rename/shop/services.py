from .models import get_usr


def discount_for(user_id):
    user = get_usr(user_id)
    if user is None:
        return 0.0
    return {"gold": 0.2, "silver": 0.1}.get(user["tier"], 0.0)
