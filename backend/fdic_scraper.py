import requests
import pandas as pd
import io

API_URL = "https://banks.data.fdic.gov/api/financials"
SUMMARY_URL = "https://banks.data.fdic.gov/api/institutions"

selected_fields = [
    "REPDTE", "CERT", "ASSET", "LNLSGR", "SC", "CHBALI", "DEP", "BRO", "OTHBRF",
    "EQTOT", "LNRECONS", "LNREMULT", "LNCOMRE", "LNRENROT", "LNATRES", "RBCT1J",
    "NIMY", "NETINC", "PTAXNETINC", "IGLSEC", "SCHTMRES", "ELNATR", "NTLNLS",
    "P9ASSET", "NAASSET", "NCLNLSR", "ORE", "INTAN", "RBC1AAJ", "IDT1CER",
    "IDT1RWAJR", "RBCRWAJ", "EQCBHCTR", "ROA", "ROE", "EEFFR", "ITAX", "ITAXR"
]

def fetch_fdic_data(cert):
    params = {
        "filters": f"CERT:{cert}",
        "fields": ",".join(selected_fields),
        "sort_by": "REPDTE",
        "sort_order": "DESC",
        "limit": "10000",
        "offset": "0",
        "format": "json"
    }
    try:
        response = requests.get(API_URL, params=params)
        if response.status_code == 200:
            return response.json().get("data", [])
        else:
            print(f"Error fetching data for CERT {cert}: {response.status_code}")
            return []
    except Exception as e:
        print(f"Exception fetching data for CERT {cert}: {e}")
        return []

def fetch_bank_name(cert):
    params = {
        "filters": f"CERT:{cert}",
        "fields": "NAME,CERT",
        "limit": "1",
        "format": "json"
    }
    try:
        response = requests.get(SUMMARY_URL, params=params)
        if response.status_code == 200:
            results = response.json().get("data", [])
            if results:
                return results[0]["data"]["NAME"]
    except Exception as e:
        print(f"Exception fetching name for CERT {cert}: {e}")
    return f"Bank_{cert}"

