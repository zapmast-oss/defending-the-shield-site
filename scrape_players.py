import os, io, sys, re, requests, pandas as pd
from bs4 import BeautifulSoup

# ========= CONFIGURE THESE =========
LOCAL_DIR = "site/current/leagues"
HTML_FILENAME_FORMAT = "league_200_players_{l}.html"
BASE_URL  = "https://zapmast-oss.github.io/defending-the-shield-site/site/current/leagues/league_200_players_{l}.html"

# SAFE TEST: one letter first; when it looks good, switch to list("abcdefghijklmnopqrstuvwxyz")
LETTERS = ["b"]
# ===================================

# Canonical columns we want (order too)
COLUMNS = ["Name","Pos","Team","Age","DOB","POB","Nationality","Bats","Throws","Height","Weight","Salary"]

# Acceptable position codes (to filter out junk rows)
POS_SET = {"SP","RP","CL","C","1B","2B","3B","SS","LF","CF","RF","DH"}

# Junk-row patterns to drop from the Name column (page chrome, nav bars, headers, etc.)
JUNK_PATTERNS = [
    r"\bA\s*\|\s*B\s*\|\s*C",                # A | B | C | ... nav row
    r"^BNN Index",                            # site header lines
    r"^THE SHIELD\b",
    r"^The Shield\b",
    r"^PLAYERS LIST\b",
    r"^LEAGUE STATS PAGE\b",
    r"^HISTORY\b",
    r"^\s*NaN\s*$",                           # literal NaN string
]

def _fmt(letter: str): return {"L": letter, "l": letter.lower()}
def _local_path(letter: str): return os.path.join(LOCAL_DIR, HTML_FILENAME_FORMAT.format(**_fmt(letter)))
def _remote_url(letter: str): return BASE_URL.format(**_fmt(letter))

def read_local(letter: str):
    path = _local_path(letter)
    print(f"[{letter}] Looking for local file: {path}")
    if os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    return None

def read_remote(letter: str):
    url = _remote_url(letter)
    print(f"[{letter}] Fetching remote URL: {url}")
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.content

def _normalize_headers(df: pd.DataFrame) -> pd.DataFrame:
    # If the first row repeats the headers, promote it to columns and drop the row
    row0 = [str(x).strip() for x in df.iloc[0].tolist()]
    overlap = sum(1 for x in row0 if x in COLUMNS)
    if overlap >= 5:  # looks like a header row
        df = df.iloc[1:].copy()
        df.columns = row0

    # Trim/standardize column names
    df.columns = [str(c).strip() for c in df.columns]

    # Map common header variants to our canonical names
    ren = {
        "Date of Birth":"DOB",
        "Place of Birth":"POB",
        "Nationality":"Nationality",
        "Throws/Bats":"Throws",   # just in case
        "Bats/Throws":"Bats",     # just in case
    }
    for k,v in ren.items():
        if k in df.columns and v not in df.columns:
            df.rename(columns={k:v}, inplace=True)

    return df

def _choose_best_table(tables: list[pd.DataFrame]) -> pd.DataFrame:
    # Score tables by how many canonical columns they have
    def score(df):
        cols = [str(c).strip() for c in df.columns]
        return sum(1 for c in cols if c in COLUMNS)
    return max(tables, key=score)

def _drop_junk_rows(df: pd.DataFrame) -> pd.DataFrame:
    if "Name" not in df.columns:
        return df

    # remove rows where Name is header-ish or nav-ish
    mask = pd.Series([False]*len(df))
    name_series = df["Name"].astype(str).str.strip()

    for pat in JUNK_PATTERNS:
        mask |= name_series.str.contains(pat, flags=re.I, regex=True, na=False)

    # rows that clearly repeat column headers
    mask |= name_series.str.fullmatch("Name", case=False, na=False)
    if "Pos" in df.columns:
        mask |= df["Pos"].astype(str).str.fullmatch("Pos|Position", case=False, na=False)
    if "Team" in df.columns:
        mask |= df["Team"].astype(str).str.fullmatch("Team", case=False, na=False)

    # rows without a comma in Name (OOTP lists are "Last, First")
    comma_mask = name_series.str.contains(",", na=False)
    # keep if comma present OR it looks like a legit player row by having a valid Pos
    if "Pos" in df.columns:
        pos_mask = df["Pos"].astype(str).str.upper().isin(POS_SET)
        keep = comma_mask | pos_mask
    else:
        keep = comma_mask

    cleaned = df[~mask & keep].copy()

    # Basic type cleanups
    if "Age" in cleaned.columns:
        cleaned["Age"] = pd.to_numeric(cleaned["Age"], errors="coerce")

    # Drop rows that have no Name or Team
    for col in ["Name","Team"]:
        if col in cleaned.columns:
            cleaned = cleaned[cleaned[col].astype(str).str.strip().ne("")]

    # De-dup
    subset = [c for c in ["Name","Team"] if c in cleaned.columns]
    if subset:
        cleaned = cleaned.drop_duplicates(subset=subset, keep="first")

    return cleaned

def extract_table(html_bytes: bytes) -> pd.DataFrame:
    # 1) Try pandas.read_html on the whole page
    try:
        tables = pd.read_html(io.BytesIO(html_bytes), flavor="lxml")
    except ValueError:
        tables = []

    # 2) If none found, use BeautifulSoup to find tables that include our headers
    if not tables:
        soup = BeautifulSoup(html_bytes, "lxml")
        candidates = []
        for t in soup.find_all("table"):
            headers = [th.get_text(strip=True) for th in t.find_all("th")]
            if headers and ("Name" in headers and "Team" in headers):
                try:
                    candidates.append(pd.read_html(str(t), flavor="lxml")[0])
                except Exception:
                    pass
        tables = candidates

    if not tables:
        raise RuntimeError("No tables found on page.")

    # Normalize and score all tables, then choose the best
    normed = []
    for df in tables:
        df2 = _normalize_headers(df)
        normed.append(df2)
    best = _choose_best_table(normed)

    # Reduce to our known columns when present (preserve order)
    keep = [c for c in COLUMNS if c in best.columns]
    if keep:
        best = best[keep].copy()

    # Final cleanup of rows
    best = _drop_junk_rows(best)

    # If some canonical columns are missing, add them empty so the CSV is consistent
    for c in COLUMNS:
        if c not in best.columns:
            best[c] = pd.NA
    best = best[COLUMNS]

    return best

def fetch_letter(letter: str) -> pd.DataFrame:
    html = read_local(letter)
    if html is None:
        html = read_remote(letter)
    return extract_table(html)

def main():
    frames = []
    for L in LETTERS:
        try:
            df = fetch_letter(L)
            df["Letter"] = L.lower()
            frames.append(df)
            print(f"[{L}] OK: {len(df)} rows")
        except Exception as e:
            print(f"[{L}] ERROR: {e}", file=sys.stderr)
            raise

    out = pd.concat(frames, ignore_index=True)

    # Stable sort for sanity
    out = out.sort_values(["Letter","Name","Team"], kind="stable", na_position="last").reset_index(drop=True)

    # Write outputs to repo root
    out.to_csv("players.csv", index=False)
    try:
        out.to_excel("players.xlsx", index=False)
    except Exception as e:
        print(f"Excel write skipped: {e}", file=sys.stderr)

    print(f"DONE: wrote {len(out):,} rows to players.csv / players.xlsx")

if __name__ == "__main__":
    main()
