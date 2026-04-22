"""
Index legal documents into ChromaDB for RAG retrieval.

Sources indexed:
- Key BGB sections (§307, §551, §573c, §74 HGB)
- BGH rulings on Schönheitsreparaturen (cosmetic repairs)
- GDPR/DSGVO requirements for employment contracts

Run with: python scripts/index_legal_docs.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.legal.knowledge_base import LegalKnowledgeBase

LEGAL_DOCUMENTS = [
    {
        "id": "bgb_307",
        "source": "BGB §307 - Inhaltskontrolle",
        "content": """BGB §307 Controls on the content of standard terms.
(1) Provisions in standard terms and conditions are ineffective if, contrary to the requirement
of good faith, they unreasonably disadvantage the other party to the contract. Unreasonable
disadvantage may also arise from a provision not being clear and comprehensible.
(2) In case of doubt, an unreasonable disadvantage exists if a provision is incompatible with
essential principles of the statutory provision from which it deviates, or if it restricts
essential rights or duties inherent in the nature of the contract to such an extent that
attainment of the contractual purpose is jeopardized.
Applies to: All contracts with consumers. Key basis for voiding unfair standard terms.""",
        "contract_type": "all",
        "category": "general",
    },
    {
        "id": "bgb_551",
        "source": "BGB §551 - Begrenzung und Anlage von Mietsicherheiten",
        "content": """BGB §551 Limitation and investment of rental security deposits.
(1) If the tenant is obligated to provide the landlord with a security deposit for the claims
arising from the tenancy, the security deposit may not exceed three times the monthly rent
not including the amounts payable for operating costs (Kaltmiete).
(2) If the tenant transfers the security deposit in cash, the landlord must invest the deposit
separately from his assets in a savings account with a statutory notice period at the usual rate.
Key rule: Maximum deposit = 3 months Kaltmiete (net cold rent). Any higher amount is void.""",
        "contract_type": "rental",
        "category": "financial",
    },
    {
        "id": "bgb_573c",
        "source": "BGB §573c - Kündigungsfristen bei der Wohnraummiete",
        "content": """BGB §573c Notice periods for residential tenancies.
(1) The notice period for the tenant is three months. For the landlord, the notice period is
three months, and it increases by three months after five years and eight years of the tenancy.
(2) Shorter notice periods for both parties may only be agreed for the case of termination by
the tenant; the notice period may be reduced to one month.
Key rule: Tenant minimum notice = 3 months. Landlord minimum = 3 months (increases with duration).
Any clause requiring tenant to give more than 3 months notice is unfavorable_but_valid (not void)
unless it makes the notice period rigid in a way that violates BGB §307.""",
        "contract_type": "rental",
        "category": "termination",
    },
    {
        "id": "bgb_schoenheitsrep",
        "source": "BGH Rulings on Schönheitsreparaturen (Cosmetic Repairs)",
        "content": """BGH (Federal Court of Justice) has ruled in multiple decisions that:
1. Rigid renovation schedule clauses (Fristenplan) are void per BGB §307 (BGH VIII ZR 215/12, BGH VIII ZR 398/12).
   Example of void clause: "Der Mieter ist verpflichtet, Schönheitsreparaturen in Küche und Bad alle 3 Jahre
   und in den übrigen Räumen alle 5 Jahre durchzuführen."
2. Clauses requiring renovation at the end of tenancy regardless of actual wear are void (BGH VIII ZR 152/15).
3. Clauses requiring renovation upon moving in (Anfangsrenovierung) are void (BGH VIII ZR 199/13).
4. A quota renovation clause (Quotenabgeltungsklausel) is void (BGH VIII ZR 88/13).
Result: If a rental contract contains ANY cosmetic repair clause with rigid timelines, it is VOID.
The tenant is not legally required to renovate according to these schedules.""",
        "contract_type": "rental",
        "category": "repairs",
    },
    {
        "id": "hgb_74_non_compete",
        "source": "HGB §74 - Post-contractual non-compete clauses",
        "content": """HGB §74 Post-contractual non-compete obligation (Wettbewerbsverbot).
(1) An agreement restricting a commercial employee from competitive activity after termination
of the employment relationship (post-contractual non-compete) is only binding on the employee
if the employer undertakes to pay a compensation for the duration of the restriction.
(2) The compensation must amount to at least one half of the contractual payments last received
by the employee.
Key rule: A non-compete clause without at least 50% compensation payment is NOT ENFORCEABLE.
The employee can simply ignore it. Maximum duration: 2 years (HGB §74a).""",
        "contract_type": "employment",
        "category": "non_compete",
    },
    {
        "id": "gdpr_employment",
        "source": "DSGVO/GDPR - Data processing in employment contracts",
        "content": """GDPR (DSGVO) requirements for data processing clauses in employment contracts:
- Art. 13 GDPR: Employees must be informed about data processing at the time of hiring.
- Art. 6(1)(b) GDPR: Processing necessary for contract performance is lawful without consent.
- Art. 6(1)(a) GDPR: Consent is valid only if freely given — employees cannot truly freely
  consent due to power imbalance; consent-based processing is therefore risky for employers.
- Monitoring of employees (email, phone, location) requires legal basis beyond consent.
Key check: Clauses requiring employees to "consent" to broad data processing are likely invalid.
Data processing clauses should cite Art. 6(1)(b) (necessity) not consent.""",
        "contract_type": "employment",
        "category": "privacy",
    },
]


def main():
    kb = LegalKnowledgeBase()
    print(f"Indexing {len(LEGAL_DOCUMENTS)} legal documents...")

    for doc in LEGAL_DOCUMENTS:
        kb.collection.upsert(
            ids=[doc["id"]],
            documents=[doc["content"]],
            metadatas=[{
                "source": doc["source"],
                "contract_type": doc["contract_type"],
                "category": doc["category"],
            }],
        )
        print(f"  Indexed: {doc['source']}")

    print(f"\nDone. Total documents in knowledge base: {kb.collection.count()}")


if __name__ == "__main__":
    main()
