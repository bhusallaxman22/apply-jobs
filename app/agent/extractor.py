from __future__ import annotations

from app.schemas import ExtractedField, PageElement, PageState


PAGE_STATE_SCRIPT = """
() => {
  const isVisible = (el) => {
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.visibility !== "hidden" &&
      style.display !== "none" &&
      rect.width > 0 &&
      rect.height > 0;
  };

  const escapeValue = (value) => {
    if (window.CSS && typeof window.CSS.escape === "function") {
      return window.CSS.escape(value);
    }
    return value.replace(/["\\\\]/g, "\\\\$&");
  };

  const textOf = (el) => (el.innerText || el.textContent || "").replace(/\\s+/g, " ").trim();

  const labelFor = (el) => {
    if (el.labels && el.labels.length) {
      return Array.from(el.labels).map(textOf).filter(Boolean).join(" ");
    }
    const ariaLabel = el.getAttribute("aria-label");
    if (ariaLabel) return ariaLabel.trim();
    const labelledBy = el.getAttribute("aria-labelledby");
    if (labelledBy) {
      const labelText = labelledBy
        .split(/\\s+/)
        .map((id) => document.getElementById(id))
        .filter(Boolean)
        .map(textOf)
        .filter(Boolean)
        .join(" ");
      if (labelText) return labelText;
    }
    const parentLabel = el.closest("label");
    if (parentLabel) return textOf(parentLabel);
    const fieldWrapper = el.closest(".application-question, .application-field, .field, .form-field, .posting-requirements");
    if (fieldWrapper) return textOf(fieldWrapper).slice(0, 240);
    const previous = el.previousElementSibling;
    if (previous) return textOf(previous);
    return "";
  };

  const selectorFor = (el) => {
    if (el.id) return `#${escapeValue(el.id)}`;
    if (el.name) return `${el.tagName.toLowerCase()}[name="${escapeValue(el.name)}"]`;
    const dataQa = el.getAttribute("data-qa");
    if (dataQa) return `[data-qa="${escapeValue(dataQa)}"]`;
    const ariaLabel = el.getAttribute("aria-label");
    if (ariaLabel) return `${el.tagName.toLowerCase()}[aria-label="${escapeValue(ariaLabel)}"]`;
    return null;
  };

  const optionsFor = (el) => {
    if (el.tagName.toLowerCase() !== "select") return [];
    return Array.from(el.options).map((option) => option.textContent.trim()).filter(Boolean);
  };

  const elements = Array.from(document.querySelectorAll("input, textarea, select, button, a"))
    .filter(isVisible)
    .slice(0, 200)
    .map((el) => ({
      label: labelFor(el) || null,
      selector: selectorFor(el),
      tag_name: el.tagName.toLowerCase(),
      input_type: el.getAttribute("type"),
      name: el.getAttribute("name"),
      placeholder: el.getAttribute("placeholder"),
      text: textOf(el).slice(0, 200) || null,
      value: el.value ? String(el.value).slice(0, 200) : null,
      options: optionsFor(el),
      disabled: !!el.disabled,
    }));

  return {
    url: window.location.href,
    title: document.title,
    visible_text: textOf(document.body).slice(0, 8000),
    elements,
  };
}
"""


async def extract_page_state(page) -> PageState:
    raw = await page.evaluate(PAGE_STATE_SCRIPT)
    return PageState(
        url=raw["url"],
        title=raw["title"],
        visible_text=raw["visible_text"],
        elements=[PageElement(**element) for element in raw["elements"]],
    )


async def extract_form_schema(page) -> list[ExtractedField]:
    page_state = await extract_page_state(page)
    fields: list[ExtractedField] = []
    for element in page_state.elements:
        if element.tag_name not in {"input", "textarea", "select"}:
            continue
        label = element.label or element.name or element.placeholder or element.selector or "unlabeled field"
        field_type = element.input_type or element.tag_name
        fields.append(
            ExtractedField(
                label=label[:240],
                selector=element.selector,
                field_type=field_type,
                name=element.name,
                placeholder=element.placeholder,
                options=element.options,
                current_value=element.value,
            )
        )
    return fields
