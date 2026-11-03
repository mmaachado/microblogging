import logging

from backend.media.images import (
    AVATAR_DRAFT_SIZE,
    InvalidImage,
    open_image,
    to_avatar,
)

logger = logging.getLogger(__name__)


def process_avatar(data: bytes) -> bytes:
    try:
        return to_avatar(open_image(data, AVATAR_DRAFT_SIZE))
    except Exception as error:
        logger.info("avatar rejected: %s", type(error).__name__)
        raise InvalidImage from None
