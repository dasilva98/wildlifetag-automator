import argparse
import os
import sys
import pandas as pd

def inspect_csv(filepath, rows=5):
    """Loads and prints a structural summary of the CSV file."""
    print("=" * 72)
    print(f"  CSV INSPECTOR: {os.path.basename(filepath)}")
    print("=" * 72)

    try:
        df = pd.read_csv(filepath)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return

    print(f"\n[ SHAPE ]")
    print(f"Rows: {len(df):,} | Columns: {len(df.columns)}")

    print(f"\n[ COLUMNS & TYPES ]")
    for col, dtype in zip(df.columns, df.dtypes):
        print(f"  - {col:<20} {dtype}")

    print(f"\n[ DATA PREVIEW (First {rows} rows) ]")
    print(df.head(rows).to_string())
    print("\n" + "=" * 72)

def main():
    parser = argparse.ArgumentParser(
        description="CSV Data Inspector - Diagnostic tool for WildlifeTag Automator",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("file", help="Path to the .csv file to inspect.")
    parser.add_argument(
        "--rows",
        type=int,
        default=5,
        help="Number of rows to preview (default: 5)."
    )

    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"\nError: File not found: '{args.file}'\n")
        sys.exit(1)

    inspect_csv(args.file, rows=args.rows)

if __name__ == "__main__":
    main()
