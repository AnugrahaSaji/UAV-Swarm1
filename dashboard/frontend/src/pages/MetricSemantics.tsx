/**
 * Metric Semantics Page - Global metric definitions and provenance
 */

import { useEffect, useMemo, useState } from 'react';

interface MetricSemantic {
    key: string;
    category: string;
    origin_side: string;
    authoritative_side: string;
    lifecycle_phase?: string | null;
    nullable_expected?: boolean | null;
    zero_valid?: string | null;
    legacy?: boolean;
    observed_types?: string | null;
}

export default function MetricSemantics() {
    const [semantics, setSemantics] = useState<MetricSemantic[]>([]);
    const [filter, setFilter] = useState('');
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
        fetch('/api/metrics/semantics')
            .then(res => { if (!res.ok) throw new Error(`${res.status}`); return res.json(); })
            .then(setSemantics)
            .catch(() => setSemantics([]))
            .finally(() => setIsLoading(false));
    }, []);

    const filtered = useMemo(() => {
        const term = filter.trim().toLowerCase();
        if (!term) return semantics;
        return semantics.filter(item => item.key.toLowerCase().includes(term));
    }, [filter, semantics]);

    if (isLoading) {
        return <div className="text-center py-12 text-gray-400">Loading metric semantics...</div>;
    }

    return (
        <div className="space-y-6">
            <h1 className="text-2xl font-bold">Metric Semantics</h1>
            <div className="card">
                <div className="text-xs text-gray-500 mb-3">
                    Generated from repository artifacts (schema, aggregator logic, and observed outputs).
                </div>
                <input
                    className="select-input w-full"
                    placeholder="Filter by key (e.g., data_plane, latency, mavlink)"
                    value={filter}
                    onChange={e => setFilter(e.target.value)}
                />
            </div>
            <div className="card overflow-x-auto">
                <table className="data-table">
                    <thead>
                        <tr>
                            <th>Key</th>
                            <th>Category</th>
                            <th>Origin</th>
                            <th>Authority</th>
                            <th>Nullable</th>
                            <th>Zero-valid</th>
                            <th>Legacy</th>
                            <th>Observed Types</th>
                        </tr>
                    </thead>
                    <tbody>
                        {filtered.map(item => (
                            <tr key={item.key}>
                                <td className="font-mono text-xs">{item.key}</td>
                                <td className="text-xs">{item.category}</td>
                                <td className="text-xs">{item.origin_side}</td>
                                <td className="text-xs">{item.authoritative_side}</td>
                                <td className="text-xs">{item.nullable_expected === null || item.nullable_expected === undefined ? '—' : item.nullable_expected ? 'yes' : 'no'}</td>
                                <td className="text-xs">{item.zero_valid ?? '—'}</td>
                                <td className="text-xs">{item.legacy ? 'yes' : 'no'}</td>
                                <td className="text-xs">{item.observed_types ?? '—'}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
