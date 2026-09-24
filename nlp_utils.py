import re
from datetime import datetime, timedelta

CATEGORY_MAP = {
    "Food": [
        "pizza", "burger", "lunch", "dinner", "breakfast", "snack", "food",
        "groceries", "grocery", "restaurant", "paneer", "coffee", "tea",
        "cafe", "swiggy", "zomato", "biryani", "meal", "dosa", "idli",
        "fruits", "vegetables", "milk", "bread",
    ],
    "Transport": [
        "petrol", "diesel", "gas", "uber", "ola", "taxi", "bus", "train",
        "flight", "transport", "metro", "auto", "fuel", "parking", "car",
        "bike", "vehicle", "cab", "rickshaw", "toll", "rapido",
    ],
    "Utilities": [
        "bill", "electricity", "water", "internet", "wifi", "rent",
        "utilities", "recharge", "mobile", "phone", "lpg", "cylinder",
        "broadband", "dth", "maintenance",
    ],
    "Entertainment": [
        "movie", "game", "concert", "ticket", "entertainment", "netflix",
        "spotify", "youtube", "party", "cinema", "prime", "hotstar", "gaming",
    ],
    "Health": [
        "doctor", "medicine", "hospital", "pharmacy", "checkup", "test",
        "tablet", "pharma", "treatment", "health", "fitness", "gym", "medical",
        "dentist", "consultation", "clinic",
    ],
    "Shopping": [
        "clothes", "cloths", "shoes", "electronics", "shopping", "amazon",
        "flipkart", "saree", "dress", "shirt", "jeans", "watch", "myntra",
    ],
    "Stationery": [
        "pencil", "pen", "notebook", "stationary", "stationery", "book",
        "pencil-box", "paper", "marker", "calculator",
    ],
    "Furniture": ["sofa", "bed", "table", "chair", "desk", "furniture", "cabinet", "wardrobe"],
    "Education": ["tuition", "fees", "course", "college", "school", "exam", "udemy", "coursera", "coaching"],
    "Investment": [
        "property", "flat", "apartment", "land", "plot", "real estate",
        "mutual fund", "stocks", "shares", "crypto", "bitcoin", "gold", "silver",
        "sip", "fixed deposit", "fd", "bonds",
    ],
    "Agriculture": [
        "tractor", "fertilizer", "seeds", "pesticide", "irrigation", "crop",
        "urea", "farming", "farm", "khatar",
    ],
    "Industrial": [
        "machinery", "tools", "raw material", "factory", "equipment", "hardware",
        "bearing", "motor", "sheet metal",
    ],
    "Spiritual & Religious": [
        "temple", "pooja", "prasad", "donation", "trust", "incense",
        "agarbatti", "spiritual", "ashram", "puja",
    ],
    "Sports & Fitness": [
        "cricket", "bat", "ball", "gym", "gripper", "badminton", "shoes",
        "workout", "protein", "football",
    ],
    "Salary": ["salary", "stipend", "payroll", "wage"],
}

INCOME_KEYWORDS = [
    "earned", "received", "salary", "income", "got paid", "credited",
    "freelance", "stipend", "bonus", "refund", "dividend", "cashback", "interest",
]
EXPENSE_KEYWORDS = [
    "spent", "paid", "bought", "purchase", "purchased", "cost", "bill",
    "ordered", "shopping for", "gave",
]

MONTH_DICT = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}


