import os

CII_TABLE = {
    "2020-21": float(os.getenv('CII_2020_21', '301')),
    "2021-22": float(os.getenv('CII_2021_22', '317')),
    "2022-23": float(os.getenv('CII_2022_23', '331')),
    "2023-24": float(os.getenv('CII_2023_24', '348')),
    "2024-25": float(os.getenv('CII_2024_25', '363')),
    "2025-26": float(os.getenv('CII_2025_26', '377')),
    "2026-27": float(os.getenv('CII_2026_27', '390'))
}
