from app.site_adapters.generic import GenericAdapter
from app.site_adapters.greenhouse import GreenhouseAdapter
from app.site_adapters.lever import LeverAdapter


def get_adapter(platform: str) -> GenericAdapter:
    if platform == "greenhouse":
        return GreenhouseAdapter()
    if platform == "lever":
        return LeverAdapter()
    return GenericAdapter()