def _extract_date(text):
    """Return YYYY-MM-DD if the sentence mentions a date, otherwise None."""
    today = datetime.now().date()
    lowered = text.lower()

    if "day after tomorrow" in lowered:
        return (today + timedelta(days=2)).strftime("%Y-%m-%d")
    if "day before yesterday" in lowered:
        return (today - timedelta(days=2)).strftime("%Y-%m-%d")
    if "yesterday" in lowered:
        return (today - timedelta(days=1)).strftime("%Y-%m-%d")
    if "tomorrow" in lowered:
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")
    if "today" in lowered:
        return today.strftime("%Y-%m-%d")

    iso = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", text)
    if iso:
        year, month, day = int(iso.group(1)), int(iso.group(2)), int(iso.group(3))
        try:
            return datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            pass

    dmy = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b", text)
    if dmy:
        day, month, year = int(dmy.group(1)), int(dmy.group(2)), int(dmy.group(3))
        if year < 100:
            year += 2000
        try:
            return datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            pass

    month_names_pattern = "|".join(MONTH_DICT.keys())
    # Format: 24th September 2026 or 24 Sep 2026 or 24 September
    named1 = re.search(
        rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({month_names_pattern})(?:\s+(\d{{2,4}}))?\b",
        lowered,
    )
    if named1:
        day = int(named1.group(1))
        month = MONTH_DICT[named1.group(2)]
        raw_year = named1.group(3)
        year = int(raw_year) if raw_year else today.year
        if year < 100:
            year += 2000
        try:
            return datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # Format: September 24, 2026 or Sep 24
    named2 = re.search(
        rf"\b({month_names_pattern})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:\s*,?\s*(\d{{2,4}}))?\b",
        lowered,
    )
    if named2:
        month = MONTH_DICT[named2.group(1)]
        day = int(named2.group(2))
        raw_year = named2.group(3)
        year = int(raw_year) if raw_year else today.year
        if year < 100:
            year += 2000
        try:
            return datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            pass

    return None


def _mask_dates(text):
    """Replace all date representations with spaces so numbers in dates are not parsed as amounts."""
    masked = re.sub(r"\b\d{4}-\d{1,2}-\d{1,2}\b", " ", text)
    masked = re.sub(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", " ", masked)
    month_names_pattern = "|".join(MONTH_DICT.keys())
    masked = re.sub(
        rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{month_names_pattern})(?:\s+\d{{2,4}})?\b",
        " ",
        masked,
        flags=re.IGNORECASE,
    )
    masked = re.sub(
        rf"\b(?:{month_names_pattern})\s+\d{{1,2}}(?:st|nd|rd|th)?(?:\s*,?\s*\d{{2,4}})?\b",
        " ",
        masked,
        flags=re.IGNORECASE,
    )
    return masked


def _parse_raw_number(num_str):
    try:
        return float(num_str.replace(",", "").strip())
    except (ValueError, TypeError):
        return 0.0


