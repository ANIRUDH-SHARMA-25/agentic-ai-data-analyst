"""Bounded, deterministic claim checks for the synthetic retail evaluation only.



This is an explicit English-format oracle, not a general semantic truth judge.

Unknown numerical claims fail closed and are identified for local review.

"""
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

NUMBER = re.compile(r"(?<![\w])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:st|nd|rd|th)?")
WORDS = {"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,"seven":7,"eight":8,"nine":9,"ten":10,"zero":0,"eleven":11,"twelve":12,"thirteen":13,"fourteen":14,"fifteen":15,"sixteen":16,"seventeen":17,"eighteen":18,"nineteen":19,"twenty":20,"thirty":30,"forty":40,"fifty":50,"sixty":60,"seventy":70,"eighty":80,"ninety":90}


def normalize(text):
    text = text.casefold().replace("\u2212", "-")
    for phrase, value in [("two hundred and sixty",260),("two hundred sixty",260),
                          ("one hundred and fifty",150),("one hundred fifty",150),
                          ("one hundred and twenty",120),("one hundred twenty",120),
                          ("five hundred and thirty",530),("five hundred thirty",530)]:
        text = re.sub(r"\b"+phrase+r"\b",str(value),text)
    text = re.sub(r"\b("+"|".join(WORDS)+r")\b",lambda m:str(WORDS[m.group()]),text)
    text = re.sub(r"\b(?:negative|minus)\s+(?=\d)","-",text)
    text = re.sub(r"[*`]", "", text)
    text = re.sub(r"(?m)^(\s*)([123])\.\s+", lambda m:m[1]+{"1":"1st ","2":"2nd ","3":"3rd "}[m[2]],text)
    # Direction headings are not assertions that an unnamed category ranks 1/3.
    return re.sub(r"\b(?:from\s+)?highest\s+to\s+lowest\b", "descending", text)


def explanation_checks(index, text, expected):
    normalized = normalize(text)
    amounts = {name.casefold():Decimal(str(value)) for name,value in expected[0]}
    names = list(amounts)
    total = sum(amounts.values())
    categories = re.compile(r"\b(?:"+"|".join(re.escape(name) for name in names)+r")\b")
    clauses = re.split(r"[;\n!?]|\.(?!\d)",normalized)
    failures, revenue_seen, second_seen = [],set(),False
    def safe_number(value):
        return float(value) if abs(value) <= Decimal('1e12') else str(value)[:60]
    def reject(kind, clause, observed=None, wanted=None, category=None):
        if len(failures) < 20:
            failures.append({"kind":kind,"claim_excerpt":clause.strip()[:160],
                             "observed":safe_number(observed) if observed is not None else None,
                             "expected":safe_number(wanted) if wanted is not None else None,
                             "category":category})
    def owner(clause, start, end, prefer_previous=False):
        positions=list(categories.finditer(clause))
        if not positions:return None
        if prefer_previous:
            previous=[m for m in positions if m.end()<=start]
            following=[m for m in positions if m.start()>=end]
            if following and re.search(r"\b(?:for|from|by)\b",clause[end:following[0].start()]):
                return following[0].group()
            if previous and start-previous[-1].end()<=120:
                return previous[-1].group()
        distances=[(max(m.start()-end,start-m.end(),0),m.group()) for m in positions]
        best=min(d for d,_ in distances)
        choices={name for d,name in distances if d==best}
        return next(iter(choices)) if len(choices)==1 and best<=120 else None
    def rank_claim(clause, start, end, rank):
        nonlocal second_seen
        name=owner(clause,start,end)
        wanted=Decimal(names.index(name)+1) if name else None
        if wanted is None or Decimal(rank)!=wanted:
            reject("rank",clause,Decimal(rank),wanted,name)
        elif name==names[1] and rank==2:
            second_seen=True
    for clause in clauses:
        tokens=list(NUMBER.finditer(clause))
        for i,token in enumerate(tokens):
            raw=token.group()
            ordinal=bool(re.search(r"(?:st|nd|rd|th)$",raw))
            raw=re.sub(r"(?:st|nd|rd|th)$","",raw)
            value=Decimal(raw.replace(",",""))
            before=clause[:token.start()]
            prefix=clause[tokens[i-1].end() if i else 0:token.start()]
            after=clause[token.end():]
            name=owner(clause,token.start(),token.end(),prefer_previous=True)
            is_rank=(ordinal or bool(re.search(r"\brank(?:ed|s)?\s*#?\s*$",before))
                     or (not before.strip() and bool(re.match(r"[.)]\s+",after))))
            if is_rank:
                rank_claim(clause,token.start(),token.end(),value)
                continue
            if re.match(r"\s*(?:categories|category)\b",after) or re.search(r"\b(?:(?:number|count) of categories|category count)(?: is|:)?:?\s*$",before):
                wanted=Decimal(len(names))
                if value!=wanted:reject("category_count",clause,value,wanted)
                continue
            measure=prefix[-60:]+after[:25]
            if re.search(r"\b(?:profit|cost|customers?|units?|items?|quantity|margin|increased?|decreased?|growth|change)\b",measure):
                reject("unsupported_measure",clause,value,None,name)
                continue
            if re.match(r"\s*(?:%|percent\b|per cent\b)",after):
                wanted=(amounts[name]*100/total) if name else (Decimal(100) if re.search(r"\ball (?:\d+ )?categories\b|\btotal (?:share|contribution)\b",clause) else None)
                places=max(0,-value.normalize().as_tuple().exponent)
                try:rounded=wanted.quantize(Decimal(1).scaleb(-places),rounding=ROUND_HALF_UP) if wanted is not None and places<=12 else None
                except InvalidOperation:rounded=None
                if rounded is None or value!=rounded:reject("percentage",clause,value,rounded,name)
                continue
            if re.search(r"\(\s*[$\u20ac\u00a3]?\s*$",before) and re.match(r"\s*\)",after):
                reject("accounting_negative",clause,-abs(value),amounts.get(name),name)
                continue
            total_words=r"\b(?:total|overall|combined|grand)\b"
            is_total=bool(re.search(r"\bout of\s*$|\bof (?:the )?total(?: revenue)?\s*$",prefix)) or (bool(re.search(total_words,prefix)) and not categories.search(prefix)) or (not categories.search(clause) and bool(re.search(total_words,before)))
            is_total = is_total or bool(re.search(r"\b(?:total|overall|combined|grand) revenue across\b",prefix))
            if is_total:
                if value!=total:reject("total",clause,value,total)
                continue
            if name:
                wanted=amounts[name]
                if value==wanted:
                    revenue_seen.add(name)
                else:reject("category_revenue",clause,value,wanted,name)
            else:
                reject("unrecognized_number",clause,value)
        rank_pattern=r"\b(first|second|third|highest|lowest)\b"
        for marker in re.finditer(rank_pattern,clause):
            word=marker.group()
            if word=="highest" and re.search(r"second[- ]$",clause[:marker.start()]):continue
            rank_claim(clause,marker.start(),marker.end(),{"first":1,"second":2,"third":3,"highest":1,"lowest":3}[word])
        if re.search(r"\b(?:not|never|no|million|billion|thousand)\b",clause):
            reject("negated_or_scaled_claim",clause)
    required=set(names) if index==0 else {names[1]}
    return {"expected_facts_present":required<=revenue_seen,
            "numerical_claims_supported":not failures,
            "second_category_identified":second_seen and not any(f['kind']=='rank' for f in failures) if index==1 else None,
            "answer_characters":len(text),"validation_failures":failures}
