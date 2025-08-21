import os, io, sys, requests, pandas as pd
from bs4 import BeautifulSoup

# ========= CONFIGURE THESE =========
# Folder in your repo where the letter pages live (as seen in the Code tab)
LOCAL_DIR = "site/current/leagues"

# Filename pattern for each letter page (your pages use lowercase letters)
HTML_FILENAME_FORMAT = "league_200_players_{l}.html"

# Public GitHub Pages URL pattern (opens in a browser too)
BASE_URL  = "https://zapmast-oss.github.io/defending-the-shield-site/site/current/leagues/league_200_players_{l}.html"

# SAFE TEST: run one letter first. When it works, change to list("abcdefghijklmnopqrstuvwxyz")
LETTERS = ["b"]
# ===================================

# Columns we want to keep/order if present
COLUMNS = ["Name","Pos","Team","Age","DOB","POB","Nationality","Bats","Throws","Height","Weight","Salary"]

def _fmt(letter: str):
    """Provide both upper and lower forms for format() templates."""
    return {"L": letter, "l": letter.lower()}

def _local_path(letter: str):
    return os.path.join(LOCAL_DIR, HTML_FILENAME_FORMAT.format(**_fmt(letter)))

def _remote_url(letter: str):
    return BASE_URL.format(**_fmt(letter))

def read_local(letter: str):
    """Read HTML bytes from repo files (if present)."""
    path = _local_path(letter)
    print(f"[{letter}] Looking for local file: {path}")
    if os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    return None

def read_remote(letter: str):
    """Fetch HTML bytes from the public site."""
    url = _remote_url(letter)
    print(f"[{letter}] Fetching remote URL: {url}")
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.content

def extract_table(html_bytes: bytes) -> pd.DataFrame:
    """Extract the player table into a DataFrame."""
    # 1) Try pandas' HTML reader first
    try:
        tables = pd.read_html(io.BytesIO(html_bytes), flavor="lxml")
    except ValueError:
        tables = []

    # 2) Fallback: find a table that has our headers using BeautifulSoup
    if not tables:
        soup = BeautifulSoup(html_bytes, "lxml")
        chosen = None
        for t in soup.find_all("table"):
            headers = [th.get_text(strip=True) for th in t.find_all("th")]
            if headers and ("Name" in headers and "Team" in headers):
                chosen = t
                break
        if chosen is not None:
            tables = [pd.read_html(str(chosen), flavor="lxml")[0]]

    if not tables:
        raise RuntimeError("No tables found on page.")

    # Pick the table that matches the most expected columns
    def score(df):
        return sum(1 for c in df.columns if str(c).strip() in COLUMNS)
    best = max(tables, key=score)

    df = best.copy()
    df.columns = [str(c).strip() for c in df.columns]

    # Keep/Order known columns when present
    keep = [c for c in COLUMNS if c in df.columns]
    if keep:
        df = df[keep].copy()

    # Basic cleanup
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].astype(str).str.strip()

    # Drop any repeated header rows
    if "Name" in df.columns:
        df = df[df["Name"].str.lower() != "name"]
        df = df[df["Name"].notna() & df["Name"].str.len().gt(0)]

    return df

def fetch_letter(letter: str) -> pd.DataFrame:
    """Try local first, then remote."""
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

    # Stable column order: known columns first
    ordered = [c for c in COLUMNS if c in out.columns] + [c for c in out.columns if c not in COLUMNS]
    out = out[ordered]

    # Stable sort for easier diffs
    sort_cols = [c for c in ["Letter","Name","Team"] if c in out.columns]
    if sort_cols:
        out = out.sort_values(sort_cols, kind="stable").reset_index(drop=True)

    # Write outputs to repo root
    out.to_csv("players.csv", index=False)
    try:
        out.to_excel("players.xlsx", index=False)
    except Exception as e:
        print(f"Excel write skipped: {e}", file=sys.stderr)

    print(f"DONE: wrote {len(out):,} rows to players.csv / players.xlsx")

if __name__ == "__main__":
    main()
