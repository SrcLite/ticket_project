from httpx import AsyncClient
from src.core.redis_client import redis_client
from src.services.cache_service import CacheService

class TestGetHallSeats:
    async def test_get_seats_success(
            self, client: AsyncClient, seat_factory, hall_factory
    ):
        hall = await hall_factory()
        await seat_factory(hall=hall)
        await seat_factory(hall=hall)

        response = await client.get(f"/api/v1/halls/{hall.id}/seats")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert all("status" in s for s in data)

    async def test_get_empty_hall(
            self, client: AsyncClient, hall_factory
    ):
        hall = await hall_factory()
        response = await client.get(f"/api/v1/halls/{hall.id}/seats")
        assert response.status_code == 404

class TestSeatsCache:

    async def test_cache_populated_after_first_request(
            self, client: AsyncClient, seat_factory, hall_factory
    ):
        hall = await hall_factory()
        await seat_factory(hall=hall)

        cached_before = await CacheService.get_hall_seats(hall.id)
        assert cached_before is None

        response = await client.get(f'/api/v1/halls/{hall.id}/seats')
        assert response.status_code == 200

        cached_after = await CacheService.get_hall_seats(hall.id)
        assert cached_after is not None
        assert len(cached_after) == 1

    async def test_cache_invalidated_on_hold(
            self,
            client: AsyncClient,
            auth_headers,
            seat_factory,
            hall_factory,
            user_factory,
        ):
        user = await user_factory()
        hall = await hall_factory()
        seat = await seat_factory(hall=hall)

        response = await client.get(f"/api/v1/halls/{hall.id}/seats")
        assert response.status_code == 200
        assert await CacheService.get_hall_seats(hall.id) is not None
        headers = await auth_headers(user=user)
        response = await client.post(f"/api/v1/hold/{seat.id}", headers=headers)
        assert response.status_code == 200, response.text
        assert await CacheService.get_hall_seats(hall.id) is None