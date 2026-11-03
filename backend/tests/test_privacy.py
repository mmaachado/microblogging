import io
import logging
from pathlib import Path

import httpx
import pytest
from PIL import Image
from sqlalchemy import String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.config import Settings
from backend.db import Base

FORBIDDEN_PARTS = ("ip", "useragent", "agent", "device", "os", "browser")


def test_no_identifying_columns() -> None:
    offenders = [
        f"{table.name}.{column.name}"
        for table in Base.metadata.tables.values()
        for column in table.columns
        if any(part in column.name.split("_") for part in FORBIDDEN_PARTS)
    ]
    assert offenders == []


async def test_requests_leave_no_identifying_trace(
    client: httpx.AsyncClient,
    settings: Settings,
    sessionmaker: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    agent = "PrivacyProbeAgent/1.0"
    forwarded = "203.0.113.77"
    email = "probe.person@example.com"
    password = "probe password 123"
    headers = {"User-Agent": agent, "X-Forwarded-For": forwarded}
    registered = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "acknowledged_email_notice": True,
        },
        headers=headers,
    )
    assert registered.status_code == 201
    token = client.cookies["session"]
    await client.post("/api/v1/auth/logout", headers=headers)
    await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers=headers,
    )
    await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "wrong password!!"},
        headers=headers,
    )
    phone = "+55 11 98765-4321"
    updated = await client.patch(
        "/api/v1/me",
        json={"username": "probe_name", "phone": phone},
        headers=headers,
    )
    assert updated.status_code == 200
    image = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(image, "PNG")
    avatar = await client.put(
        "/api/v1/me/avatar",
        files={"file": ("probe_photo.png", image.getvalue())},
        headers=headers,
    )
    assert avatar.status_code == 200
    post_body = "probe post body text"
    post = await client.post(
        "/api/v1/posts",
        data={"body": post_body},
        files=[("files", ("probe_post_photo.png", image.getvalue()))],
        headers=headers,
    )
    assert post.status_code == 201
    rejected = await client.post(
        "/api/v1/posts",
        data={"body": post_body},
        files=[("files", ("probe_bad_file.png", b"not media"))],
        headers=headers,
    )
    assert rejected.status_code == 422
    secrets_ = [agent, forwarded, email, password, token]

    logged = caplog.text + Path(settings.log_file).read_text()
    for secret in [
        *secrets_,
        phone,
        "probe_name",
        "probe_photo",
        "probe_post_photo",
        "probe_bad_file",
        post_body,
    ]:
        assert secret not in logged

    async with sessionmaker() as db:
        for table in Base.metadata.sorted_tables:
            columns = [
                c
                for c in table.columns
                if isinstance(c.type, String | Text)
                and (table.name, c.name) != ("users", "email")
            ]
            if not columns:
                continue
            rows = (await db.execute(select(*columns))).all()
            stored = " ".join(str(v) for row in rows for v in row)
            for secret in secrets_:
                assert secret not in stored
