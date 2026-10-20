"""Small bilingual retrieval vocabulary. These aliases never establish a verdict."""

COMPONENTS = {
    'first_stage': ('first stage', 'first-stage', 'lower stage', 'lower-stage', 'booster', '一级', '助推器'),
    'upper_stage': ('upper stage', 'upper-stage', 'second stage', 'second-stage', '上面级', '二级'),
    'engine': ('engine', 'engines', '发动机'),
    'vehicle': ('vehicle', '运载器', '运载火箭'),
}
MILESTONES = {
    'landing': ('landing', 'landed', 'land', '着陆'),
    'recovery': ('recovery', 'recover', 'recovers', 'recovered', 'recovering', '回收'),
    'reflight': ('reflight', 're-flight', 'reflown', 'refly', 'second flight', 'second launch',
                'flew again', 'fly again', 'launching the recovered unit again', '复飞', '第二次飞行', '再次发射'),
    'reuse': ('reuse', 'reusable', 'reused', '重复使用', '复用'),
    'repeated_reflight': ('repeated reflight', 'multiple reflights', '多次复飞'),
    'routine': ('routine', 'operational reuse', 'scheduled missions', '常态化', '定期任务'),
    'restart': ('restart', 'relight', 'second ignition', 'second engine firing', '重复点火', '二次启动'),
    'test': ('test', 'trial', 'testing', 'demonstration', 'demonstrated', '验证', '试验'),
}
# Canonicalization is used only in the new lexical candidate adapter, never in
# source text, citations or the legacy evaluation path. No broad semantic expansion.
LEXICAL_VARIANTS = {
    'recovery': MILESTONES['recovery'],
    'reflight': MILESTONES['reflight'] + MILESTONES['repeated_reflight'],
    'restart': MILESTONES['restart'],
    'stage': ('stage', 'stages'),
}
PLANNED = (r'\b(?:plans?|planned|will|targets?|targeted|expected|intends?|future|next year)\b'
           r'|\bscheduled\s+(?:to|for)\b|计划|规划|目标|明年|将要|将于')
COMPLETED = (r'\b(?:completed|successfully|performed|flew|demonstrated|achieved)\b'
             r'|完成|成功|已验证|再次发射|已实现')
NEGATIVE = (r'\b(?:not|never|untested|unperformed|expendable|expends?|discarded)\b'
            r'|尚未|没有|未能|未曾|不回收|一次性|未报告|不是')
BACKGROUND = (r'\b(?:benefits?|advantages?|in principle|requires?|offers?|could|potential)\b'
              r'|一般优势|可以|需要|要求')
SCOPE = r'\bboth\s+stages\b|两级|两级回收'
QUERY_PREFIX = r'^(?:(?:has|have|had|did|does|do|is|are|was|were|can|could|the|same)\s+)+'
QUERY_BOUNDARY = (r'\b(?:complete[ds]?|recover(?:s|ed|y)?|demonstrat\w*|achiev\w*|'
                  r'reuse[ds]?|reusable|reflight|reflown|been|has|have)\b|是否|已经|完成|实现')

# Retrieval distinctions, NOT a logical implication chain or evidence taxonomy.
MILESTONE_LEVEL = {'landing': 1, 'recovery': 2, 'reflight': 3, 'reuse': 3,
                   'repeated_reflight': 4, 'routine': 5}
RELATIONSHIP_STRENGTH = 0.25
# One global feature formula; never query- or fixture-specific weights.
WEIGHTS = {
    'entity_match': 1.0, 'entity_event_locality': 3.0, 'entity_conflict': -8.0,
    'component_match': 2.0, 'component_conflict': -3.0,
    'milestone_match': 2.0, 'milestone_conflict': -2.0,
    'requested_completed': 2.0, 'negative_answer': 1.5,
    'planned_when_completed_requested': -2.0, 'requested_plan': 2.0,
    'background_language': -1.0, 'temporal_match': 3.0, 'temporal_conflict': -3.0,
    'jurisdiction_match': 2.0, 'jurisdiction_conflict': -4.0,
    'same_clause': 1.0,
    'entity_sentence_locality': 2.0, 'entity_paragraph_locality': 1.0,
}
