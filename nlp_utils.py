import re
from datetime import datetime, timedelta

CATEGORY_MAP = {
    "Food": [
        "pizza", "burger", "lunch", "dinner", "breakfast", "snack", "food",
        "groceries", "grocery", "restaurant", "paneer", "coffee", "tea",
        "cafe", "swiggy", "zomato", "biryani", "meal",
    ],
    "Transport": [
        "petrol", "diesel", "gas", "uber", "ola", "taxi", "bus", "train",
        "flight", "transport", "metro", "auto", "fuel", "parking",
    ],
    "Utilities": [
        "bill", "electricity", "water", "internet", "wifi", "rent",
        "utilities", "recharge", "mobile", "phone",
    ],
    "Entertainment": [
        "movie", "game", "concert", "ticket", "entertainment", "netflix",
        "spotify", "youtube", "party",
    ],
    "Health": [
        "doctor", "medicine", "hospital", "pharmacy", "health", "fitness",
        "gym", "medical",
    ],
    "Shopping": [
        "clothes", "cloths", "shoes", "electronics", "shopping", "amazon",
        "flipkart", "saree",
    ],
    "Stationery": [
        "pencil", "pen", "notebook", "stationary", "stationery", "book",
        "pencil-box",
    ],
    "Furniture": ["sofa", "bed", "table", "chair", "desk", "furniture", "cabinet"],
    "Education": ["tuition", "fees", "course", "college", "school", "exam"],
    "Salary": ["salary", "stipend", "payroll", "wage"],
}

INCOME_KEYWORDS = [
    "earned", "received", "salary", "income", "got paid", "credited",
    "freelance", "stipend", "bonus", "refund",
]
EXPENSE_KEYWORDS = [
    "spent", "paid", "bought", "purchase", "purchased", "cost", "bill",
]


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
        year, month, day = (int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
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

    months = {
        "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
        "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
        "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
        "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
    }
    named = re.search(
        r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\b",
        lowered,
    )
    if named:
        day = int(named.group(1))
        month = months[named.group(2)]
        year = today.year
        try:
            return datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            pass

    return None


def _mask_dates(text):
    masked = re.sub(r"\b\d{4}-\d{1,2}-\d{1,2}\b", " ", text)
    masked = re.sub(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", " ", masked)
    return masked


def _extract_amount(text):
    """Pick the most likely rupee amount, ignoring numbers that belong to dates."""
    search_text = _mask_dates(text)
    currency = re.search(
        r"(?:₹|rs\.?|inr)\s*(\d+(?:,\d{2,3})*(?:\.\d{1,2})?)",
        search_text,
        flags=re.IGNORECASE,
    )
    if currency:
        return float(currency.group(1).replace(",", ""))

    verb = re.search(
        r"(?:spent|paid|bought|cost|earned|received|got)\s+(?:₹|rs\.?|inr)?\s*(\d+(?:,\d{2,3})*(?:\.\d{1,2})?)",
        search_text,
        flags=re.IGNORECASE,
    )
    if verb:
        return float(verb.group(1).replace(",", ""))

    for_amount = re.search(
        r"(?:for|of)\s+(?:₹|rs\.?|inr)?\s*(\d+(?:,\d{2,3})*(?:\.\d{1,2})?)",
        search_text,
        flags=re.IGNORECASE,
    )
    if for_amount:
        return float(for_amount.group(1).replace(",", ""))

    numbers = re.findall(r"\d+(?:,\d{2,3})*(?:\.\d{1,2})?", search_text)
    if numbers:
        return float(numbers[0].replace(",", ""))
    return 0.0


def _extract_category(text):
    lowered = text.lower()
    for category, keywords in CATEGORY_MAP.items():
        if category.lower() in lowered:
            return category
        for keyword in keywords:
            if re.search(r"\b" + re.escape(keyword) + r"\b", lowered):
                return category
    return "Miscellaneous"


def _extract_type(text):
    lowered = text.lower()
    if any(word in lowered for word in INCOME_KEYWORDS):
        return "income"
    if any(word in lowered for word in EXPENSE_KEYWORDS):
        return "expense"
    return "expense"


def process_natural_language(text):
    """
    Parse a short English sentence into a transaction.

    Examples:
    - Spent ₹500 on dinner yesterday
    - Paid 120 for Uber today
    - Received salary 25000
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
    result["category"] = _extract_category(raw)
    result["tx_type"] = _extract_type(raw)

    if result["tx_type"] == "income" and result["category"] == "Miscellaneous":
        if "salary" in raw.lower():
            result["category"] = "Salary"
        else:
            result["category"] = "Income"

    return result
