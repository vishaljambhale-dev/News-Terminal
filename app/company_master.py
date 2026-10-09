BUILTIN_ALIASES = {
    "RELIANCE": ["Reliance Industries", "RIL"],
    "TCS": ["Tata Consultancy Services", "TCS"],
    "INFY": ["Infosys"],
    "HDFCBANK": ["HDFC Bank"],
    "ICICIBANK": ["ICICI Bank"],
    "SBIN": ["State Bank of India", "SBI"],
    "TATAMOTORS": ["Tata Motors", "JLR", "Jaguar Land Rover"],
}

class CompanyMaster:
    def __init__(self, symbols):
        self.symbols = symbols
        self.alias_map = {}
        for sym in symbols:
            aliases = BUILTIN_ALIASES.get(sym, [sym])
            if sym not in aliases:
                aliases.append(sym)
            self.alias_map[sym] = [a.lower() for a in aliases]

    def match_symbol(self, text):
        text_lower = text.lower()
        matched = []
        for sym, aliases in self.alias_map.items():
            if any(alias in text_lower for alias in aliases):
                matched.append(sym)
        return matched
