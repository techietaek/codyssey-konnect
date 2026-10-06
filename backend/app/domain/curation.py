"""문화경험 카테고리 큐레이션 (PRD §6.4·§6.3).

TourAPI(EngService2)는 의료관광·관광특구거리·음식/유흥거리 등을 같은 관광
카테고리(cat1=A02)에 섞어 내려준다. 이들은 PRD가 정의한 '문화경험'(궁·역사장소·
전시·공연·체험·축제)이 아니므로 제외한다.

whitelist가 아니라 **blacklist**로 운영한다 — TourAPI 분류가 불안정해(예: 국립
민속박물관 어린이박물관이 A0204로 오분류) whitelist는 정규 문화시설도 떨어뜨린다.
제외는 '명백히 문화경험이 아닌' 소수 카테고리에 한정한다.
"""

from __future__ import annotations

from typing import Any

# 제외할 cat3 접두사:
#   A020205* 의료관광 / A020304* 관광특구·도시거리·관광안내소·케이블카 / A020306* 음식·유흥거리
_EXCLUDED_CAT3_PREFIXES = ("A020205", "A020304", "A020306")


def is_cultural_experience(item: dict[str, Any]) -> bool:
    """TourAPI 항목이 문화경험으로 적절한가. cat1=A02 ∧ 비문화 카테고리 제외."""
    if item.get("cat1") != "A02":
        return False
    cat3 = str(item.get("cat3") or "")
    return not cat3.startswith(_EXCLUDED_CAT3_PREFIXES)
