/**
 * Suite Detail Page - Deep-dive into single suite metrics
 */

import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useDashboardStore } from '../state/store';
import type { ReliabilityClass, MetricStatus } from '../types/metrics';

// Reliability badge component
function ReliabilityBadge({ reliability }: { reliability: ReliabilityClass }) {
    const classes: Record<ReliabilityClass, string> = {
        VERIFIED: 'badge-verified',
        CONDITIONAL: 'badge-conditional',
        DEPRECATED: 'badge-deprecated',
        MISSING: 'badge-missing',
    };
    return <span className={classes[reliability]}>{reliability}</span>;
}

// Metric display component
function MetricValue({
    value,
    unit = '',
    status,
    classification,
}: {
    value: number | string | boolean | null | undefined;
    unit?: string;
    status?: MetricStatus;
    classification?: string | null;
}) {
    const consistencyBadge = classification && classification !== 'CONSISTENT' ? (
        <span
            className={classification === 'BROKEN'
                ? 'ml-2 text-xs text-red-400 bg-red-500/20 px-1.5 py-0.5 rounded'
                : classification === 'MISLEADING'
                    ? 'ml-2 text-xs text-amber-300 bg-amber-500/20 px-1.5 py-0.5 rounded'
                    : 'ml-2 text-xs text-gray-300 bg-gray-500/20 px-1.5 py-0.5 rounded'
            }
            title={classification === 'BROKEN' ? 'BROKEN — do not interpret' : classification === 'MISLEADING' ? 'MISLEADING — interpret with caution' : classification}
        >
            {classification === 'BROKEN' ? 'BROKEN' : classification === 'MISLEADING' ? 'MISLEADING' : classification}
        </span>
    ) : null;
    if (status?.status === 'invalid') {
        return <span className="text-red-400 italic">Invalid{status.reason ? ` (${status.reason})` : ''}{consistencyBadge}</span>;
    }
    if (status?.status === 'not_implemented') {
        return <span className="text-gray-500 italic">Not implemented{consistencyBadge}</span>;
    }
    if (status?.status === 'not_collected') {
        return <span className="text-gray-500 italic">Not collected{consistencyBadge}</span>;
    }
    if (value === null || value === undefined || value === '') {
        return <span className="text-gray-500 italic">Not collected{consistencyBadge}</span>;
    }
    if (typeof value === 'boolean') {
        return <span className={value ? 'text-green-400' : 'text-red-400'}>{value ? 'Yes' : 'No'}{consistencyBadge}</span>;
    }
    if (typeof value === 'number') {
        return <span className="font-mono">{value.toFixed(2)} {unit}{consistencyBadge}</span>;
    }
    if (typeof value === 'object') {
        return <span className="font-mono text-xs text-amber-500" title={JSON.stringify(value)}>
            {JSON.stringify(value).substring(0, 20)}{JSON.stringify(value).length > 20 ? '...' : ''}
        </span>;
    }
    return <span>{value} {unit}{consistencyBadge}</span>;
}

// Metric card component
function MetricCard({ title, children, reliability = 'VERIFIED' as ReliabilityClass }: { title: ReactNode; children: ReactNode; reliability?: ReliabilityClass }) {
    return (
        <div className="card">
            <div className="flex items-center justify-between mb-3">
                <h3 className="card-header mb-0">{title}</h3>
                <ReliabilityBadge reliability={reliability} />
            </div>
            {children}
        </div>
    );
}

