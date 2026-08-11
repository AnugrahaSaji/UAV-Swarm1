import { useEffect, useState } from 'react';

interface SwarmNode {
    node_id: string;
    role: string;
    cluster_id: string;
    ip_address: string;
    status: string;
    battery_pct: number;
    signal_dbm: number;
}

interface SwarmTopology {
    status: string;
    active_nodes: number;
    cluster_count: number;
    leader_id: string;
    topology_mode: string;
    nodes: SwarmNode[];
}

interface SMTStatus {
    tree_depth: number;
    total_leaves: number;
    root_hash: string;
    hash_algorithm: string;
    verification_status: string;
    proof_sample: {
        key: string;
        value: string;
        proof_siblings: string[];
        is_valid: boolean;
    };
}

interface D2DRoute {
    source_uav: string;
    target_uav: string;
    hop_count: number;
    d2d_latency_ms: number;
    d2d_rtt_ms: number;
    smt_verification_time_ms: number;
    link_quality_pct: number;
}

interface D2DPerformance {
    status: string;
    d2d_avg_latency_ms: number;
    d2d_avg_rtt_ms: number;
    d2d_throughput_mbps: number;
    d2d_packet_loss_pct: number;
    smt_proof_gen_time_ms: number;
    smt_proof_verify_time_ms: number;
    smt_proof_size_bytes: number;
    root_sync_interval_ms: number;
    verification_success_rate_pct: number;
    routes: D2DRoute[];
}

