from __future__ import annotations

from datetime import datetime
from typing import Protocol

from ccprophet.domain.entities import PricingRate


class PricingProvider(Protocol):
    def rate_for(self, model: str, at: datetime | None = None) -> PricingRate: ...
