ENTITY_PATTERNS = {
    "Account": ["account", "acct", "ledger", "gl_"],
    "Asset": ["asset", "equipment", "device"],
    "Budget": ["budget", "forecast", "plan"],
    "Case": ["case", "incident", "ticket", "request"],
    "Claim": ["claim", "authorization", "encounter"],
    "Cost Center": ["cost_center", "cost centre", "department_code"],
    "Employee": ["employee", "worker", "staff", "associate"],
    "Inventory Item": ["inventory", "stock", "sku", "item"],
    "Journal Entry": ["journal", "journal_entry", "journal_entries", "entry_id"],
    "Location": ["location", "site", "branch", "warehouse", "store"],
    "Mapping": ["mapping", "crosswalk", "lookup", "xref"],
    "Patient": ["patient", "member", "subscriber"],
    "Payment": ["payment", "receipt", "remittance"],
    "Policy": ["policy", "coverage", "premium"],
    "Product": ["product", "material", "part_number", "part_id"],
    "Project": ["project", "initiative", "workstream"],
    "Shipment": ["shipment", "delivery", "carrier", "tracking"],
    "Student": ["student", "learner", "enrollment"],
    "Transaction": ["transaction", "txn"],
    "Customer": ["customer", "cust", "client", "res_partner"],
    "Supplier": ["supplier", "vendor"],
    "Invoice": ["invoice", "bill"],
    "Order": ["order", "sales_order"],
    "Funding": ["funding", "grant"],
    "Service": ["service"],
    "Program": ["program"],
    "Contract": ["contract", "agreement"],
}

GENERIC_PREFIXES = {"raw", "stg", "stage", "staging", "src", "source", "dim", "fact", "ref", "hub", "sat", "link"}
GENERIC_SUFFIXES = {"data", "dataset", "table", "list", "upload", "manual", "master", "detail", "details", "history", "hist", "log", "logs", "entries", "records"}
TECHNICAL_TOKENS = {"id", "key", "code", "date", "time", "timestamp", "created", "updated", "modified", "deleted", "flag", "status", "type"}


def detect_entity(table_name: str, column_names: list[str]) -> str | None:
    table_haystack = table_name.lower()
    haystack = " ".join([table_name, *column_names]).lower()
    for entity, patterns in sorted(ENTITY_PATTERNS.items(), key=lambda item: _specificity(item[1]), reverse=True):
        if any(_matches_pattern(pattern, table_haystack) for pattern in patterns):
            return entity
    for entity, patterns in sorted(ENTITY_PATTERNS.items(), key=lambda item: _specificity(item[1]), reverse=True):
        if any(_matches_pattern(pattern, haystack) for pattern in patterns):
            return entity
    return _entity_from_table_name(table_name)


def _specificity(patterns: list[str]) -> int:
    return max((len(pattern) for pattern in patterns), default=0)


def _matches_pattern(pattern: str, haystack: str) -> bool:
    if pattern.endswith("_"):
        return pattern in haystack.replace(" ", "_")
    return pattern in haystack


def _entity_from_table_name(table_name: str) -> str | None:
    tokens = [token for token in table_name.lower().replace("-", "_").split("_") if token]
    while tokens and tokens[0] in GENERIC_PREFIXES:
        tokens.pop(0)
    while tokens and tokens[-1] in GENERIC_SUFFIXES:
        tokens.pop()
    business_tokens = [token for token in tokens if token not in TECHNICAL_TOKENS and not token.isdigit()]
    if not business_tokens:
        return None
    if len(business_tokens) > 3:
        business_tokens = business_tokens[:3]
    return " ".join(_humanize_token(token) for token in business_tokens)


def _humanize_token(token: str) -> str:
    acronyms = {"ap": "AP", "ar": "AR", "gl": "GL", "hr": "HR", "sku": "SKU", "pnl": "P&L"}
    if token in acronyms:
        return acronyms[token]
    if token.endswith("ies") and len(token) > 3:
        token = f"{token[:-3]}y"
    elif token.endswith("s") and len(token) > 3:
        token = token[:-1]
    return token.capitalize()
