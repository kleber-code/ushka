# routes/glitch.py


class CyberneticImplantError(Exception):
    """Raised when the digital soul rejects the chrome."""

    pass


async def get():
    raise CyberneticImplantError(
        "⚡ SYNAPTIC FAILURE: Neural handshake refused. "
        "The system is rejecting the external payload."
    )
