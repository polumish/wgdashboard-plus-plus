/**
 * Format a traffic value (stored in gigabytes by the backend) into a
 * human-readable string with an auto-scaled unit (B, KB, MB, GB, TB).
 *
 * The backend persists all peer/configuration traffic counters as GB.
 * Displaying them always as GB means small traffic like 5 MiB shows up
 * as "0.0047 GB", which is unreadable. This helper picks the largest
 * unit where the number is >= 1, and falls back to bytes for tiny
 * values.
 *
 * @param {number|string} gb  Traffic value in gigabytes
 * @returns {string}          Formatted string like "5.47 MB" or "1.23 GB"
 */
export function formatTraffic(gb) {
    const value = Number(gb)
    if (!value || value <= 0 || !Number.isFinite(value)) {
        return '0 B'
    }
    // Convert GB to bytes for scaling logic.
    const bytes = value * 1024 * 1024 * 1024
    const units = ['B', 'KB', 'MB', 'GB', 'TB']
    let i = 0
    let n = bytes
    while (n >= 1024 && i < units.length - 1) {
        n /= 1024
        i++
    }
    // Whole bytes: no decimals. KB+: two decimals (one for GB+ is enough
    // but two keeps small changes visible).
    const decimals = i === 0 ? 0 : 2
    return `${n.toFixed(decimals)} ${units[i]}`
}