export default function SuiteDetail() {
    const { suiteKey } = useParams<{ suiteKey: string }>();
    const { selectedSuite, selectedSuiteInventory, isLoading, error, fetchSuiteDetail, fetchSuiteInventory } = useDashboardStore();
    const [inventoryFilter, setInventoryFilter] = useState('');

    useEffect(() => {
        if (suiteKey) {
            fetchSuiteDetail(decodeURIComponent(suiteKey));
            fetchSuiteInventory(decodeURIComponent(suiteKey));
        }
    }, [suiteKey, fetchSuiteDetail, fetchSuiteInventory]);

    const inventoryStatusMap = useMemo(() => {
        const map = new Map<string, MetricStatus>();
        if (!selectedSuiteInventory?.metrics) return map;
        selectedSuiteInventory.metrics.forEach(item => {
            if (item.source !== 'DRONE') return;
            if (!item.key) return;
            if (item.status === 'invalid') {
                map.set(item.key, { status: 'invalid', reason: item.reason || undefined });
            } else if (item.status === 'not_collected') {
                map.set(item.key, { status: 'not_collected', reason: item.reason || undefined });
            }
        });
        return map;
    }, [selectedSuiteInventory]);

    const consistencyMap = useMemo(() => {
        const map = new Map<string, string>();
        if (!selectedSuiteInventory?.metrics) return map;
        selectedSuiteInventory.metrics.forEach(item => {
            if (!item.key || !item.classification) return;
            if (!map.has(item.key)) {
                map.set(item.key, item.classification);
            }
        });
        return map;
    }, [selectedSuiteInventory]);

    const inventoryRows = useMemo(() => {
        if (!selectedSuiteInventory?.metrics) {
            return [];
        }
        const term = inventoryFilter.trim().toLowerCase();
        if (!term) {
            return selectedSuiteInventory.metrics;
        }
        return selectedSuiteInventory.metrics.filter(item => item.key.toLowerCase().includes(term));
    }, [selectedSuiteInventory, inventoryFilter]);

    if (error && !selectedSuite) {
        return (
            <div className="flex items-center justify-center h-64">
                <div className="text-red-400">Failed to load suite details: {error}</div>
            </div>
        );
    }

    if (isLoading || !selectedSuite) {
        return (
            <div className="flex items-center justify-center h-64">
                <div className="text-gray-400">Loading suite details...</div>
            </div>
        );
    }

    const suite = selectedSuite;
    const statusMap = suite.validation.metric_status || {};

    const getStatus = (path: string): MetricStatus | undefined => {
        return inventoryStatusMap.get(path) || statusMap[path];
    };

    const getConsistency = (path: string): string | null => {
        return consistencyMap.get(path) ?? null;
    };

    const formatInventoryValue = (value: unknown) => {
        if (value === null || value === undefined) return 'null';
        if (typeof value === 'string') return value;
        if (typeof value === 'number' || typeof value === 'boolean') return String(value);
        try {
            return JSON.stringify(value);
        } catch {
            return String(value);
        }
    };

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center gap-4">
                <Link to="/suites" className="text-gray-400 hover:text-white">← Back</Link>
                <h1 className="text-2xl font-bold">{suite.run_context.suite_id}</h1>
                <span className={suite.validation.benchmark_pass_fail === 'PASS'
                    ? 'badge-verified'
                    : suite.validation.benchmark_pass_fail === 'FAIL'
                        ? 'bg-red-500/20 text-red-400 px-2 py-0.5 rounded text-xs'
                        : 'badge-missing'}>
                    {suite.validation.benchmark_pass_fail || 'Not collected'}
                </span>
            </div>

            {/* A. Run Context */}
            <MetricCard title="A. Run Context">
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
                    <div><span className="text-gray-400">Run ID:</span> <span className="font-mono">{suite.run_context.run_id}</span></div>
                    <div><span className="text-gray-400">Suite Index:</span> {suite.run_context.suite_index}</div>
                    <div><span className="text-gray-400">Git Commit:</span> <span className="font-mono"><MetricValue value={suite.run_context.git_commit_hash} status={getStatus('run_context.git_commit_hash')} classification={getConsistency('run_context.git_commit_hash')} /></span></div>
                    <div><span className="text-gray-400">GCS Host:</span> <MetricValue value={suite.run_context.gcs_hostname} status={getStatus('run_context.gcs_hostname')} classification={getConsistency('run_context.gcs_hostname')} /></div>
                    <div><span className="text-gray-400">Drone Host:</span> <MetricValue value={suite.run_context.drone_hostname} status={getStatus('run_context.drone_hostname')} classification={getConsistency('run_context.drone_hostname')} /></div>
                    <div><span className="text-gray-400">Start Time:</span> {suite.run_context.run_start_time_wall ? new Date(suite.run_context.run_start_time_wall).toLocaleString() : 'Not collected'}</div>
                </div>
            </MetricCard>

            {/* B. Crypto Identity */}
            <MetricCard title="B. Crypto Identity">
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
                    <div><span className="text-gray-400">KEM:</span> <span className="font-mono text-blue-400"><MetricValue value={suite.crypto_identity.kem_algorithm} status={getStatus('crypto_identity.kem_algorithm')} classification={getConsistency('crypto_identity.kem_algorithm')} /></span></div>
                    <div><span className="text-gray-400">KEM Family:</span> <MetricValue value={suite.crypto_identity.kem_family} status={getStatus('crypto_identity.kem_family')} classification={getConsistency('crypto_identity.kem_family')} /></div>
                    <div><span className="text-gray-400">Signature:</span> <span className="font-mono text-purple-400"><MetricValue value={suite.crypto_identity.sig_algorithm} status={getStatus('crypto_identity.sig_algorithm')} classification={getConsistency('crypto_identity.sig_algorithm')} /></span></div>
                    <div><span className="text-gray-400">Sig Family:</span> <MetricValue value={suite.crypto_identity.sig_family} status={getStatus('crypto_identity.sig_family')} classification={getConsistency('crypto_identity.sig_family')} /></div>
                    <div><span className="text-gray-400">AEAD:</span> <span className="font-mono"><MetricValue value={suite.crypto_identity.aead_algorithm} status={getStatus('crypto_identity.aead_algorithm')} classification={getConsistency('crypto_identity.aead_algorithm')} /></span></div>
                    <div><span className="text-gray-400">Security Level:</span> <MetricValue value={suite.crypto_identity.suite_security_level} status={getStatus('crypto_identity.suite_security_level')} classification={getConsistency('crypto_identity.suite_security_level')} /></div>
                </div>
            </MetricCard>

            {/* D. Handshake */}
            <MetricCard title="D. Handshake Metrics">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                    <div>
                        <div className="text-gray-400 text-xs">Total Duration</div>
                        <div className="text-xl"><MetricValue value={suite.handshake.handshake_total_duration_ms} unit="ms" status={getStatus('handshake.handshake_total_duration_ms')} classification={getConsistency('handshake.handshake_total_duration_ms')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Protocol Duration</div>
                        <div className="font-mono"><MetricValue value={suite.handshake.protocol_handshake_duration_ms} unit="ms" status={getStatus('handshake.protocol_handshake_duration_ms')} classification={getConsistency('handshake.protocol_handshake_duration_ms')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">End-to-end Duration</div>
                        <div className="font-mono"><MetricValue value={suite.handshake.end_to_end_handshake_duration_ms} unit="ms" status={getStatus('handshake.end_to_end_handshake_duration_ms')} classification={getConsistency('handshake.end_to_end_handshake_duration_ms')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Success</div>
                        <div className="text-xl"><MetricValue value={suite.handshake.handshake_success} status={getStatus('handshake.handshake_success')} classification={getConsistency('handshake.handshake_success')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Failure Reason</div>
                        <div><MetricValue value={suite.handshake.handshake_failure_reason} status={getStatus('handshake.handshake_failure_reason')} classification={getConsistency('handshake.handshake_failure_reason')} /></div>
                    </div>
                </div>
            </MetricCard>

            {/* M. Control Plane */}
            <MetricCard title="M. Control Plane">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                    <div>
                        <div className="text-gray-400 text-xs">Scheduler Tick</div>
                        <div className="font-mono"><MetricValue value={suite.control_plane.scheduler_tick_interval_ms} unit="ms" status={getStatus('control_plane.scheduler_tick_interval_ms')} classification={getConsistency('control_plane.scheduler_tick_interval_ms')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Policy Name</div>
                        <div className="font-mono"><MetricValue value={suite.control_plane.policy_name} status={getStatus('control_plane.policy_name')} classification={getConsistency('control_plane.policy_name')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Policy State</div>
                        <div className="font-mono"><MetricValue value={suite.control_plane.policy_state} status={getStatus('control_plane.policy_state')} classification={getConsistency('control_plane.policy_state')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Action Type</div>
                        <div className="font-mono"><MetricValue value={suite.control_plane.scheduler_action_type} status={getStatus('control_plane.scheduler_action_type')} classification={getConsistency('control_plane.scheduler_action_type')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Action Reason</div>
                        <div className="font-mono"><MetricValue value={suite.control_plane.scheduler_action_reason} status={getStatus('control_plane.scheduler_action_reason')} classification={getConsistency('control_plane.scheduler_action_reason')} /></div>
                    </div>
                </div>
            </MetricCard>

            {/* G. Data Plane */}
            <MetricCard title="G. Data Plane">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                    <div>
                        <div className="text-gray-400 text-xs">Packets Sent</div>
                        <div className="font-mono"><MetricValue value={suite.data_plane.packets_sent} status={getStatus('data_plane.packets_sent')} classification={getConsistency('data_plane.packets_sent')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Packets Received</div>
                        <div className="font-mono"><MetricValue value={suite.data_plane.packets_received} status={getStatus('data_plane.packets_received')} classification={getConsistency('data_plane.packets_received')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Packets Dropped</div>
                        <div className="font-mono">
                            <MetricValue value={suite.data_plane.packets_dropped} status={getStatus('data_plane.packets_dropped')} classification={getConsistency('data_plane.packets_dropped')} />
                        </div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Delivery Ratio</div>
                        <div className="font-mono">
                            <MetricValue value={suite.data_plane.packet_delivery_ratio !== null && suite.data_plane.packet_delivery_ratio !== undefined ? suite.data_plane.packet_delivery_ratio * 100 : null} unit="%" status={getStatus('data_plane.packet_delivery_ratio')} classification={getConsistency('data_plane.packet_delivery_ratio')} />
                        </div>
                    </div>
                </div>
            </MetricCard>

            {/* Link Quality */}
            <MetricCard title="Link Quality">
                <div className="text-xs text-gray-500 mb-2">Source: {suite.packet_counters_source || 'unknown'}</div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                    <div>
                        <div className="text-gray-400 text-xs">Goodput</div>
                        <div className="font-mono"><MetricValue value={suite.data_plane.goodput_mbps} unit="Mbps" status={getStatus('data_plane.goodput_mbps')} classification={getConsistency('data_plane.goodput_mbps')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Achieved Throughput</div>
                        <div className="font-mono"><MetricValue value={suite.data_plane.achieved_throughput_mbps} unit="Mbps" status={getStatus('data_plane.achieved_throughput_mbps')} classification={getConsistency('data_plane.achieved_throughput_mbps')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Packet Loss</div>
                        <div className="font-mono"><MetricValue value={suite.data_plane.packet_loss_ratio !== null && suite.data_plane.packet_loss_ratio !== undefined ? suite.data_plane.packet_loss_ratio * 100 : null} unit="%" status={getStatus('data_plane.packet_loss_ratio')} classification={getConsistency('data_plane.packet_loss_ratio')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Delivery Ratio</div>
                        <div className="font-mono"><MetricValue value={suite.data_plane.packet_delivery_ratio !== null && suite.data_plane.packet_delivery_ratio !== undefined ? suite.data_plane.packet_delivery_ratio * 100 : null} unit="%" status={getStatus('data_plane.packet_delivery_ratio')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Packets Sent</div>
                        <div className="font-mono"><MetricValue value={suite.data_plane.packets_sent} status={getStatus('data_plane.packets_sent')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Packets Received</div>
                        <div className="font-mono"><MetricValue value={suite.data_plane.packets_received} status={getStatus('data_plane.packets_received')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Packets Dropped</div>
                        <div className="font-mono"><MetricValue value={suite.data_plane.packets_dropped} status={getStatus('data_plane.packets_dropped')} /></div>
                    </div>
                </div>
            </MetricCard>

            {/* H. Latency & Jitter */}
            <MetricCard title="H. Latency & Jitter">
                <div className="text-xs text-gray-500 mb-2">Source: {suite.latency_source || 'unknown'}</div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                    <div>
                        <div className="text-gray-400 text-xs">One-way Avg</div>
                        <div className="font-mono"><MetricValue value={suite.latency_jitter.one_way_latency_avg_ms} unit="ms" status={getStatus('latency_jitter.one_way_latency_avg_ms')} classification={getConsistency('latency_jitter.one_way_latency_avg_ms')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">One-way P95</div>
                        <div className="font-mono"><MetricValue value={suite.latency_jitter.one_way_latency_p95_ms} unit="ms" status={getStatus('latency_jitter.one_way_latency_p95_ms')} classification={getConsistency('latency_jitter.one_way_latency_p95_ms')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Jitter Avg</div>
                        <div className="font-mono"><MetricValue value={suite.latency_jitter.jitter_avg_ms} unit="ms" status={getStatus('latency_jitter.jitter_avg_ms')} classification={getConsistency('latency_jitter.jitter_avg_ms')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Jitter P95</div>
                        <div className="font-mono"><MetricValue value={suite.latency_jitter.jitter_p95_ms} unit="ms" status={getStatus('latency_jitter.jitter_p95_ms')} classification={getConsistency('latency_jitter.jitter_p95_ms')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">One-way Valid</div>
                        <div className="font-mono"><MetricValue value={suite.latency_jitter.one_way_latency_valid} classification={getConsistency('latency_jitter.one_way_latency_valid')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">RTT Avg</div>
                        <div className="font-mono"><MetricValue value={suite.latency_jitter.rtt_avg_ms} unit="ms" status={getStatus('latency_jitter.rtt_avg_ms')} classification={getConsistency('latency_jitter.rtt_avg_ms')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">RTT P95</div>
                        <div className="font-mono"><MetricValue value={suite.latency_jitter.rtt_p95_ms} unit="ms" status={getStatus('latency_jitter.rtt_p95_ms')} classification={getConsistency('latency_jitter.rtt_p95_ms')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">RTT Valid</div>
                        <div className="font-mono"><MetricValue value={suite.latency_jitter.rtt_valid} classification={getConsistency('latency_jitter.rtt_valid')} /></div>
                    </div>
                    <div className="col-span-2">
                        <div className="text-gray-400 text-xs">Latency Invalid Reason</div>
                        <div className="font-mono"><MetricValue value={suite.latency_jitter.latency_invalid_reason} classification={getConsistency('latency_jitter.latency_invalid_reason')} /></div>
                    </div>
                    <div className="col-span-2">
                        <div className="text-gray-400 text-xs">RTT Invalid Reason</div>
                        <div className="font-mono"><MetricValue value={suite.latency_jitter.rtt_invalid_reason} classification={getConsistency('latency_jitter.rtt_invalid_reason')} /></div>
                    </div>
                </div>
            </MetricCard>

            {/* Full Inventory */}
            <MetricCard title="Full Metric Inventory (Authoritative + Validation + Legacy)">
                <div className="text-xs text-gray-500 mb-3">
                    This table is generated from the authoritative DRONE JSON plus GCS validation payloads. Legacy fields are labeled. Consistency classification is enforced from the consistency matrix. All categories (including lifecycle, observability, and fc_telemetry) are present here.
                </div>
                <div className="mb-3">
                    <input
                        className="select-input w-full"
                        placeholder="Filter metrics by key (e.g., data_plane, handshake, mavlink)"
                        value={inventoryFilter}
                        onChange={e => setInventoryFilter(e.target.value)}
                    />
                </div>
                {!selectedSuiteInventory ? (
                    <div className="text-gray-400">Loading metric inventory...</div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="data-table">
                            <thead>
                                <tr>
                                    <th>Metric</th>
                                    <th>Value</th>
                                    <th>Status</th>
                                    <th>Consistency</th>
                                    <th>Source</th>
                                    <th>Nullable</th>
                                    <th>Zero-valid</th>
                                    <th>Origin</th>
                                </tr>
                            </thead>
                            <tbody>
                                {inventoryRows.map((item, idx) => (
                                    <tr key={`${item.source}:${item.key}:${idx}`}>
                                        <td className="font-mono text-xs">{item.key}</td>
                                        <td className="font-mono text-xs text-gray-200 break-all">
                                            {formatInventoryValue(item.value)}
                                        </td>
                                        <td className="text-xs">
                                            <span className={item.status === 'invalid' ? 'text-red-400' : item.status === 'not_collected' ? 'text-gray-400' : item.status === 'legacy' ? 'text-amber-400' : 'text-green-400'}>
                                                {item.status}{item.reason ? ` (${item.reason})` : ''}
                                            </span>
                                        </td>
                                        <td className="text-xs">
                                            {item.classification ? (
                                                <span className={item.classification === 'BROKEN' ? 'text-red-400' : item.classification === 'MISLEADING' ? 'text-amber-300' : item.classification === 'CONSISTENT' ? 'text-green-400' : 'text-gray-300'}>
                                                    {item.classification}
                                                </span>
                                            ) : (
                                                <span className="text-gray-500">—</span>
                                            )}
                                        </td>
                                        <td className="text-xs">{item.source}</td>
                                        <td className="text-xs">{item.nullable_expected === null || item.nullable_expected === undefined ? '—' : item.nullable_expected ? 'yes' : 'no'}</td>
                                        <td className="text-xs">{item.zero_valid ?? '—'}</td>
                                        <td className="text-xs text-gray-400">{item.origin_function ?? '—'}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </MetricCard>

            {/* Raw Payloads */}
            <MetricCard title="Raw Payloads (Drone Authoritative / GCS Validation)">
                {!selectedSuiteInventory ? (
                    <div className="text-gray-400">Loading raw payloads...</div>
                ) : (
                    <div className="space-y-4 text-xs">
                        <details className="bg-gray-800/40 p-3 rounded">
                            <summary className="cursor-pointer text-gray-300">Raw DRONE JSON</summary>
                            <pre className="mt-2 overflow-x-auto whitespace-pre-wrap">{JSON.stringify(selectedSuiteInventory.raw.drone, null, 2)}</pre>
                        </details>
                        <details className="bg-gray-800/40 p-3 rounded">
                            <summary className="cursor-pointer text-gray-300">Raw GCS JSON</summary>
                            <pre className="mt-2 overflow-x-auto whitespace-pre-wrap">{JSON.stringify(selectedSuiteInventory.raw.gcs, null, 2)}</pre>
                        </details>
                        <details className="bg-gray-800/40 p-3 rounded">
                            <summary className="cursor-pointer text-gray-300">GCS Validation (JSONL + derived)</summary>
                            <pre className="mt-2 overflow-x-auto whitespace-pre-wrap">{JSON.stringify(selectedSuiteInventory.raw.gcs_validation ?? {}, null, 2)}</pre>
                        </details>
                    </div>
                )}
            </MetricCard>

            {/* K. MAVLink Integrity */}
            <MetricCard
                title="K. MAVLink Integrity"
                reliability={suite.mavlink_integrity.mavlink_out_of_order_count && suite.mavlink_integrity.mavlink_out_of_order_count > 0 ? 'CONDITIONAL' : 'VERIFIED'}
            >
                <div className="text-xs text-gray-500 mb-2">Source: {suite.integrity_source || 'unknown'}</div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                    <div>
                        <div className="text-gray-400 text-xs">Out of Order</div>
                        <div className="font-mono">
                            <MetricValue value={suite.mavlink_integrity.mavlink_out_of_order_count} status={getStatus('mavlink_integrity.mavlink_out_of_order_count')} classification={getConsistency('mavlink_integrity.mavlink_out_of_order_count')} />
                        </div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">CRC Errors</div>
                        <div className="font-mono">
                            <MetricValue value={suite.mavlink_integrity.mavlink_packet_crc_error_count} status={getStatus('mavlink_integrity.mavlink_packet_crc_error_count')} classification={getConsistency('mavlink_integrity.mavlink_packet_crc_error_count')} />
                        </div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Decode Errors</div>
                        <div className="font-mono">
                            <MetricValue value={suite.mavlink_integrity.mavlink_decode_error_count} status={getStatus('mavlink_integrity.mavlink_decode_error_count')} classification={getConsistency('mavlink_integrity.mavlink_decode_error_count')} />
                        </div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Duplicates</div>
                        <div className="font-mono"><MetricValue value={suite.mavlink_integrity.mavlink_duplicate_count} status={getStatus('mavlink_integrity.mavlink_duplicate_count')} classification={getConsistency('mavlink_integrity.mavlink_duplicate_count')} /></div>
                    </div>
                </div>
            </MetricCard>

            {/* N. System Resources Drone */}
            <MetricCard title="N. System Resources (Drone)">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                    <div>
                        <div className="text-gray-400 text-xs">CPU Avg</div>
                        <div className="font-mono"><MetricValue value={suite.system_drone.cpu_usage_avg_percent} unit="%" status={getStatus('system_drone.cpu_usage_avg_percent')} classification={getConsistency('system_drone.cpu_usage_avg_percent')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">CPU Peak</div>
                        <div className="font-mono"><MetricValue value={suite.system_drone.cpu_usage_peak_percent} unit="%" status={getStatus('system_drone.cpu_usage_peak_percent')} classification={getConsistency('system_drone.cpu_usage_peak_percent')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Memory RSS</div>
                        <div className="font-mono"><MetricValue value={suite.system_drone.memory_rss_mb} unit="MB" status={getStatus('system_drone.memory_rss_mb')} classification={getConsistency('system_drone.memory_rss_mb')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Temperature</div>
                        <div className="font-mono"><MetricValue value={suite.system_drone.temperature_c} unit="°C" status={getStatus('system_drone.temperature_c')} classification={getConsistency('system_drone.temperature_c')} /></div>
                    </div>
                </div>
            </MetricCard>

            {/* O. System Resources GCS */}
            <MetricCard title="O. System Resources (GCS)">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                    <div>
                        <div className="text-gray-400 text-xs">CPU Avg</div>
                        <div className="font-mono"><MetricValue value={suite.system_gcs.cpu_usage_avg_percent} unit="%" status={getStatus('system_gcs.cpu_usage_avg_percent')} classification={getConsistency('system_gcs.cpu_usage_avg_percent')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">CPU Peak</div>
                        <div className="font-mono"><MetricValue value={suite.system_gcs.cpu_usage_peak_percent} unit="%" status={getStatus('system_gcs.cpu_usage_peak_percent')} classification={getConsistency('system_gcs.cpu_usage_peak_percent')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Memory RSS</div>
                        <div className="font-mono"><MetricValue value={suite.system_gcs.memory_rss_mb} unit="MB" status={getStatus('system_gcs.memory_rss_mb')} classification={getConsistency('system_gcs.memory_rss_mb')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Temperature</div>
                        <div className="font-mono"><MetricValue value={suite.system_gcs.temperature_c} unit="°C" status={getStatus('system_gcs.temperature_c')} classification={getConsistency('system_gcs.temperature_c')} /></div>
                    </div>
                </div>
            </MetricCard>

            {/* P. Power & Energy */}
            <MetricCard title="P. Power & Energy">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                    <div>
                        <div className="text-gray-400 text-xs">Sensor Type</div>
                        <div className="font-mono"><MetricValue value={suite.power_energy.power_sensor_type} status={getStatus('power_energy.power_sensor_type')} classification={getConsistency('power_energy.power_sensor_type')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Power Avg</div>
                        <div className="text-xl text-green-400"><MetricValue value={suite.power_energy.power_avg_w} unit="W" status={getStatus('power_energy.power_avg_w')} classification={getConsistency('power_energy.power_avg_w')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Power Peak</div>
                        <div className="font-mono"><MetricValue value={suite.power_energy.power_peak_w} unit="W" status={getStatus('power_energy.power_peak_w')} classification={getConsistency('power_energy.power_peak_w')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Energy Total</div>
                        <div className="text-xl text-blue-400"><MetricValue value={suite.power_energy.energy_total_j} unit="J" status={getStatus('power_energy.energy_total_j')} classification={getConsistency('power_energy.energy_total_j')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Voltage Avg</div>
                        <div className="font-mono"><MetricValue value={suite.power_energy.voltage_avg_v} unit="V" status={getStatus('power_energy.voltage_avg_v')} classification={getConsistency('power_energy.voltage_avg_v')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Current Avg</div>
                        <div className="font-mono"><MetricValue value={suite.power_energy.current_avg_a} unit="A" status={getStatus('power_energy.current_avg_a')} classification={getConsistency('power_energy.current_avg_a')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Energy/Handshake</div>
                        <div className="font-mono"><MetricValue value={suite.power_energy.energy_per_handshake_j} unit="J" status={getStatus('power_energy.energy_per_handshake_j')} classification={getConsistency('power_energy.energy_per_handshake_j')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Sampling Rate</div>
                        <div className="font-mono"><MetricValue value={suite.power_energy.power_sampling_rate_hz} unit="Hz" status={getStatus('power_energy.power_sampling_rate_hz')} classification={getConsistency('power_energy.power_sampling_rate_hz')} /></div>
                    </div>
                </div>
            </MetricCard>

            {/* F. Rekey Metrics */}
            <MetricCard title={<span>F. Rekey Metrics <span title="Blackout is proxy-defined and traffic-dependent." className="text-gray-500 text-xs">(info)</span></span>}>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                    <div>
                        <div className="text-gray-400 text-xs">Rekey Attempts</div>
                        <div className="font-mono"><MetricValue value={suite.rekey.rekey_attempts} classification={getConsistency('rekey.rekey_attempts')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Rekey Duration</div>
                        <div className="font-mono"><MetricValue value={suite.rekey.rekey_duration_ms} unit="ms" classification={getConsistency('rekey.rekey_duration_ms')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Rekey Blackout</div>
                        <div className="font-mono"><MetricValue value={suite.rekey.rekey_blackout_duration_ms} unit="ms" classification={getConsistency('rekey.rekey_blackout_duration_ms')} /></div>
                    </div>
                </div>
            </MetricCard>

            {/* R. Validation */}
            <MetricCard title="R. Validation">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                    <div>
                        <div className="text-gray-400 text-xs">Collected Samples</div>
                        <div className="font-mono"><MetricValue value={suite.validation.collected_samples} classification={getConsistency('validation.collected_samples')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Lost Samples</div>
                        <div className="font-mono"><MetricValue value={suite.validation.lost_samples} classification={getConsistency('validation.lost_samples')} /></div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Success Rate</div>
                        <div className="font-mono">
                            <MetricValue value={suite.validation.success_rate_percent !== null && suite.validation.success_rate_percent !== undefined ? suite.validation.success_rate_percent : null} unit="%" classification={getConsistency('validation.success_rate_percent')} />
                        </div>
                    </div>
                    <div>
                        <div className="text-gray-400 text-xs">Result</div>
                        <div className={suite.validation.benchmark_pass_fail === 'PASS' ? 'text-green-400' : 'text-red-400'}>
                            {suite.validation.benchmark_pass_fail || '—'}
                        </div>
                    </div>
                </div>
            </MetricCard>
        </div>
    );
}
