from httpx import AsyncClient

from tests.conftest import tokens_for


class TestRegister:

    async def test_register_success(self, client: AsyncClient):
         response = await client.post(
             "/api/v1/auth/register",
             json={"name": "test", "email": "new@example.com","password": "secret123"},
         )
         assert response.status_code == 201, response.text
         data = response.json()
         assert data["email"] == "new@example.com"
         assert data["role"] == "user"
         assert "id" in data
         assert "password" not in data
         assert "hashed_password" not in data

    async def test_register_duplicate_email(self, client: AsyncClient, user_factory):
        await user_factory(email="dup@example.com")
        response = await client.post(
            "/api/v1/auth/register",
            json={"name": "test", "email": "dup@example.com", "password": "secret123"},
        )
        assert response.status_code == 409

    async def test_register_weak_password(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/auth/register",
            json={"name": "test", "email": "weak@example.com", "password": "short"},
        )
        assert response.status_code == 422

    async def test_register_password_without_digit(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/auth/register",
            json={"name": "test", "email": "no-digit@example.com", "password": "onlyletters"},
        )
        assert response.status_code == 422

    async def test_register_invalid_email(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/auth/register",
            json={"name": "test", "email": "not-an-email", "password": "secret123"},
        )
        assert response.status_code == 422

class TestLogin:
    async def test_login_success(self, client: AsyncClient, user_factory):
        user = await user_factory(email="login@example.com")
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "login@example.com", "password": "password123"}
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == 900

    async def test_login_wrong_password(self, client: AsyncClient, user_factory):
        await user_factory(email="user@example.com")
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "user@example.com", "password": "wrong_password",}
        )
        assert response.status_code == 401

    async def test_login_nonexistent_user(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "ghost@example.com", "password": "secret123"},
        )
        assert response.status_code == 401

    async def test_login_inactive_user(self, client: AsyncClient, user_factory):
        await user_factory(email="blocked@example.com", is_active=False)
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "blocked@example.com", "password": "password123"},
        )
        assert response.status_code == 403

class TestMe:

    async def test_me_authenticated(self, client: AsyncClient, auth_headers):
        headers = await auth_headers()
        response = await client.get("/api/v1/auth/me", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "email" in data
        assert data["role"] == "user"

    async def test_me_unauthorized(self, client: AsyncClient):
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401

    async def test_me_invalid_token(self, client: AsyncClient):
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer garbage.token.here"},
        )
        assert response.status_code == 401

    async def test_me_wrong_scheme(self, client: AsyncClient):
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "garbage"},
        )
        assert response.status_code == 401


class TestRefresh:
    async def test_refresh_success(self, client: AsyncClient, user_factory, tokens_for):
        user = await user_factory()
        tokens = tokens_for(user)

        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["refresh_token"] != tokens["refresh_token"]

    async def test_refresh_with_access_token_fails(self, client: AsyncClient, user_factory, tokens_for):
        user = await user_factory()
        tokens = tokens_for(user)

        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["access_token"]}
        )
        assert response.status_code == 401

    async def test_refresh_token_rotation(self, client: AsyncClient, user_factory, tokens_for):
        user = await user_factory()
        tokens = tokens_for(user)
        old_refresh = tokens["refresh_token"]

        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_refresh}
        )

        assert response.status_code == 200

        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_refresh},
        )
        assert response.status_code == 401

class TestLogout:
    async def test_logout_success(self, client: AsyncClient, auth_headers, user_factory, tokens_for):
        user = await user_factory()
        tokens = tokens_for(user)
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        response = await client.post(
            "/api/v1/auth/logout",
            headers=headers,
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert response.status_code == 204

    async def test_logout_without_token(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/logout")
        assert response.status_code == 422


# class TestRateLimit:
#     async def test_login_rate_limit(self, client: AsyncClient, user_factory):
#         await user_factory(email="ratelimit@example.com")
#
#         for i in range(6):
#             response = await client.post(
#                 "/api/v1/auth/login",
#                 json={"email": "ratelimit@example.com", "password": "wrong"},
#             )
#         assert response.status_code == 429