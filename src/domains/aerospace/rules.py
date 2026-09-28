"""Conservative maturity guard, not a domain-independent truth classifier."""
STATUSES = {'DEMONSTRATED', 'OPERATIONAL', 'TESTING', 'PLANNED', 'TARGETED',
            'PROPOSED', 'DELAYED', 'CANCELLED', 'UNKNOWN'}
MILESTONES = {'launch': 0, 'descent': 1, 'landing': 2, 'recovery': 2,
              'inspection': 3, 'reflight': 4, 'repeated_reflight': 5, 'routine_reuse': 6}


def capability_compatible(claim, status, milestone):
    if status not in STATUSES:
        return False
    text = claim.lower()
    # Explicit plan claims can be supported as plans. No automatic translations.
    if any(word in text for word in ('plans', 'planned', 'targeted', '计划', '拟于')):
        return True
    required = (6 if any(w in text for w in ('routine', '常态化')) else
                4 if any(w in text for w in ('reflight', 'reflown', 'reuse', '复飞', '重复使用')) else None)
    if required is None:
        return True
    return status in {'DEMONSTRATED', 'OPERATIONAL'} and MILESTONES.get(milestone, -1) >= required
