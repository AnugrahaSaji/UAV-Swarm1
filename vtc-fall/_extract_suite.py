import csv

target_pairs = {}
with open('../suite_comparison_full.csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        sid = row['Suite ID']
        if 'aesgcm' not in sid:
            continue
        kem = row['Baseline (No DDoS) | KEM']
        sig = row['Baseline (No DDoS) | SIG']
        lvl = row['Baseline (No DDoS) | Security Level']
        hs = row.get('Baseline (No DDoS) | Handshake ms', '')
        crypto = row.get('Baseline (No DDoS) | Total Crypto ms', '')
        kg = row.get('Baseline (No DDoS) | KEM Keygen ms', '')
        enc = row.get('Baseline (No DDoS) | KEM Encaps ms', '')
        dec = row.get('Baseline (No DDoS) | KEM Decaps ms', '')
        sign = row.get('Baseline (No DDoS) | SIG Sign ms', '')
        ver = row.get('Baseline (No DDoS) | SIG Verify ms', '')
        pavg = row.get('Baseline (No DDoS) | Power Avg W', '')
        etot = row.get('Baseline (No DDoS) | Energy/HS J', '')
        cpu = row.get('Baseline (No DDoS) | Drone CPU Avg %', '')
        tput = row.get('Baseline (No DDoS) | Throughput Mbps', '')

        key = (kem, sig, lvl)
        if key not in target_pairs:
            target_pairs[key] = dict(
                hs=float(hs) if hs else 0,
                crypto=float(crypto) if crypto else 0,
                kg=float(kg) if kg else 0,
                enc=float(enc) if enc else 0,
                dec=float(dec) if dec else 0,
                sign=float(sign) if sign else 0,
                ver=float(ver) if ver else 0,
                pavg=float(pavg) if pavg else 0,
                etot=float(etot) if etot else 0,
                cpu=float(cpu) if cpu else 0,
                tput=float(tput) if tput else 0,
            )

kem_map = {
    'ML-KEM-512': 'ML512', 'ML-KEM-768': 'ML768', 'ML-KEM-1024': 'ML1024',
    'HQC-128': 'HQ128', 'HQC-192': 'HQ192', 'HQC-256': 'HQ256',
    'Classic-McEliece-348864': 'MC348', 'Classic-McEliece-460896': 'MC460',
    'Classic-McEliece-8192128': 'MC8192',
}
sig_map = {
    'ML-DSA-44': 'DSA44', 'ML-DSA-65': 'DSA65', 'ML-DSA-87': 'DSA87',
    'Falcon-512': 'F512', 'Falcon-1024': 'F1024',
    'SPHINCS+-SHA2-128s-simple': 'SP128', 'SPHINCS+-SHA2-192s-simple': 'SP192',
    'SPHINCS+-SHA2-256s-simple': 'SP256',
}

for lvl_name in ['L1', 'L3', 'L5']:
    print(f'--- {lvl_name} ---')
    items = [(k, v) for k, v in target_pairs.items() if k[2] == lvl_name]
    items.sort(key=lambda x: x[1]['hs'])
    ref_hs = items[0][1]['hs'] if items else 1
    for (kem, sig, lvl), d in items:
        ka = kem_map.get(kem, kem)
        sa = sig_map.get(sig, sig)
        kem_t = d['kg'] + d['enc'] + d['dec']
        sig_t = d['sign'] + d['ver']
        rho = d['hs'] / ref_hs if ref_hs > 0 else 0
        # energy per handshake: if etot=0, estimate from power * time
        ehs = d['etot']
        if ehs == 0 and d['pavg'] > 0:
            ehs = d['pavg'] * d['hs'] / 1000.0  # W * ms / 1000 = mJ -> J... actually W*s = J, so W * ms/1000 = J? No. W * (ms/1000) = W*s = J
            # ehs in J
        print(f'{ka:>6}+{sa:<6}  HS={d["hs"]:>10.2f}ms  Crypto={d["crypto"]:>10.2f}ms  KEM={kem_t:>10.2f}  SIG={sig_t:>10.2f}  P={d["pavg"]:>6.3f}W  E/HS={ehs:>8.4f}J  rho={rho:>7.1f}x  CPU={d["cpu"]:>5.1f}%')
    print()
