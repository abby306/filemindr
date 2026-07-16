"""Predefined document classes seeded into every account.

The catalog is a **two-level taxonomy**: ~20 broad parent categories, each with a
handful of specific subclasses (leaves). `parent` is the slug of the parent class
(``None`` for a top-level category). Both parents and leaves are selectable slugs,
so a document can be labelled at parent level when no subclass fits.

`description` is intentionally rich — it feeds the extraction-time classifier, so
each line should read like a short instruction about what belongs in the class.
Accounts may add their own custom classes on top of these system ones.

Backward compatibility: the original flat slugs (`invoice`, `receipt`, `contract`,
`bank_statement`, `payslip`, `resume`, `warranty`, `insurance`, `utility_bill`,
`report`, …) are preserved as either parents or leaves, so existing
`document_classes` links stay valid. A few legacy slugs (`id_document`,
`tax_document`, `medical_record`, `letter`) are superseded by richer categories
but are never deleted — the seed is additive.
"""

from __future__ import annotations

from typing import NamedTuple


class ClassSeed(NamedTuple):
    slug: str
    name: str
    description: str
    parent: str | None = None  # slug of the parent category, or None for a root


# Parents are listed immediately before their children for readability; the seed
# resolves `parent` slugs to ids regardless of ordering.
DEFAULT_CLASSES: tuple[ClassSeed, ...] = (
    # --- financial ---------------------------------------------------------
    ClassSeed("financial", "Financial", "Money-related documents: bills, statements, and proof of payment."),
    ClassSeed("invoice", "Invoice", "A bill requesting payment for goods or services, with line items, totals, and a due date.", "financial"),
    ClassSeed("receipt", "Receipt", "Proof of a completed payment or purchase, showing amount paid, date, and merchant.", "financial"),
    ClassSeed("bank_statement", "Bank Statement", "A periodic summary of account transactions, balances, and fees from a bank.", "financial"),
    # --- tax ---------------------------------------------------------------
    ClassSeed("tax", "Tax", "Tax-related forms, filings, and assessments."),
    ClassSeed("tax_return", "Tax Return", "A filed income-tax return summarizing income, deductions, and tax owed or refunded.", "tax"),
    ClassSeed("tax_form", "Tax Form", "An informational tax form such as a W-2, 1099, or VAT statement reporting income or withholding.", "tax"),
    # --- legal -------------------------------------------------------------
    ClassSeed("legal", "Legal", "Legally binding or official legal documents."),
    ClassSeed("contract", "Contract", "A legally binding agreement between parties, with terms, obligations, and signatures.", "legal"),
    ClassSeed("nda", "NDA", "A non-disclosure or confidentiality agreement restricting the sharing of information.", "legal"),
    ClassSeed("court_document", "Court Document", "A filing, ruling, subpoena, or other document from a legal proceeding.", "legal"),
    # --- identity ----------------------------------------------------------
    ClassSeed("identity", "Identity", "Official identification documents for a person."),
    ClassSeed("passport", "Passport", "A government-issued passport used for international travel and identification.", "identity"),
    ClassSeed("drivers_license", "Driver's License", "A license authorizing a person to drive, also used as photo identification.", "identity"),
    ClassSeed("national_id", "National ID", "A national identity card or equivalent government-issued ID.", "identity"),
    # --- insurance ---------------------------------------------------------
    ClassSeed("insurance", "Insurance", "Insurance policies, certificates, and claims."),
    ClassSeed("health_insurance", "Health Insurance", "A health, dental, or medical insurance policy, card, or claim.", "insurance"),
    ClassSeed("auto_insurance", "Auto Insurance", "A vehicle insurance policy, certificate, or claim.", "insurance"),
    # --- medical -----------------------------------------------------------
    ClassSeed("medical", "Medical", "Clinical and health records."),
    ClassSeed("lab_result", "Lab Result", "Laboratory or diagnostic test results with measured values and reference ranges.", "medical"),
    ClassSeed("prescription", "Prescription", "A prescription for medication, listing drug, dose, and prescriber.", "medical"),
    ClassSeed("discharge_summary", "Discharge Summary", "A clinical summary of a hospital stay, diagnosis, and follow-up.", "medical"),
    # --- utility bills -----------------------------------------------------
    ClassSeed("utility_bill", "Utility Bill", "A recurring service bill for a household or business."),
    ClassSeed("electricity_bill", "Electricity / Gas Bill", "A bill for electricity, gas, or water service with usage and charges.", "utility_bill"),
    ClassSeed("internet_phone_bill", "Internet / Phone Bill", "A bill for internet, mobile, or landline phone service with usage and charges.", "utility_bill"),
    # --- employment --------------------------------------------------------
    ClassSeed("employment", "Employment", "Work and hiring documents."),
    ClassSeed("offer_letter", "Offer Letter", "A job offer stating role, compensation, and start date.", "employment"),
    ClassSeed("payslip", "Payslip", "An employer's record of wages for a pay period, with gross pay, deductions, and net pay.", "employment"),
    ClassSeed("resume", "Resume / CV", "A summary of a person's work experience, education, and skills.", "employment"),
    # --- education ---------------------------------------------------------
    ClassSeed("education", "Education", "Academic and learning documents."),
    ClassSeed("transcript", "Transcript", "An academic transcript listing courses and grades.", "education"),
    ClassSeed("certificate", "Certificate", "A certificate of completion, award, or professional qualification.", "education"),
    ClassSeed("thesis_dissertation", "Thesis / Dissertation", "A thesis, dissertation, or long-form academic research document.", "education"),
    # --- real estate -------------------------------------------------------
    ClassSeed("real_estate", "Real Estate", "Property ownership and tenancy documents."),
    ClassSeed("lease", "Lease", "A rental or lease agreement for property, with term and rent.", "real_estate"),
    ClassSeed("deed", "Deed", "A deed or title transferring or evidencing ownership of property.", "real_estate"),
    ClassSeed("mortgage", "Mortgage", "A mortgage or home-loan agreement and its statements.", "real_estate"),
    # --- business ----------------------------------------------------------
    ClassSeed("business", "Business", "Commercial and operational business documents."),
    ClassSeed("purchase_order", "Purchase Order", "A purchase order authorizing a purchase with items, quantities, and prices.", "business"),
    ClassSeed("quote_estimate", "Quote / Estimate", "A price quote or estimate for goods or services, not yet a bill.", "business"),
    # --- technical ---------------------------------------------------------
    ClassSeed("technical", "Technical", "Engineering, software, and research technical documents."),
    ClassSeed("technical_spec", "Technical Spec", "A technical specification or requirements document for a system or product.", "technical"),
    ClassSeed("design_document", "Design Document", "An architecture or design document describing how something is built.", "technical"),
    ClassSeed("research_paper", "Research Paper", "A scientific or technical paper presenting original research and results.", "technical"),
    # --- correspondence ----------------------------------------------------
    ClassSeed("correspondence", "Correspondence", "Letters and written communication."),
    ClassSeed("formal_letter", "Formal Letter", "Formal or business correspondence addressed to a recipient.", "correspondence"),
    ClassSeed("email", "Email", "An email message or printed email thread.", "correspondence"),
    # --- warranty / product ------------------------------------------------
    ClassSeed("warranty_product", "Warranty / Product", "Product ownership, warranty, and support documents."),
    ClassSeed("warranty", "Warranty", "A guarantee covering repair or replacement of a product for a stated period.", "warranty_product"),
    ClassSeed("product_manual", "Product Manual", "A user manual, guide, or instructions for a product.", "warranty_product"),
    # --- travel ------------------------------------------------------------
    ClassSeed("travel", "Travel", "Trip and travel-related documents."),
    ClassSeed("itinerary", "Itinerary", "A travel itinerary listing flights, dates, and reservations.", "travel"),
    ClassSeed("boarding_pass", "Boarding Pass", "A boarding pass or ticket for a flight, train, or other transport.", "travel"),
    # --- government --------------------------------------------------------
    ClassSeed("government", "Government", "Official government-issued documents and notices."),
    ClassSeed("permit", "Permit", "A permit or license granting official permission for an activity.", "government"),
    ClassSeed("government_notice", "Government Notice", "An official notice, letter, or assessment from a government agency.", "government"),
    # --- marketing ---------------------------------------------------------
    ClassSeed("marketing", "Marketing", "Promotional and outreach materials."),
    ClassSeed("brochure", "Brochure", "A brochure, flyer, or promotional leaflet.", "marketing"),
    ClassSeed("presentation", "Presentation", "A slide deck or presentation.", "marketing"),
    # --- personal ----------------------------------------------------------
    ClassSeed("personal", "Personal", "Personal notes and everyday documents."),
    ClassSeed("notes_journal", "Notes / Journal", "Personal notes, a journal entry, or handwritten memos.", "personal"),
    ClassSeed("recipe", "Recipe", "A cooking recipe with ingredients and instructions.", "personal"),
    # --- reports -----------------------------------------------------------
    ClassSeed("report", "Report", "An analytical or informational document presenting findings, metrics, or research."),
    ClassSeed("financial_report", "Financial Report", "A financial report such as a P&L, balance sheet, or earnings summary.", "report"),
    ClassSeed("analytics_report", "Analytics Report", "A metrics, performance, or analytics report presenting data and findings.", "report"),
    # --- other -------------------------------------------------------------
    ClassSeed("other", "Other", "Documents that don't fit another category."),
    ClassSeed("screenshot", "Screenshot", "A screenshot or captured image of a screen.", "other"),
    ClassSeed("blank_form", "Blank Form", "An empty or unfilled form or template.", "other"),
)
