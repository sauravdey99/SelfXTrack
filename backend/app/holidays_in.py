"""Indian public holidays used to pause routine AI alerts (parents can switch this off per child).
2026: Central Government gazetted holidays (DoPT order of 3 July 2025, Delhi list).
Moon-based dates (Id, Muharram, Milad) can shift by a day. Add next year's list when DoPT publishes it."""
HOLIDAYS = {
    "2026-01-26": "Republic Day", "2026-03-04": "Holi", "2026-03-21": "Id-ul-Fitr", "2026-03-26": "Ram Navami",
    "2026-03-31": "Mahavir Jayanti", "2026-04-03": "Good Friday", "2026-05-01": "Buddha Purnima",
    "2026-05-27": "Id-ul-Zuha (Bakrid)", "2026-06-26": "Muharram", "2026-08-15": "Independence Day",
    "2026-08-26": "Milad-un-Nabi", "2026-09-04": "Janmashtami", "2026-10-02": "Gandhi Jayanti",
    "2026-10-20": "Dussehra", "2026-11-08": "Diwali", "2026-11-24": "Guru Nanak Jayanti", "2026-12-25": "Christmas",
    # fixed-date national holidays (every year)
    "2027-01-26": "Republic Day", "2027-08-15": "Independence Day", "2027-10-02": "Gandhi Jayanti",
    "2027-12-25": "Christmas",
}


def public_holiday(day_iso: str) -> str | None:
    return HOLIDAYS.get(day_iso)
