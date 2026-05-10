export type ForgeVisionMode = "form" | "layout"

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

export interface ForgeVisionLayoutRoom {
    id: string
    type: "office" | "meeting" | "corridor" | "core" | "service" | "unknown"
    name?: string
    polygon: Array<[number, number]>
    areaM2?: number
    confidence?: number
}

export interface ForgeVisionLayoutResult {
    source: "forgevision-layout"
    sessionId: string
    status: "completed" | "completed_reference_only" | "failed" | "no_outputs" | "timeout"
    previewPaths: string[]
    layoutTopologyPath?: string
    logPath?: string
    forgeVisionLayoutConstraints: {
        inputKind: "floor_plan" | "layout_reference" | "unknown"
        isReferenceOnly: true
        rooms: ForgeVisionLayoutRoom[]
        adjacency: Array<[string, string]>
        circulationHint?: string
        coreHint?: string
        scaleHint?: string
        notes: string[]
    }
    constraints?: ForgeVisionLayoutResult["forgeVisionLayoutConstraints"]
}

export type ForgeVisionResult = ForgeVisionFormResult | ForgeVisionLayoutResult
export type NormalizedVisionaryResult = ForgeVisionResult
