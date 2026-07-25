from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Базовая схема ответа: наружу поля идут в camelCase.

    TS-фронт потребляет ответы без промежуточного маппинга, а внутри
    Python-кода остаётся привычный snake_case.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )
