import pandas as pd
d = pd.read_csv("train_ddos_data_0.1.csv")
a = d[d["Status"]==1]["Mavlink_Count"].values
n = d[d["Status"]==0]["Mavlink_Count"].values
print("First 20 attack:", a[:20].tolist())
print("Attack rows 95-110:", a[95:110].tolist())
print(f"Attack mean: {a.mean():.1f}, min: {a.min()}, max: {a.max()}")
print(f"Attack rows with value > 25: {(a > 25).sum()} out of {len(a)}")
print("First 20 normal:", n[:20].tolist())
print(f"Normal mean: {n.mean():.1f}, min: {n.min()}, max: {n.max()}")

# Check where in the raw CSV the attack transitions happen
print("\nCSV structure (first 5 rows):")
print(d.head())
print("\nCSV status value counts:")
print(d["Status"].value_counts())

# Find where attack rows get low values
for i in range(0, min(200, len(a)), 5):
    chunk = a[i:i+5].tolist()
    avg = sum(chunk)/len(chunk)
    if i < 20 or avg < 20:
        print(f"  attack_rows[{i}:{i+5}] = {chunk}  avg={avg:.1f}")