def apply_calculations(df):
    df = df.apply(pd.to_numeric, errors='coerce')

    try: df.loc["Assets"] = df.loc["ASSET"]
    except: df.loc["Assets"] = None

    try: df.loc["Loans"] = df.loc["LNLSGR"]
    except: df.loc["Loans"] = None

    try: df.loc["Investment Securities"] = df.loc["SC"] + df.loc["CHBALI"]
    except: df.loc["Investment Securities"] = None

    try: df.loc["Investments/Assets"] = round((df.loc["SC"] + df.loc["CHBALI"]) / df.loc["ASSET"] * 100, 2)
    except: df.loc["Investments/Assets"] = None

    try: df.loc["Deposits"] = df.loc["DEP"]
    except: df.loc["Deposits"] = None

    try: df.loc["Loan-to-Deposit Ratio"] = round(df.loc["LNLSGR"] / df.loc["DEP"] * 100, 2)
    except: df.loc["Loan-to-Deposit Ratio"] = None

    try: df.loc["Brokered Deposits"] = df.loc["BRO"]
    except: df.loc["Brokered Deposits"] = None

    try: df.loc["Brokered Deposits/Total Deposits"] = round(df.loc["BRO"] / df.loc["DEP"] * 100, 2)
    except: df.loc["Brokered Deposits/Total Deposits"] = None

    try: df.loc["Borrowings"] = df.loc["OTHBRF"]
    except: df.loc["Borrowings"] = None

    try: df.loc["Borrowings/Assets"] = round(df.loc["OTHBRF"] / df.loc["ASSET"] * 100, 2)
    except: df.loc["Borrowings/Assets"] = None

    try: df.loc["GAAP Capital"] = df.loc["EQTOT"]
    except: df.loc["GAAP Capital"] = None

    try: df.loc["GAAP Capital/Assets"] = round(df.loc["EQTOT"] / df.loc["ASSET"] * 100, 2)
    except: df.loc["GAAP Capital/Assets"] = None

    try:
        df.loc["Non-Owner Occupied Commercial Real Estate/Total Capital"] = round(
            (df.loc["LNRECONS"] + df.loc["LNREMULT"] + df.loc["LNCOMRE"] + df.loc["LNRENROT"]) /
            (df.loc["LNATRES"] + df.loc["RBCT1J"]) * 100, 2)
    except: df.loc["Non-Owner Occupied Commercial Real Estate/Total Capital"] = None

    try: df.loc["Net Interest Margin"] = round(df.loc["NIMY"], 2)
    except: df.loc["Net Interest Margin"] = None

    try: df.loc["Net Income"] = df.loc["NETINC"]
    except: df.loc["Net Income"] = None

    try: df.loc["Efficiency Ratio"] = round(df.loc["EEFFR"], 2)
    except: df.loc["Efficiency Ratio"] = None

    try:
        months_up_to_quarter = df.columns.to_series().dt.quarter.map({1: 3, 2: 6, 3: 9, 4: 12})
        df.loc["Annualized Earnings (Pre-Tax)"] = ((df.loc["PTAXNETINC"] - df.loc["IGLSEC"]) / months_up_to_quarter) * 12
        df.loc["Annualized Earnings (Tax Adjusted)"] = (df.loc["NETINC"] / months_up_to_quarter) * 12
    except:
        df.loc["Annualized Earnings (Pre-Tax)"] = None
        df.loc["Annualized Earnings (Tax Adjusted)"] = None

    try: df.loc["Return on Assets"] = round(df.loc["ROA"], 2)
    except: df.loc["Return on Assets"] = None

    try: df.loc["Return on Equity"] = round(df.loc["ROE"], 2)
    except: df.loc["Return on Equity"] = None

    try: df.loc["Allowance for Loan Losses"] = df.loc["LNATRES"]
    except: df.loc["Allowance for Loan Losses"] = None

    try: df.loc["CECL Adoption"] = df.loc["SCHTMRES"]
    except: df.loc["CECL Adoption"] = None

    try: df.loc["Allowance/Loans"] = round(df.loc["LNATRES"] / df.loc["LNLSGR"] * 100, 2)
    except: df.loc["Allowance/Loans"] = None

    try: df.loc["YTD Provision for Loan Losses"] = df.loc["ELNATR"]
    except: df.loc["YTD Provision for Loan Losses"] = None

    try: df.loc["YTD Net Charge-Offs (Recoveries)"] = df.loc["NTLNLS"]
    except: df.loc["YTD Net Charge-Offs (Recoveries)"] = None

    try:
        months_up_to_quarter = df.columns.to_series().dt.quarter.map({1: 3, 2: 6, 3: 9, 4: 12})
        df.loc["Annualized Losses/Loans"] = round(((df.loc["NTLNLS"] / months_up_to_quarter) * 12) / df.loc["LNLSGR"] * 100, 2)
    except: df.loc["Annualized Losses/Loans"] = None

    try: df.loc["90 Days Past Due & Nonaccrual Loans"] = df.loc["P9ASSET"] + df.loc["NAASSET"]
    except: df.loc["90 Days Past Due & Nonaccrual Loans"] = None

    try: df.loc["Non-Performing Loans Ratio"] = round(df.loc["NCLNLSR"], 2)
    except: df.loc["Non-Performing Loans Ratio"] = None

    try: df.loc["Other Real Estate Owned"] = df.loc["ORE"]
    except: df.loc["Other Real Estate Owned"] = None

    try:
        df.loc["(90 Days Past Due + Nonaccrual + REO) / (Capital + Allowance)"] = round(
            (df.loc["P9ASSET"] + df.loc["NAASSET"] + df.loc["ORE"]) /
            (df.loc["LNATRES"] + df.loc["EQTOT"] - df.loc["INTAN"]) * 100, 2)
    except: df.loc["(90 Days Past Due + Nonaccrual + REO) / (Capital + Allowance)"] = None

    try: df.loc["Tier 1 Leverage Ratio"] = round(df.loc["RBC1AAJ"], 2)
    except: df.loc["Tier 1 Leverage Ratio"] = None

    try: df.loc["Common Equity Tier 1 Ratio"] = round(df.loc["IDT1CER"], 2)
    except: df.loc["Common Equity Tier 1 Ratio"] = None

    try: df.loc["Tier 1 Risk Based Ratio"] = round(df.loc["IDT1RWAJR"], 2)
    except: df.loc["Tier 1 Risk Based Ratio"] = None

    try: df.loc["Total Risk Based Ratio"] = round(df.loc["RBCRWAJ"], 2)
    except: df.loc["Total Risk Based Ratio"] = None

    try: df.loc["Capital Contribution"] = df.loc["EQCBHCTR"]
    except: df.loc["Capital Contribution"] = None

    try: df.loc["Ineligible Intangibles"] = df.loc["INTAN"]
    except: df.loc["Ineligible Intangibles"] = None

    try: df.loc["YTD Taxes Paid"] = df.loc["ITAX"]
    except: df.loc["YTD Taxes Paid"] = None

    try: df.loc["YTD Taxes Paid as a Percentage of Income"] = round(df.loc["ITAXR"], 2)
    except: df.loc["YTD Taxes Paid as a Percentage of Income"] = None

    # ✅ FORMATTING SECTION — numbers and percentages
    dollar_rows = [
        "Allowance for Loan Losses", "Annualized Earnings (Pre-Tax)", "Annualized Earnings (Tax Adjusted)",
        "Assets", "Borrowings", "Brokered Deposits", "Capital Contribution", "CECL Adoption",
        "Deposits", "GAAP Capital", "Ineligible Intangibles", "Investment Securities", "Loans",
        "Net Income", "Other Real Estate Owned", "YTD Net Charge-Offs (Recoveries)",
        "YTD Provision for Loan Losses", "YTD Taxes Paid", "90 Days Past Due & Nonaccrual Loans"
    ]

    percent_rows = [
        "(90 Days Past Due + Nonaccrual + REO) / (Capital + Allowance)", "Allowance/Loans",
        "Borrowings/Assets", "Brokered Deposits/Total Deposits", "Common Equity Tier 1 Ratio",
        "Efficiency Ratio", "GAAP Capital/Assets", "Investments/Assets", "Loan-to-Deposit Ratio",
        "Net Interest Margin", "Non-Owner Occupied Commercial Real Estate/Total Capital",
        "Non-Performing Loans Ratio", "Return on Assets", "Return on Equity",
        "Tier 1 Leverage Ratio", "Tier 1 Risk Based Ratio", "Total Risk Based Ratio",
        "YTD Taxes Paid as a Percentage of Income", "Annualized Losses/Loans"
    ]

    gap_after = [
        "Assets", "Borrowings/Assets", "Return on Equity",
        "(90 Days Past Due + Nonaccrual + REO) / (Capital + Allowance)",
        "Total Risk Based Ratio", "Ineligible Intangibles"
    ]

    for row in reversed(gap_after):
        if row in df.index:
            idx = df.index.get_loc(row)
            top = df.iloc[:idx + 1]
            bottom = df.iloc[idx + 1:]
            gap_row = pd.DataFrame([["" for _ in df.columns]], index=[""], columns=df.columns)
            df = pd.concat([top, gap_row, bottom])

    # NOTE: In this version we return numeric values to Excel so we can use Excel formatting,
    # or we can pre-format strings.The reference code formatted them as strings.
    # To keep consistency with the reference implementation which people might rely on visually,
    # I will keep the string formatting but maybe improvements could be made later.
    # Actually, the reference main.py logic had the formatting at the end of process_data.
    
    for row in dollar_rows:
        if row in df.index:
            df.loc[row] = df.loc[row].apply(lambda x: f"{x:,.0f}" if pd.notnull(x) and x != "" else x)

    for row in percent_rows:
        if row in df.index:
            df.loc[row] = df.loc[row].apply(lambda x: f"{x:.2f}%" if pd.notnull(x) and x != "" else x)

    return df

