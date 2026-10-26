import asyncio
from datetime import datetime, timedelta
from httpx import AsyncClient
from src.models.booking import BookingStatusEnum
from src.models.seat import Seat, SeatStatusEnum
from tests.conftest import user_factory, db_session


class TestHoldSeat:
    async def test_hold_seat_success(self, client: AsyncClient, auth_headers, seat_factory):
        seat = await seat_factory()
        headers = await auth_headers()
        response = await client.post(f"/api/v1/hold/{seat.id}", headers=headers)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["status"] == "success"
        assert "booking_id" in data
        assert "reserved_until" in data

    async def test_hold_seat_unauthorized(self, client: AsyncClient, seat_factory):
        seat = await seat_factory()
        response = await client.post(f"/api/v1/hold/{seat.id}")
        assert response.status_code == 401

    async def test_hold_seat_not_found(self, client: AsyncClient, auth_headers):
        headers = await auth_headers()
        response = await client.post("/api/v1/hold/99999", headers=headers)
        assert response.status_code == 400

    async def test_hold_a_ready_booked_seat(
            self, client: AsyncClient, auth_headers, seat_factory
    ):
        seat = await seat_factory(status=SeatStatusEnum.RESERVED)
        headers = await auth_headers()
        response = await client.post(f"/api/v1/hold/{seat.id}", headers=headers)
        assert response.status_code == 400

    async def test_hold_race_condition(
            self, client: AsyncClient,user_factory, seat_factory, tokens_for
    ):
        seat = await seat_factory()
        user1 = await user_factory()
        user2 = await user_factory()

        headers1 = {"Authorization": f"Bearer {tokens_for(user1)['access_token']}"}
        headers2 = {"Authorization": f"Bearer {tokens_for(user2)['access_token']}"}
        results = await asyncio.gather(
            client.post(f"/api/v1/hold/{seat.id}", headers=headers1),
            client.post(f"/api/v1/hold/{seat.id}", headers=headers2),
            return_exceptions=True,
        )
        status_codes = sorted(r.status_code for r in results)
        assert status_codes == [200,400], status_codes

class TestConfirmBooking:
    async def test_confirm_success(
            self, client: AsyncClient, auth_headers, booking_factory, user_factory
    ):
        user = await user_factory()
        booking = await booking_factory(user=user)
        headers = await auth_headers(user=user)
        headers["Idempotency-Key"] = "test-key-1"
        response = await client.post(
            f"/api/v1/confirm/{booking.id}", headers=headers
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["status"] == "success"
        assert data["booking_id"] == booking.id

    async def test_confirm_without_idempotency_key(
            self, client: AsyncClient, auth_headers, booking_factory, user_factory
    ):
        user = await user_factory()
        booking = await booking_factory(user=user)
        headers = await auth_headers(user=user)
        response = await client.post(
            f"/api/v1/confirm/{booking.id}", headers=headers
        )
        assert response.status_code == 422
    async def test_confirm_idempotency(
            self, client: AsyncClient, auth_headers, booking_factory, user_factory
    ):
        user = await user_factory()
        booking = await booking_factory(user=user)
        headers = await auth_headers(user=user)
        headers["Idempotency-Key"] = "idempotent-key"
        r1 = await client.post(f"/api/v1/confirm/{booking.id}", headers=headers)
        r2 = await client.post(f"/api/v1/confirm/{booking.id}", headers=headers)

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["booking_id"] == r1.json()["booking_id"]

    async def test_confirm_expired_booking(
            self, client: AsyncClient, auth_headers, booking_factory
    ):
        past = datetime.utcnow() - timedelta(minutes=10)
        booking = await booking_factory(
            status = BookingStatusEnum.RESERVED,
            reserved_until = past,
        )
        headers = await auth_headers()
        headers["Idempotency-Key"] = 'expired-key'

        response = await client.post(
            f"/api/v1/confirm/{booking.id}", headers=headers
        )
        assert response.status_code == 400
    async def test_confirm_already_sold(
            self, client: AsyncClient, auth_headers, booking_factory
    ):
        booking = await booking_factory(status=BookingStatusEnum.SOLD)
        headers = await auth_headers()
        headers["Idempotency-Key"] = "Sold-key"
        response = await client.post(
            f"/api/v1/confirm/{booking.id}", headers=headers
        )
        assert response.status_code == 400

class TestCleanupTask:
    async def test_release_expired_seats(
            self, run_task, booking_factory, db_session
    ):
        from src.tasks.cleanup_tasks import release_expired_seats
        past = datetime.utcnow() - timedelta(minutes=10)
        booking = await booking_factory(
            status=BookingStatusEnum.RESERVED,
            reserved_until=past,
        )
        result = await run_task(release_expired_seats)
        assert result["released"] == 1
        await db_session.refresh(booking)
        assert booking.status == BookingStatusEnum.EXPIRED

        seat = await db_session.get(Seat, booking.seat_id)
        await db_session.refresh(seat)
        assert seat.status == SeatStatusEnum.FREE

    async def test_does_not_release_active_bookings(
            self, run_task, booking_factory, db_session
    ):
        from src.tasks.cleanup_tasks import release_expired_seats

        future = datetime.utcnow() + timedelta(minutes=5)
        booking = await booking_factory(
            status=BookingStatusEnum.RESERVED,
            reserved_until=future,
        )
        result = await run_task(release_expired_seats)
        assert result["released"] == 0

        await db_session.refresh(booking)
        assert booking.status == BookingStatusEnum.RESERVED