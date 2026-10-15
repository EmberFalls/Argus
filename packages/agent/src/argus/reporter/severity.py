def severity_for(category: str) -> str:
    return {"data_loss": "P1", "security": "P0", "functional": "P2", "cosmetic": "P3"}.get(category, "P2")
