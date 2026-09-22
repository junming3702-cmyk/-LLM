"""Conservative input-only factual-task signals; not general Chinese parsing.

Only a directly attached, explicit exclusion suppresses a cue. Double
negation, quotation and unclear scopes remain active and require review.
This helper never reads answers, law evidence, IDs or reference labels.
"""
import re

VERSION = 'question-scope-signals-v1'
CUES = re.compile(r'是否实际|是否真实|是否已提交|是否已送达|是否齐全|是否完整提交|(?:核验|核实)[^，,。；;！？!?\n]{0,8}真实性|实际开标|实际履行')
EXCLUSION = re.compile(r'(?:暂不|不再|不应|不得|无需|无须|不需|不必|不负责|不涉及|不包括|不包含|不)(?:(?:另行|进一步|再次|再))?(?:(?:核验|核实|审查|检查|确认|判断)(?:其)?)?$')
DOUBLE = re.compile(r'不能不|不得不|并非不|不是不|不应不|不要不|不可不|无需不|无须不|不必不|不需要不|不能无需|并非无需|不是无需')
UNCERTAIN = re.compile(r'如果|除非|假如|倘若|若|是否|能否|可否|不确定|不清楚|不明确|尚未明确|不排除')


def factual_question_audit(question):
    question = question if isinstance(question, str) else ''
    signals = []
    for match in CUES.finditer(question):
        start = max([question.rfind(c, 0, match.start()) for c in '，,。；;！？!?\n'] + [-1]) + 1
        prefix = question[start:match.start()]
        left = prefix[-24:]
        neg = EXCLUSION.search(left)
        uncertain = bool(DOUBLE.search(left) or (neg and UNCERTAIN.search(prefix)))
        # A quoted instruction is content, not reliable evidence of task scope.
        quote_context = any(q in prefix for q in '“”「」『』\"')
        excluded = bool(neg and not uncertain and not quote_context)
        signals.append({'start': match.start(), 'end': match.end(), 'cue': match.group(),
            'excluded': excluded, 'prefix': left,
            'reason': 'explicit_attached_exclusion' if excluded else
                      'ambiguous_negation_preserved' if uncertain else
                      'quoted_scope_not_interpreted' if quote_context else 'affirmative_or_unresolved'})
    return {'version': VERSION, 'signals': signals,
            'has_active_factual_cue': any(not s['excluded'] for s in signals),
            'ambiguity_requires_review': any(s['reason'] in {'ambiguous_negation_preserved','quoted_scope_not_interpreted'} for s in signals),
            'not_a_general_language_parser': True}


def legacy_conflict_active(question, audit):
    """Retain the old stage-conflict cue set; only suppress proven exclusions."""
    for match in re.finditer(r'是否实际|实际开标|实际履行|是否已提交|是否已送达', question):
        covering = [s for s in audit['signals'] if s['start'] <= match.start() and s['end'] >= match.end()]
        if not covering or not all(s['excluded'] for s in covering):
            return True
    return False