def process_data(data):
    records = [entry["data"] for entry in data]
    if not records:
        return pd.DataFrame()
        
    df = pd.DataFrame(records)
    
    # Convert REPDTE to datetime and sort correctly
    df["REPDTE"] = pd.to_datetime(df["REPDTE"])
    df.sort_values("REPDTE", ascending=False, inplace=True)
    # Create a new column with formatted dates (e.g., "Dec 2024")
    df["REPDTE_formatted"] = df["REPDTE"].dt.strftime("%b %Y")
    df.drop("REPDTE", axis=1, inplace=True)
    df.rename(columns={"REPDTE_formatted": "REPDTE"}, inplace=True)
    
    df.set_index("REPDTE", inplace=True)
    df = df.transpose()
    df = apply_calculations(df)
    
    # Ensure earnings rows exist even if blank
    if "Annualized Earnings (Pre-Tax)" not in df.index:
        df.loc["Annualized Earnings (Pre-Tax)"] = ""
    if "Annualized Earnings (Tax Adjusted)" not in df.index:
        df.loc["Annualized Earnings (Tax Adjusted)"] = ""
    
    ordered_rows = [
        "Assets", "Loans", "Investment Securities", "Investments/Assets", "Deposits",
        "Loan-to-Deposit Ratio", "Brokered Deposits", "Brokered Deposits/Total Deposits",
        "Borrowings", "Borrowings/Assets", "GAAP Capital", "GAAP Capital/Assets",
        "Non-Owner Occupied Commercial Real Estate/Total Capital", "Net Interest Margin",
        "Net Income", "Efficiency Ratio", "Annualized Earnings (Pre-Tax)",
        "Annualized Earnings (Tax Adjusted)", "Return on Assets", "Return on Equity",
        "Allowance for Loan Losses", "CECL Adoption", "Allowance/Loans",
        "YTD Provision for Loan Losses", "YTD Net Charge-Offs (Recoveries)",
        "Annualized Losses/Loans", "90 Days Past Due & Nonaccrual Loans",
        "Non-Performing Loans Ratio", "Other Real Estate Owned",
        "(90 Days Past Due + Nonaccrual + REO) / (Capital + Allowance)",
        "Tier 1 Leverage Ratio", "Common Equity Tier 1 Ratio",
        "Tier 1 Risk Based Ratio", "Total Risk Based Ratio",
        "Capital Contribution", "Ineligible Intangibles",
        "YTD Taxes Paid", "YTD Taxes Paid as a Percentage of Income"
    ]
    
    # Filter duplicates and reorder
    df = df[~df.index.duplicated(keep="first")]
    
    # Only reindex with rows that actually exist or should exist
    # If we strictly reindex with ordered_rows, we drop anything else.
    # The reference code did:
    df = df.reindex([row for row in ordered_rows if row in df.index])
    
    return df

