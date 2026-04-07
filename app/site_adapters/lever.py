from app.site_adapters.generic import GenericAdapter


class LeverAdapter(GenericAdapter):
    name = "lever"
    apply_triggers = (
        "apply for this job",
        "apply now",
        "apply",
    )
