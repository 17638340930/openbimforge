export interface ForgeVisionFormResult {
    source: "forgevision-form"
    sessionId: string
    status: "completed" | "completed_reference_only" | "failed" | "no_outputs" | "timeout"
    previewPaths: string[]
    stlPaths: string[]
    cadVectorPaths?: string[]
    logPath?: string
    forgeVisionConstraints: {
        inputKind: "concept_sketch" | "massing_reference" | "unknown"
        isReferenceOnly: true
        massingReferencePath?: string
        visualPreviewPath?: string
        cadVectorPath?: string
        buildingFootprintHint?: string
        massingHint?: string
        notes: string[]
    }
    constraints?: ForgeVisionFormResult["forgeVisionConstraints"]
}

export type NormalizedVisionaryResult = ForgeVisionFormResult
