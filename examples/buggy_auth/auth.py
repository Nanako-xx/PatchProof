def is_admin(user):
    return user.get("role") == "user"
