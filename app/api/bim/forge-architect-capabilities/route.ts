import { promises as fs } from "fs"
import path from "path"
import { NextResponse } from "next/server"
import {
    getNexusArchitectRoot,
    getNexusRuntimeRoot,
} from "@/lib/bim/openbimforge-paths"

export const runtime = "nodejs"

/**
 * Returns the absolute path to the Nexus Synthesis Capability Manifest.
 */
function getManifestPath(): string {
    return path.join(
        getNexusRuntimeRoot("runtime_capabilities"),
        "vectorworks_styles.json",
    )
}

/**
 * Builds the Python script for scanning synthesis capabilities within the BIM Synthesis Workbench.
 */
function buildCapabilityScanScript(): string {
    const projectRoot = getNexusArchitectRoot()
    const manifestPath = getManifestPath()
    return [
        "import sys",
        "",
        `project_root = r"${projectRoot}"`,
        "if project_root not in sys.path:",
        "    sys.path.insert(0, project_root)",
        "",
        "from tool_agent_bridge.vectorworks_capability_scan import write_manifest",
        "",
        `path = write_manifest(r"${manifestPath}")`,
        "print(path)",
    ].join("\n")
}

export async function GET() {
    const manifestPath = getManifestPath()
    const capabilityScanScript = buildCapabilityScanScript()
    try {
        const content = await fs.readFile(manifestPath, "utf-8")
        const stat = await fs.stat(manifestPath)
        return NextResponse.json({
            ok: true,
            ready: true,
            manifestPath,
            updatedAt: stat.mtime.toISOString(),
            manifest: JSON.parse(content),
            capabilityScanScript,
            maintenanceNote:
                "Re-execute synthesis capability scan upon variations in the BIM Workbench environment, including style libraries or plugin resources.",
        })
    } catch {
        return NextResponse.json({
            ok: true,
            ready: false,
            manifestPath,
            capabilityScanScript,
            message:
                "Nexus Synthesis Capability Contract is currently uninitialized. Execute the provided scan script within the BIM Synthesis Workbench.",
        })
    }
}
