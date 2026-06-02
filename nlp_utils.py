import re

def process_natural_language(text):
    """
    Parses a single string to extract expense amount, category, and description.
    
    System Design:
    - This function acts as the Natural Language Processing (NLP) component of the 
      input subsystem. It uses local pattern matching without external APIs.
      
    System Analysis:
    - Inputs: Raw string (e.g., "Spent 500 for Pizza")
    - Process: Regex extraction for numeric amounts and keyword scanning for categories.
    - Outputs: A dictionary containing amount, category, and description.
    """
    
    result = {
        'amount': 0.0,
        'category': 'Miscellaneous',
        'description': text.strip()
    }
    
    # Extract amount using Regex: looks for numbers possibly containing decimals
    amount_match = re.search(r'\d+(\.\d+)?', text)
    if amount_match:
        result['amount'] = float(amount_match.group())
        
    # Basic string tokenization / keyword scanning for Categories
    # We define a simple mapping of keywords to canonical categories
    category_map = {
        'food': ['pizza', 'burger', 'lunch', 'dinner', 'breakfast', 'snack', 'food', 'groceries', 'restaurant', 'paneer'],
        'transport': ['petrol', 'gas', 'uber', 'taxi', 'bus', 'train', 'flight', 'transport'],
        'utilities': ['bill', 'electricity', 'water', 'internet', 'wifi', 'rent', 'utilities'],
        'entertainment': ['movie', 'game', 'concert', 'ticket', 'entertainment'],
        'health': ['doctor', 'medicine', 'hospital', 'pharmacy', 'health', 'fitness', 'gym'],
        'shopping': ['clothes', 'shoes', 'electronics', 'shopping', 'amazon'],
        'stationary': ['pencil', 'pen', 'notebook', 'stationary', 'pencil-box', 'stationery', 'book'],
        'furniture': ['sofa', 'bed', 'table', 'chair', 'desk', 'furniture', 'cabinet']
    }
    
    text_lower = text.lower()
    
    # Search for canonical categories first
    for cat in category_map.keys():
        if cat in text_lower:
            result['category'] = cat.capitalize()
            return result
            
    # Search for related keywords
    for cat, keywords in category_map.items():
        for keyword in keywords:
            if keyword in text_lower:
                result['category'] = cat.capitalize()
                return result
                
    return result
