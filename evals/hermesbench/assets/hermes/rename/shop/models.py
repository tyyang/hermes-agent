USERS = {1: {"name": "Ada", "tier": "gold"}, 2: {"name": "Linus", "tier": "silver"}}


def get_usr(user_id):
    """Return the user dict for user_id, or None."""
    return USERS.get(user_id)


def get_usr_count():
    return len(USERS)
