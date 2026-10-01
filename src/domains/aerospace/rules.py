"""Conservative maturity guard, not a domain-independent truth classifier."""
import re
STATUSES = {'DEMONSTRATED', 'OPERATIONAL', 'TESTING', 'PLANNED', 'TARGETED',
            'PROPOSED', 'DELAYED', 'CANCELLED', 'UNKNOWN'}
MILESTONES = {'launch': 0, 'descent': 1, 'landing': 2, 'recovery': 2,
              'inspection': 3, 'reflight': 4, 'repeated_reflight': 5, 'routine_reuse': 6}


def capability_compatible(claim, status, milestone):
    if status not in STATUSES:
        return False
    text = claim.lower()
    # A plan word must not exempt a compound statement of completed performance.
    planned = bool(re.search(r'\b(plans?|planned|targeted|proposed)\b', text)
                   or any(w in text for w in ('计划', '拟于')))
    completed = bool(re.search(r'\b(already|demonstrated|flew|flown|launched|reflown)\b', text)
                     or any(w in text for w in ('已经', '已完成', '成功', '实现')))
    if planned and not completed:
        return True
    required = (6 if any(w in text for w in ('routine', '常态化')) else
                5 if any(w in text for w in ('repeated reflight', '多次复飞')) else
                4 if (re.search(r'\b(reflight|reflown|reuse|reused)\b', text) or '复飞' in text) else
                2 if (re.search(r'\b(landed|landing|recovered|recovery)\b', text)
                      or any(w in text for w in ('着陆', '回收'))) else
                0 if (re.search(r'\b(flown|flew|launched|launch|flight)\b', text)
                      or any(w in text for w in ('飞行', '发射'))) else
                4 if '重复使用' in text else None)
    if required is None:
        return True
    return status in {'DEMONSTRATED', 'OPERATIONAL'} and MILESTONES.get(milestone, -1) >= required
