ENTITY_PATTERNS = {
    "Customer": ["customer", "cust", "client", "res_partner"],
    "Supplier": ["supplier", "vendor"],
    "Invoice": ["invoice", "bill"],
    "Order": ["order", "sales_order"],
    "Funding": ["funding", "grant"],
    "Service": ["service"],
    "Program": ["program"],
    "Contract": ["contract", "agreement"],
}


def detect_entity(table_name: str, column_names: list[str]) -> str | None:
    haystack = " ".join([table_name, *column_names]).lower()
    for entity, patterns in ENTITY_PATTERNS.items():
        if any(pattern in haystack for pattern in patterns):
            return entity
    return None