export default function SwarmSMTAudit() {
    const [swarm, setSwarm] = useState<SwarmTopology | null>(null);
    const [smt, setSmt] = useState<SMTStatus | null>(null);
    const [d2d, setD2d] = useState<D2DPerformance | null>(null);
    const [loading, setLoading] = useState(true);

    const [testKey, setTestKey] = useState('telemetry_log_001');
    const [testValue, setTestValue] = useState('MAVLink_Packet_Valid_01');
    const [verifyResult, setVerifyResult] = useState<any>(null);
    const [verifying, setVerifying] = useState(false);
    const [showRootHash, setShowRootHash] = useState(false);

    const maskHash = (hashStr?: string) => {
        if (!hashStr) return '••••••••••••••••••••••••••••••••';
        if (showRootHash) return hashStr;
        if (hashStr.length > 10) {
            return hashStr.slice(0, 6) + '•'.repeat(48) + hashStr.slice(-4);
        }
        return '••••••••••••••••••••••••••••••••';
    };

    useEffect(() => {
        const fetchData = async () => {
            try {
                const [swarmRes, smtRes, d2dRes] = await Promise.all([
                    fetch('/api/swarm/topology'),
                    fetch('/api/smt/status'),
                    fetch('/api/swarm/d2d-performance'),
                ]);
                if (swarmRes.ok) setSwarm(await swarmRes.json());
                if (smtRes.ok) setSmt(await smtRes.json());
                if (d2dRes.ok) setD2d(await d2dRes.json());
            } catch (err) {
                console.error("Failed to load Swarm/SMT status", err);
            } finally {
                setLoading(false);
            }
        };
        fetchData();
    }, []);

    const handleVerify = async () => {
        setVerifying(true);
        try {
            const res = await fetch('/api/smt/verify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key: testKey, value: testValue }),
            });
            if (res.ok) setVerifyResult(await res.json());
        } catch (err) {
            console.error("Verification failed", err);
        } finally {
            setVerifying(false);
        }
    };

    if (loading) {
        return (
            <div className="p-8 text-center text-gray-400">
                Loading Drone-to-Drone Swarm & SMT Performance Data...
            </div>
        );
    }

    return (
        <div className="p-6 max-w-[1400px] mx-auto space-y-6 text-gray-100">
            {/* Header */}
            <div className="flex items-center justify-between border-b border-gray-700 pb-4">
                <div>
                    <h1 className="text-2xl font-bold text-blue-400 flex items-center gap-2">
                        <span>🐝</span> Drone-to-Drone (D2D) Swarm & SMT Performance
                    </h1>
                    <p className="text-sm text-gray-400 mt-1">
                        Real-time inter-UAV wireless communication metrics, SMT Merkle proof latency, and D2D routing throughput.
                    </p>
                </div>
                <div className="flex items-center gap-3">
                    <span className="px-3 py-1 bg-green-500/20 text-green-400 text-xs font-bold rounded-full border border-green-500/30">
                        ● D2D LINK: {d2d?.status || 'HEALTHY'}
                    </span>
                    <span className="px-3 py-1 bg-purple-500/20 text-purple-400 text-xs font-bold rounded-full border border-purple-500/30">
                        ● SMT PROOF: VERIFIED ({d2d?.verification_success_rate_pct}%)
                    </span>
                </div>
            </div>

            {/* D2D Key Performance Metrics Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="bg-gray-800/80 border border-gray-700 rounded-xl p-4 text-center">
                    <div className="text-xs text-gray-400 font-medium">Inter-UAV Latency</div>
                    <div className="text-2xl font-bold text-blue-400 mt-1">{d2d?.d2d_avg_latency_ms} ms</div>
                    <div className="text-[11px] text-gray-500 mt-1">One-Way D2D Link</div>
                </div>

                <div className="bg-gray-800/80 border border-gray-700 rounded-xl p-4 text-center">
                    <div className="text-xs text-gray-400 font-medium">Inter-UAV RTT</div>
                    <div className="text-2xl font-bold text-green-400 mt-1">{d2d?.d2d_avg_rtt_ms} ms</div>
                    <div className="text-[11px] text-gray-500 mt-1">Round-Trip Time</div>
                </div>

                <div className="bg-gray-800/80 border border-gray-700 rounded-xl p-4 text-center">
                    <div className="text-xs text-gray-400 font-medium">SMT Verify Time</div>
                    <div className="text-2xl font-bold text-purple-400 mt-1">{d2d?.smt_proof_verify_time_ms} ms</div>
                    <div className="text-[11px] text-gray-500 mt-1">Per Packet Check</div>
                </div>

                <div className="bg-gray-800/80 border border-gray-700 rounded-xl p-4 text-center">
                    <div className="text-xs text-gray-400 font-medium">D2D Throughput</div>
                    <div className="text-2xl font-bold text-amber-400 mt-1">{d2d?.d2d_throughput_mbps} Mbps</div>
                    <div className="text-[11px] text-gray-500 mt-1">Packet Loss: {d2d?.d2d_packet_loss_pct}%</div>
                </div>
            </div>

            {/* Grid 2: Drone-to-Drone Routing Table & SMT Overhead */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Inter-UAV Route Performance Table */}
                <div className="bg-gray-800/60 border border-gray-700 rounded-xl p-5 shadow-lg space-y-4">
                    <div className="flex items-center justify-between">
                        <h2 className="text-lg font-semibold text-blue-300 flex items-center gap-2">
                            <span>📡</span> Inter-UAV Communication Routes
                        </h2>
                        <span className="text-xs bg-gray-700 px-2 py-1 rounded text-gray-300">
                            Active Links: {d2d?.routes.length}
                        </span>
                    </div>

                    <div className="overflow-x-auto">
                        <table className="w-full text-left text-xs text-gray-300">
                            <thead className="bg-gray-900/80 text-gray-400 uppercase text-[10px]">
                                <tr>
                                    <th className="p-2">Source UAV</th>
                                    <th className="p-2">Target UAV</th>
                                    <th className="p-2">Hops</th>
                                    <th className="p-2">D2D Latency</th>
                                    <th className="p-2">D2D RTT</th>
                                    <th className="p-2">SMT Verify</th>
                                    <th className="p-2">Link Quality</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-700/50">
                                {d2d?.routes.map((r, i) => (
                                    <tr key={i} className="hover:bg-gray-700/30">
                                        <td className="p-2 font-mono font-medium text-white">{r.source_uav}</td>
                                        <td className="p-2 font-mono text-blue-300">{r.target_uav}</td>
                                        <td className="p-2 text-center font-bold text-gray-300">{r.hop_count}</td>
                                        <td className="p-2 text-blue-400">{r.d2d_latency_ms} ms</td>
                                        <td className="p-2 text-green-400">{r.d2d_rtt_ms} ms</td>
                                        <td className="p-2 text-purple-400">{r.smt_verification_time_ms} ms</td>
                                        <td className="p-2 text-amber-400">{r.link_quality_pct}%</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>

                {/* SMT Cryptographic Overhead Details */}
                <div className="bg-gray-800/60 border border-gray-700 rounded-xl p-5 shadow-lg space-y-4">
                    <div className="flex items-center justify-between">
                        <h2 className="text-lg font-semibold text-purple-300 flex items-center gap-2">
                            <span>🛡️</span> SMT Cryptographic Overhead
                        </h2>
                        <span className="text-xs bg-purple-900/40 text-purple-300 px-2 py-1 rounded border border-purple-700/50 font-mono">
                            {smt?.hash_algorithm}
                        </span>
                    </div>

                    <div className="bg-gray-900/80 p-4 rounded-lg border border-gray-700 space-y-3 text-xs">
                        <div className="flex justify-between items-center pb-2 border-b border-gray-700">
                            <span className="text-gray-400">SMT Proof Generation Time:</span>
                            <span className="font-mono text-purple-300 font-bold">{d2d?.smt_proof_gen_time_ms} ms</span>
                        </div>
                        <div className="flex justify-between items-center pb-2 border-b border-gray-700">
                            <span className="text-gray-400">SMT Proof Verification Time:</span>
                            <span className="font-mono text-green-400 font-bold">{d2d?.smt_proof_verify_time_ms} ms</span>
                        </div>
                        <div className="flex justify-between items-center pb-2 border-b border-gray-700">
                            <span className="text-gray-400">Packet Overhead Payload Size:</span>
                            <span className="font-mono text-amber-300 font-bold">{d2d?.smt_proof_size_bytes} bytes / packet</span>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-gray-400">Swarm Merkle Root Sync Interval:</span>
                            <span className="font-mono text-blue-300 font-bold">{d2d?.root_sync_interval_ms} ms</span>
                        </div>
                    </div>

                    <div className="bg-gray-900/80 p-3.5 rounded-lg border border-gray-700 space-y-2">
                        <div className="flex items-center justify-between">
                            <div className="text-[11px] text-gray-400 uppercase tracking-wider font-semibold">
                                CURRENT SWARM MERKLE ROOT
                            </div>
                            <button
                                onClick={() => setShowRootHash(!showRootHash)}
                                className="flex items-center gap-1.5 px-2.5 py-1 text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 rounded border border-gray-600 transition-colors shadow-sm cursor-pointer"
                                title={showRootHash ? "Hide Plaintext Root Hash" : "Show Plaintext Root Hash"}
                            >
                                <span>{showRootHash ? '🙈' : '👁️'}</span>
                                <span className="text-[11px] font-medium">{showRootHash ? 'Hide Root' : 'Reveal Root'}</span>
                            </button>
                        </div>
                        <div className="font-mono text-xs text-green-400 break-all bg-black/50 p-2.5 rounded border border-green-900/50 flex items-center justify-between">
                            <span>{maskHash(smt?.root_hash)}</span>
                        </div>
                    </div>
                </div>
            </div>

            {/* Swarm Topology & Nodes Detail */}
            <div className="bg-gray-800/60 border border-gray-700 rounded-xl p-5 shadow-lg space-y-4">
                <div className="flex items-center justify-between">
                    <h2 className="text-lg font-semibold text-blue-300 flex items-center gap-2">
                        <span>🛰️</span> Active UAV Swarm Node Topology
                    </h2>
                    <span className="text-xs bg-gray-700 px-2 py-1 rounded text-gray-300">
                        Mode: {swarm?.topology_mode}
                    </span>
                </div>

                <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs text-gray-300">
                        <thead className="bg-gray-900/80 text-gray-400 uppercase text-[10px]">
                            <tr>
                                <th className="p-2">Node ID</th>
                                <th className="p-2">Role</th>
                                <th className="p-2">Cluster ID</th>
                                <th className="p-2">IP Address</th>
                                <th className="p-2">Battery</th>
                                <th className="p-2">Signal Strength</th>
                                <th className="p-2">Status</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-700/50">
                            {swarm?.nodes.map((node) => (
                                <tr key={node.node_id} className="hover:bg-gray-700/30">
                                    <td className="p-2 font-mono font-medium text-white">{node.node_id}</td>
                                    <td className="p-2">
                                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                            node.role === 'Leader'
                                                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                                                : node.role === 'ClusterHead'
                                                ? 'bg-blue-500/20 text-blue-300'
                                                : 'bg-gray-700 text-gray-300'
                                        }`}>
                                            {node.role}
                                        </span>
                                    </td>
                                    <td className="p-2 font-mono text-gray-400">{node.cluster_id}</td>
                                    <td className="p-2 font-mono text-gray-400">{node.ip_address}</td>
                                    <td className="p-2 text-green-400">{node.battery_pct}%</td>
                                    <td className="p-2 text-gray-400">{node.signal_dbm} dBm</td>
                                    <td className="p-2 text-green-400 font-bold">{node.status}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* Live Interactive Merkle Proof Tester */}
            <div className="bg-gray-800/60 border border-gray-700 rounded-xl p-5 shadow-lg space-y-4">
                <h2 className="text-lg font-semibold text-purple-300 flex items-center gap-2">
                    <span>🔍</span> Test Live SMT Cryptographic Leaf Verification
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                        <label className="block text-xs font-semibold text-gray-400 mb-1">Telemetry Record Key</label>
                        <input
                            type="text"
                            value={testKey}
                            onChange={(e) => setTestKey(e.target.value)}
                            className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-blue-500"
                        />
                    </div>
                    <div>
                        <label className="block text-xs font-semibold text-gray-400 mb-1">Telemetry Record Value</label>
                        <input
                            type="text"
                            value={testValue}
                            onChange={(e) => setTestValue(e.target.value)}
                            className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-blue-500"
                        />
                    </div>
                </div>

                <button
                    onClick={handleVerify}
                    disabled={verifying}
                    className="px-5 py-2.5 bg-purple-600 hover:bg-purple-500 text-white font-medium text-sm rounded-lg transition-colors shadow-md disabled:opacity-50"
                >
                    {verifying ? 'Verifying SMT Proof...' : 'Verify Cryptographic Inclusion Proof'}
                </button>

                {verifyResult && (
                    <div className={`p-4 rounded-lg border text-sm font-mono space-y-1 ${
                        verifyResult.verified
                            ? 'bg-green-950/40 border-green-700 text-green-300'
                            : 'bg-red-950/40 border-red-700 text-red-300'
                    }`}>
                        <div className="font-bold flex items-center gap-2">
                            <span>{verifyResult.verified ? '✅' : '❌'}</span>
                            <span>{verifyResult.audit_result}</span>
                        </div>
                        <div className="text-xs opacity-80">Merkle Root: {maskHash(verifyResult.merkle_root)}</div>
                    </div>
                )}
            </div>
        </div>
    );
}
