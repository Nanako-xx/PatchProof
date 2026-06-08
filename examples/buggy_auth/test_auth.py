from auth import is_admin


def test_admin_user_is_admin():
    assert is_admin({"role": "admin"}) is True
