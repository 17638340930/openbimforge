import path from "node:path"

export function getOpenBimForgeRoot(): string {
    return path.resolve(process.env.OPENBIMFORGE_ROOT || process.cwd())
}

/**
 * Returns the root directory for the Nexus Orchestration framework.
 * This identifies the project core for the multi-expert BIM generation.
 */
export function getNexusArchitectRoot(): string {
    return (
        process.env.OPENBIMFORGE_NEXUS_ROOT ||
        process.env.OPENBIMFORGE_ROOT ||
        getOpenBimForgeRoot()
    )
}

const RUNTIME_NAME_MAP: Record<string, string> = {
    runtime_handoffs: path.join("forge_runtime", "handoffs"),
    runtime_state: path.join("forge_runtime", "state"),
    runtime_capabilities: path.join("forge_runtime", "capabilities"),
    runtime_artifacts: path.join("forge_runtime", "artifacts"),
    runtime_logs: path.join("forge_runtime", "logs"),
}

/**
 * Returns the absolute path for a specific Nexus runtime directory.
 * Used for managing Transit-Payloads, Session States, and Digital BIM Assets.
 */
export function getNexusRuntimeRoot(name: string): string {
    const mappedName = RUNTIME_NAME_MAP[name] || name
    return path.join(getNexusArchitectRoot(), mappedName)
}

export function getNexusRuntimeRoots(names: string[]): string[] {
    return names.map((name) => path.resolve(getNexusRuntimeRoot(name)))
}

export function isPathInsideRoots(
    targetPath: string,
    allowedRoots: string[],
): boolean {
    const resolved = path.resolve(targetPath)
    return allowedRoots.some(
        (root) => resolved === root || resolved.startsWith(`${root}${path.sep}`),
    )
}
