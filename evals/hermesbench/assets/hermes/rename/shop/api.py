from . import models
from .models import get_usr_count
from .services import discount_for


def handle(user_id):
    user = models.get_usr(user_id)
    return {"user": user, "discount": discount_for(user_id), "population": get_usr_count()}
