import subprocess,os
files = subprocess.check_output(['git','ls-files']).decode().splitlines()
rows=[]
for f in files:
    try:
        s = os.path.getsize(f)
        rows.append((s,f))
    except Exception:
        pass
rows.sort(reverse=True)
for s,f in rows[:50]:
    print(f"{s/1024/1024:.2f} MB\t{f}")
