import os, io, sys, glob, requests, pandas as pd
from bs4 import BeautifulSoup

# ==== EDIT THESE THREE TO MATCH YOUR REPO ====
LOCAL_DIR = "assets/site/current/leagues"  # folder where A.html, B.html, ... live (relative to repo root)
BASE_URL  = "https://zapmast-oss.github.io/defending-the-shield-site/assets/site/current/leagues/league_200_players_{L}.html"  # if scraping from GitHub Pages
HTML_FILENAME_FORMAT = "league_200_players_{L}.html"  # change if your files are named differently (e.g., "players_{L}.html")
# ============================================

# Start with a single letter to "measure twice"
LETTERS = list("b")  # for first dry run, change to ["A"]
# LETTERS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

COLUMNS = ["Name","Pos","Team","Age","DOB","POB","Nationality","Bats","Throws","Height","Weight","Salary"]

def read_local(letter: str):
    path = os.path.join(LOCAL_DIR, HTML_FILENAME_FORMAT.format(L=letter))
    if os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    return None

def read_remote(letter: str):
    url = BASE_URL.format(L=letter)
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.content

def extract_table(html_bytes: bytes) -> pd.DataFrame:
    # Try pandas first (fast)
    try:
        tables = pd.read_html(io.BytesIO(html_bytes), flavor="lxml")
    except ValueError:
        tables = []

    # Fallback: find the table with our headers via BeautifulSoup if needed
    if not tables:
        soup = BeautifulSoup(html_bytes, "lxml")
        tables_soup = soup.find_all("table")
        for t in tables_soup:
            headers = [th.get_text(strip=True) for th in t.find_all("th")]
            if headers and ("Name" in headers and "Team" in headers):
                df = pd.read_html(str(t), flavor="lxml")[0]
                tables.append(df)

    if not tables:
        raise RuntimeError("No tables found on page.")

    # Pick the table that contains 'Name' and as many of our columns as possible
    best = None
    best_score = -1
    for df in tables:
        score = sum(1 for c in df.columns if str(c).strip() in COLUMNS)
        if score > best_score:
            best = df
            best_score = score

    df = best.copy()
    # Normalize headers
    df.columns = [str(c).strip() for c in df.columns]

    # If the table has extra cols, reduce to our set when present
    keep = [c for c in COLUMNS if c in df.columns]
    df = df[keep].copy()

    # Clean whitespace
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].astype(str).str.strip()

    # Drop header-echo rows if any
    df = df[df["Name"].str.lower() != "name"]

    # Basic sanity: require Name & Team presence
    df = df[df["Name"].notna() & df["Name"].str.len().gt(0)]

    return df

def fetch_letter(letter: str) -> pd.DataFrame:
    html = read_local(letter)
    if html is None:
        # fall back to GitHub Pages
        html = read_remote(letter)
    return extract_table(html)

def main():
    frames = []
    for L in LETTERS:
        try:
            df = fetch_letter(L)
        except Exception as e:
            print(f"[{L}] ERROR: {e}", file=sys.stderr)
            raise
        df["Letter"] = L
        frames.append(df)

    out = pd.concat(frames, ignore_index=True)
    # Reorder columns consistently if available
    ordered = [c for c in COLUMNS if c in out.columns] + [c for c in out.columns if c not in COLUMNS]
    out = out[ordered]

    # Sort for stability
    out = out.sort_values(["Letter","Name"], kind="stable").reset_index(drop=True)

    # Write outputs at repo root
    out.to_csv("players.csv", index=False)
    try:
        out.to_excel("players.xlsx", index=False)
    except Exception as e:
        print(f"Could not write Excel (openpyxl missing?): {e}", file=sys.stderr)

    print(f"OK: wrote {len(out):,} rows to players.csv / players.xlsx")

if __name__ == "__main__":
    main()
