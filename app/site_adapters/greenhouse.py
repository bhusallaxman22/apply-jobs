from app.site_adapters.generic import GenericAdapter


class GreenhouseAdapter(GenericAdapter):
    name = "greenhouse"
    apply_triggers = (
        "apply for this job",
        "apply now",
        "apply",
    )
