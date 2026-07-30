export function statusVariant(status: string): 'outline' | 'secondary' | 'destructive' | 'default' {
	if (status === 'failed') return 'destructive';
	if (status === 'completed' || status === 'passed') return 'default';
	if (status === 'idle') return 'outline';
	return 'secondary';
}

export function clampInteger(value: number, minimum: number, maximum: number): number {
	const numericValue = Number(value);
	if (!Number.isFinite(numericValue)) return minimum;
	return Math.min(maximum, Math.max(minimum, Math.round(numericValue)));
}

export function elapsed(startedAt?: number, finishedAt?: number): string {
	if (startedAt === undefined) return '—';
	const milliseconds = (finishedAt ?? Date.now()) - startedAt;
	return `${Math.max(0, milliseconds / 1_000).toFixed(1)}s`;
}
