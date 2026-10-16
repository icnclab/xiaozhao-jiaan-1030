"""Compare the actor of a duty, not merely presence of role names in a chunk."""
import re
from app.services.text import normalize, bigrams

_ALIASES = {'照顧服務員':'照服員','居服員':'照服員','居家服務督導員':'督導',
            '居督員':'督導','居督':'督導','個案':'住民','服務使用者':'住民','長輩':'住民'}
_ROLES = r'照服員|督導|家屬|住民|主管|護理師|護理人員'

def duties(text):
    t = normalize(re.sub(r'\s+', '', text))
    for alias, canonical in sorted(_ALIASES.items(), key=lambda x:-len(x[0])):
        t = t.replace(normalize(alias), canonical)
    actor = None
    out = []
    for clause in re.split(r'[，,。；;！？!?]|\d+[.、]', t):
        explicit = re.search(rf'(?:請)?({_ROLES})(?:應|須|需(?!求)|不得|不可|可以|得|會|詳實|負責|必須|紀錄|記錄|提供|執行|擬定|協調|回報|通報)', clause)
        if explicit:
            actor = explicit.group(1)
            predicate = clause[explicit.end(1):]
        elif actor and re.search(r'^(?:並|且|同時|亦|另|則|應|須|需|不得)', clause):
            predicate = clause
        else:
            continue
        predicate = re.sub(r'應|須|需|不得|不可|可以|同時|詳實|並|亦|會|請', '', predicate)
        out.append((actor, predicate, set(bigrams(predicate))))
    return out

def check_roles(claim, evidence_texts):
    source = [d for text in evidence_texts for d in duties(text)]
    mismatches = []
    for actor, predicate, tokens in duties(claim):
        matches = [(len(tokens & st), sa, sp) for sa, sp, st in source]
        if not matches:
            continue
        score = max(x[0] for x in matches)
        # Require a substantive predicate overlap, not merely a common verb.
        if score < 3:
            continue
        best = [x for x in matches if x[0] == score]
        if actor not in {x[1] for x in best}:
            mismatches.append(dict(claim_actor=actor, predicate=predicate,
                                   source_actors=sorted({x[1] for x in best}),
                                   source_predicates=[x[2] for x in best]))
    return dict(passed=not mismatches, mismatches=mismatches)