def _extract_amount(text):
    """
    Pick the most likely monetary amount.
    Supports:
    - ₹, Rs, Rs., rupees, inr (prefix or suffix)
    - Indian comma formatting (1,200 or 1,00,000)
    - Multipliers: k, thousand, lakh, lac, lacs, crore, cr
    - Decimals: 2.5k, 2.5 lakh, 2.5 cr, 99.50
    """
    search_text = _mask_dates(text)

    # 1. Multipliers: 5k, 2.5k, 5 thousand, 5 lakh, 5 lac, 5 lacs, 2.5 lakh, 1 crore, 2.5 cr
    mult_pattern = (
        r"(?:₹|rs\.?|inr)?\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*"
        r"(k|thousand|lakhs?|lacs?|crores?|cr)\b"
    )
    match = re.search(mult_pattern, search_text, flags=re.IGNORECASE)
    if match:
        base = _parse_raw_number(match.group(1))
        unit = match.group(2).lower()
        if unit in ("k", "thousand"):
            return round(base * 1000, 2)
        elif unit in ("lakh", "lakhs", "lac", "lacs"):
            return round(base * 100000, 2)
        elif unit in ("crore", "crores", "cr"):
            return round(base * 10000000, 2)

    # 2. Suffix currency: 1,200 rupees, 500 rs, 500/-, 500 inr
    suffix_pattern = (
        r"(\d+(?:,\d+)*(?:\.\d+)?)\s*"
        r"(?:rupees?|rs\.?|inr|\/-)\b"
    )
    match = re.search(suffix_pattern, search_text, flags=re.IGNORECASE)
    if match:
        return _parse_raw_number(match.group(1))

    # 3. Prefix currency: ₹500, Rs. 500, Rs 500, inr 500, ₹ 1,200
    prefix_pattern = (
        r"(?:₹|rs\.?|inr|rupees?)\s*"
        r"(\d+(?:,\d+)*(?:\.\d+)?)"
    )
    match = re.search(prefix_pattern, search_text, flags=re.IGNORECASE)
    if match:
        return _parse_raw_number(match.group(1))

    # 4. Context verbs/prepositions: spent 500, paid 120, bought 850, for 1200, of 400, received 25000, salary 25000
    context_pattern = (
        r"(?:spent|paid|bought|cost|earned|received|salary|for|of)\s+"
        r"(?:₹|rs\.?|inr)?\s*(\d+(?:,\d+)*(?:\.\d+)?)"
    )
    match = re.search(context_pattern, search_text, flags=re.IGNORECASE)
    if match:
        return _parse_raw_number(match.group(1))

    # 5. Suffix verbs: 500 spent, 120 paid, 25000 credited
    suffix_verb_pattern = (
        r"(\d+(?:,\d+)*(?:\.\d+)?)\s*"
        r"(?:spent|paid|credited|debited)\b"
    )
    match = re.search(suffix_verb_pattern, search_text, flags=re.IGNORECASE)
    if match:
        return _parse_raw_number(match.group(1))

    # 6. Fallback: first isolated number
    numbers = re.findall(r"\b\d+(?:,\d+)*(?:\.\d+)?\b", search_text)
    if numbers:
        return _parse_raw_number(numbers[0])

    return 0.0


def _extract_category(text, user_id=None):
    lowered = text.lower()
    if user_id:
        try:
            from db_manager import get_user_keywords
            user_kws = get_user_keywords(user_id)
            tokens = re.findall(r"[a-zA-Z0-9]+", lowered)
            for token in tokens:
                if token in user_kws:
                    return user_kws[token]
        except Exception as e:
            print(f"[SmartSpend] Error loading user keywords for NLP lookup: {e}")

    for category, keywords in CATEGORY_MAP.items():
        if category.lower() in lowered:
            return category
        for keyword in keywords:
            if re.search(r"\b" + re.escape(keyword) + r"\b", lowered):
                return category
    return "Miscellaneous"


def _extract_type(text):
    lowered = text.lower()
    if any(re.search(r"\b" + re.escape(w) + r"\b", lowered) for w in INCOME_KEYWORDS):
        return "income"
    if any(re.search(r"\b" + re.escape(w) + r"\b", lowered) for w in EXPENSE_KEYWORDS):
        return "expense"
    return "expense"


def process_natural_language(text, user_id=None):
    """
    Parse a natural language financial sentence into structured transaction data.

    Examples:
    - 'Spent ₹500 on dinner yesterday'
    - 'Paid 120 for Uber today'
    - 'Received salary 25000'
    - 'Bought groceries for 1,200 rupees'
    - 'Spent 5k on shopping'
    - 'Spent 2.5k on food'
    - 'Paid 5 thousand for rent'
    - 'Spent 5 lakh on a car'
    - 'Spent 2.5 cr on property'
    """
    raw = (text or "").strip()
    result = {
        "amount": 0.0,
        "category": "Miscellaneous",
        "description": raw,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "tx_type": "expense",
        "date_from_text": False,
    }
    if not raw:
        return result

    parsed_date = _extract_date(raw)
    if parsed_date:
        result["date"] = parsed_date
        result["date_from_text"] = True

    result["amount"] = _extract_amount(raw)
    result["category"] = _extract_category(raw, user_id=user_id)
    result["tx_type"] = _extract_type(raw)

    if result["tx_type"] == "income" and result["category"] == "Miscellaneous":
        if "salary" in raw.lower():
            result["category"] = "Salary"
        else:
            result["category"] = "Income"

    return result
