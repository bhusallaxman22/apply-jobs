from app.schemas import PageState


def detect_platform(page_state: PageState) -> str:
    url = page_state.url.lower()
    title = page_state.title.lower()
    visible_text = page_state.visible_text.lower()

    if "greenhouse.io" in url or "greenhouse" in title or "greenhouse" in visible_text:
        return "greenhouse"
    if "lever.co" in url or "lever" in title or "lever" in visible_text:
        return "lever"
    return "generic"
