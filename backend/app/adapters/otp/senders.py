"""OTP delivery — 2/3 §7.1.

`mock` is the default and is what every test and the offline demo run. There is
no SMS implementation in this build: wiring one is a gateway account, a sender
id registered with TRAI, and a DLT template, none of which exist yet. The
protocol is here so that adding it changes this file and nothing else.
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.errors import ConfigurationError
from app.core.logging import get_logger

logger = get_logger(__name__)


class MockOTPSender:
    """Delivers nothing.

    The code comes back in the response body instead, so a demo on a laptop
    with no signal can complete a sign-in. `PatientAuthService` gates that on
    the environment not being production — this class being in use is not on its
    own enough to leak a code.
    """

    name = "mock"
    reveals_code = True

    async def send(self, *, phone: str, code: str) -> None:
        # Neither argument is logged. A mock that prints the code to the
        # application log would put live codes in Cloud Logging the moment
        # somebody left the mock enabled by accident.
        logger.info("otp_send_skipped", provider=self.name)


class SMSOTPSender:
    """Placeholder for a real gateway.

    Raises rather than silently succeeding: a sign-in flow that reports success
    and sends nothing is worse than one that fails loudly, because the patient
    waits for a message that is never coming.
    """

    name = "sms"
    reveals_code = False

    def __init__(self, settings: Settings) -> None:
        raise ConfigurationError(
            "OTP_PROVIDER=sms is configured but no SMS gateway is implemented in "
            "this build. Set OTP_PROVIDER=mock, or implement this class."
        )

    async def send(self, *, phone: str, code: str) -> None:  # pragma: no cover
        raise NotImplementedError


def build_sender(settings: Settings) -> MockOTPSender | SMSOTPSender:
    if settings.otp_provider == "sms":
        return SMSOTPSender(settings)
    return MockOTPSender()
