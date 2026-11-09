"""Mago adapter for Serena's public external backend registration mechanism."""
from .server import MagoServer


def register():
    from solidlsp.ls_config import ExternalLanguageServerId, FilenameMatcher, LanguageServerRegistry

    LanguageServerRegistry.get_instance().register(
        ExternalLanguageServerId(key="mago", matcher=FilenameMatcher(".php"), implementation=MagoServer)
    )
