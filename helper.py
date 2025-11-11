# TODO: make this general use
tripinfo_csv_tool_out = OUT_DIR / f"tripinfo_sim{sim_id}_day{day}_{policy.get('id')}.csv"
if tripinfo_out.exists():
    cmd = ["python", str(XML2CSV_PATH), str(tripinfo_out), "--output", str(tripinfo_csv_tool_out)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0: print(f"tripinfo CSV converted: {tripinfo_csv_tool_out}")
    else: print(f"CONVERSION FAILED:\n{result.stderr}")
else: print(f"tripinfo XML NOT FOUND: {tripinfo_out}")