def generate_fdic_excel(bank_codes: list[int | str]) -> bytes:
    """
    Generates an Excel file (in bytes) for the given list of bank codes.
    """
    output = io.BytesIO()
    
    # Use xlsxwriter for consistency with reference, or openpyxl. 
    # Reference used xlsxwriter. Backend main.py uses openpyxl.
    # Let's use xlsxwriter as in reference to ensure specific formatting options work as intended if any.
    # Actually, let's stick to what's available. `pandas` supports both.
    
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        processed_count = 0
        
        for cert in bank_codes:
            cert = str(cert).strip()
            if not cert:
                continue
                
            print(f"Processing CERT {cert}...")
            data = fetch_fdic_data(cert)
            
            if data:
                bank_name = fetch_bank_name(cert)
                df = process_data(data)
                
                if df.empty:
                    continue
                
                # Reset index so that the metrics become a column
                df_reset = df.reset_index()
                df_reset.columns.values[0] = "Metric"
                
                # Sanitize sheet name (max 31 chars, no invalid chars)
                # Strategy: "{Name} - {Cert}"
                # Reserve space for suffix " - {cert}"
                clean_name = "".join(c for c in bank_name if c not in "[]:*?/\\")
                suffix = f"-{cert}"
                max_name_len = 31 - len(suffix)
                sheet_name = f"{clean_name[:max_name_len]}{suffix}"
                
                # Write data starting at row 5
                df_reset.to_excel(writer, sheet_name=sheet_name, startrow=4, index=False)
                
                # Get workbook and worksheet objects
                workbook = writer.book
                worksheet = writer.sheets[sheet_name]
                
                # Write header rows
                worksheet.write("A1", bank_name)
                worksheet.write("A2", "(overview, amounts in $1000s)")
                worksheet.write("A3", f"FDIC CERT: {cert}")
                
                # Adjust column widths
                worksheet.set_column(0, 0, 45) # Metric column width
                worksheet.set_column(1, len(df.columns), 15) # Data columns width
                
                processed_count += 1
                
        if processed_count == 0:
            # Create a dummy sheet if no data found to avoid error saving
            pd.DataFrame(["No data found for provided codes"]).to_excel(writer, sheet_name="Error", header=False, index=False)

    output.seek(0)
    return output.getvalue()
