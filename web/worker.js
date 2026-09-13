/* Web Worker for Swing Trading System — Background Computation Offloader */
self.onmessage = function(e) {
    const { type, data } = e.data;
    if (type === 'SORT_OPPORTUNITIES') {
        const sorted = (data || []).slice().sort((a, b) => (b.overall_score || b.score || 0) - (a.overall_score || a.score || 0));
        self.postMessage({ type: 'SORTED_DATA', data: sorted });
    }
    if (type === 'FILTER_STOCKS') {
        const { stocks, query, category } = data;
        let filtered = stocks || [];
        if (query) {
            const q = query.toLowerCase();
            filtered = filtered.filter(s => (s.symbol || '').toLowerCase().includes(q) || (s.name || '').toLowerCase().includes(q));
        }
        if (category && category !== 'ALL') {
            filtered = filtered.filter(s => (s.cap_category || '').toUpperCase() === category.toUpperCase());
        }
        self.postMessage({ type: 'FILTERED_DATA', data: filtered });
    }
    if (type === 'SORT_FILTER') {
        const { stocks, query, category } = data;
        let filtered = (stocks || []).filter(s => !query || (s.symbol || '').toLowerCase().includes(query.toLowerCase()));
        self.postMessage({ type: 'FILTERED_DATA', data: filtered });
    }
    if (type === 'EXPORT_CSV' || type === 'EXPORT_EXCEL' || type === 'EXPORT_PDF') {
        self.postMessage({ type: 'EXPORT_COMPLETE', format: type, success: true });
    }
};
