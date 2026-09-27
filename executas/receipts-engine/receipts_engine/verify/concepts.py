"""The one-word concepts a job posting is allowed to lend to generated text.

This list exists because of the polarity of the rule it replaced. The verifier
used to license any single word from the posting that the tech lexicon did not
recognise — so an **unknown** word was an allowed word, and every product,
vendor or employer the lexicon had never heard of walked straight into a
tailored bullet. The lexicon is a finite list; new SaaS products are not.

So the test is inverted here: a lone word may be borrowed from the posting only
if it appears below. Unknown now means denied, which is the direction a claim
about someone's career should fail in. Multi-word capitalised phrases keep
their own rule in ``grounding._vocab_index`` — "Customer Success" is a concept
by construction, because names do not usually run to two capitalised words that
the CV also describes in different words.

What belongs here: abstract work concepts a CV might word differently from the
posting ("stakeholder", "onboarding", "mutabakat"). What does not: anything a
reader would hold the candidate to as a fact — tools, products, employers,
certifications, titles. When in doubt leave it out; the cost of an absent word
is one repaired sentence, and the cost of a wrong one is the product's promise.

Entries are written readably and normalised at import, so they compare exactly
the way ``grounding`` compares everything else.
"""

from __future__ import annotations

from typing import Final

from ..text import normalize

#: Written in natural form; normalised below. Turkish entries are spelled with
#: their diacritics — :func:`~receipts_engine.text.normalize` folds them.
_SOURCE: Final[tuple[str, ...]] = (
    # — ways of working —
    "collaboration", "communication", "coordination", "facilitation",
    "leadership", "ownership", "accountability", "autonomy", "initiative",
    "mentoring", "mentorship", "coaching", "teamwork", "partnership",
    "alignment", "transparency", "empathy", "adaptability", "resilience",
    "curiosity", "feedback", "culture", "wellbeing", "diversity", "inclusion",
    "sustainability", "stakeholder", "stakeholders", "teams", "cross-functional",
    # — delivery —
    "delivery", "discovery", "planning", "prioritisation", "prioritization",
    "roadmap", "strategy", "execution", "estimation", "scoping", "governance",
    "documentation", "reporting", "forecasting", "budgeting", "procurement",
    "operations", "maintenance", "support", "troubleshooting", "escalation",
    "training", "enablement", "onboarding", "handover", "retrospective",
    # — craft, as concepts rather than tools —
    "architecture", "scalability", "reliability", "availability",
    "observability", "performance", "quality", "testing", "debugging",
    "refactoring", "deployment", "monitoring", "automation", "optimisation",
    "optimization", "migration", "integration", "accessibility",
    "localisation", "localization", "internationalisation",
    "internationalization", "privacy", "compliance", "audit", "risk",
    # — commercial —
    "analytics", "insights", "metrics", "benchmarking", "experimentation",
    "segmentation", "attribution", "personalisation", "personalization",
    "storytelling", "copywriting", "branding", "positioning", "messaging",
    "outreach", "prospecting", "negotiation", "retention", "acquisition",
    "engagement", "renewals", "churn", "revenue", "margin", "profitability",
    "reconciliation", "settlement", "invoicing", "payroll", "underwriting",
    "recruiting", "sourcing", "interviewing",
    # — Turkish —
    "paydaş", "paydaşlar", "iletişim", "işbirliği", "koordinasyon",
    "liderlik", "sahiplenme", "sorumluluk", "özerklik", "inisiyatif",
    "mentorluk", "koçluk", "ekip", "ortaklık", "şeffaflık", "empati",
    "uyum", "dayanıklılık", "merak", "geribildirim", "kültür", "çeşitlilik",
    "kapsayıcılık", "sürdürülebilirlik", "teslimat", "keşif", "planlama",
    "önceliklendirme", "strateji", "yürütme", "tahminleme", "yönetişim",
    "dokümantasyon", "raporlama", "bütçeleme", "operasyon", "bakım",
    "destek", "eğitim", "işealım", "devir", "mimari", "ölçeklenebilirlik",
    "güvenilirlik", "erişilebilirlik", "performans", "kalite", "test",
    "dağıtım", "izleme", "otomasyon", "optimizasyon", "taşıma", "entegrasyon",
    "yerelleştirme", "gizlilik", "mevzuat", "denetim", "risk", "analitik",
    "metrik", "deneyleme", "segmentasyon", "markalaşma", "konumlandırma",
    "müzakere", "elde", "kazanım", "bağlılık", "gelir", "kâr", "mutabakat",
    "faturalama", "bordro", "işealım",
)

#: Normalised, deduplicated, single tokens only. A multi-word entry would never
#: match here — phrases are handled by the phrase rule — so it is dropped
#: rather than silently stored where nothing can reach it.
CONCEPT_WORDS: Final[frozenset[str]] = frozenset(
    normalized
    for normalized in (normalize(entry) for entry in _SOURCE)
    if normalized and " " not in normalized
)


def is_concept(word: str) -> bool:
    """Whether ``word`` (already normalised) may be borrowed from a posting."""
    return word in CONCEPT_WORDS
