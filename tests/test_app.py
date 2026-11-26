import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
print("DEBUG DATABASE_URL:", os.environ.get("DATABASE_URL"))

from models import Expense, User, db
from app import app
import pytest

app.secret_key = os.environ.get("SECRET_KEY", "test-secret")

@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///expenses.db")
    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.drop_all()


def register_and_login(client, username, password="password123"):
    client.post("/register", data={"username": username, "password": password}, follow_redirects=True)

    client.post("/login", data={"username": username, "password": password}, follow_redirects=True)


def test1(client):
    response = client.get("/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]

def test_anonmyous_redirects_to_login(client):
    register_and_login(client, "Alice", "password123")
    response = client.get("/")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "/logout" in body

def test_short_password_rejected(client):
    client.post("/register", data={"username":"Bob", "password":"12345"})

    with app.app_context():
        assert User.query.filter_by(username="Bob").first() is None
        assert User.query.count() == 0

def test_user_cannot_edit_another_users_expense(client):
    register_and_login(client, "A", "password123")
    client.post("/add", data={"amount":800, "category":"Food", "description":"Dinner at restaurant"}, follow_redirects=True)

    with app.app_context():
        expense = Expense.query.first()

        assert expense is not None
        expense_id = expense.id

    own_response = client.get(f"/edit/{expense_id}")
    assert own_response.status_code == 200

    client.get("/logout", follow_redirects=True)

    register_and_login(client, "B", "password123")
    response = client.get(f"/edit/{expense_id}")

    assert response.status_code == 404

# def test_uses_memory_database(client):
#     assert str(db.engine.url) == "sqlite:///:memory:"

def test_uses_memory_database(client):
    assert db.engine.url.drivername == "sqlite"
    assert db.engine.url.database == ":memory:"