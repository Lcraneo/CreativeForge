"""External image-model prompt composition.

The custom API receives the user's original goal plus the structured
character attributes so third-party models get the same information the
built-in pipeline has.
"""

from agent.generation.spec import parse_prompt

STYLE_SUFFIX = (
    "character concept art, full body front view, clean line art, soft cel shading, "
    "semi-realistic anime style, delicate facial features, detailed hair, elegant "
    "proportions, high detail, plain light background, no text, no watermark"
)


def build_image_prompt(goal, overrides=None, enhanced=None):
    spec = parse_prompt(goal)

    if enhanced:
        # the chat model already produced an art-directed prompt
        return "{}\n{}".format(str(enhanced).strip(), STYLE_SUFFIX)

    parts = [str(goal).strip()]

    details = [
        spec.get("gender_label"),
        spec.get("class_label") if spec.get("class") != "hero" else None,
        "{}{}".format(spec.get("element_label", ""), "") if spec.get("element") != "none" else None,
        "{}体型".format(spec.get("build_label")) if spec.get("build_label") else None,
        "身高{}cm".format(spec.get("height_cm")) if spec.get("height_cm") else None,
        "{}{}".format(spec.get("hair_color_label", ""), spec.get("hair_style_label", "")),
        "{}眼神".format(spec.get("expression_label")) if spec.get("expression_label") else None,
        "手持{}".format(spec.get("weapon_label")) if spec.get("weapon") not in (None, "none") else None,
    ]
    details = [item for item in details if item]
    if details:
        parts.append("角色设定：" + "，".join(details))

    if overrides:
        pairs = ["{}={}".format(key, value) for key, value in overrides.items() if value]
        if pairs:
            parts.append("参数约束：" + "，".join(pairs))

    parts.append(STYLE_SUFFIX)
    return "\n".join(parts)
